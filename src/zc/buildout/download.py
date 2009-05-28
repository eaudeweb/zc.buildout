##############################################################################
#
# Copyright (c) 2009 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Buildout download infrastructure"""

try:
    from hashlib import md5
except ImportError:
    from md5 import new as md5
import os
import os.path
import shutil
import urllib
import urlparse
import zc.buildout


class URLOpener(urllib.FancyURLopener):
    http_error_default = urllib.URLopener.http_error_default


class ChecksumError(zc.buildout.UserError):
    pass


url_opener = URLOpener()


FALLBACK = object()


class Download(object):
    """Configurable download utility.

    Handles the download cache and offline mode.

    Download(buildout, use_cache=True, namespace=None, hash_name=False)

    buildout: mapping of buildout options (the ``buildout`` config section)
    use_cache: whether to use the cache at all
    namespace: namespace directory to use inside the cache
    hash_name: whether to use a hash of the URL as cache file name

    """

    def __init__(self, buildout,
                 use_cache=True, namespace=None, hash_name=False):
        self.buildout = buildout
        self.set_cache(use_cache, namespace)
        self.hash_name = hash_name

    def set_cache(self, use_cache=True, namespace=None):
        """Configure the caching properties.

        See __init__.

        """
        self.use_cache = use_cache
        self.namespace = namespace
        if use_cache and self.buildout.get('download-cache'):
            self.cache = os.path.join(self.buildout['download-cache'],
                                      namespace or '')
        else:
            self.cache = None

    def __call__(self, url, md5sum=None, path=None):
        """Download a file according to the utility's configuration.

        url: URL to download
        md5sum: MD5 checksum to match
        path: where to place the downloaded file

        Returns the path to the downloaded file.

        """
        if self.cache is None:
            return self.download(url, md5sum, path)

        cached_path = self.download_cached(url, md5sum)
        if (path is None
            or os.path.abspath(path) == os.path.abspath(cached_path)):
            return cached_path

        try:
            os.link(cached_path, path)
        except (AttributeError, OSError):
            shutil.copyfile(cached_path, path)
        return path

    def download_cached(self, url, md5sum=None):
        """Download a file to the cache, assuming the cache was configured.

        See __call__.

        """
        if not os.path.exists(self.cache):
            os.makedirs(self.cache)
        cached_path = os.path.join(self.cache, self.filename(url))

        if os.path.isfile(cached_path):
            if self.use_cache is FALLBACK:
                try:
                    self.download(url, md5sum, cached_path)
                except ChecksumError:
                    raise
                except Exception:
                    pass

            if not check_md5sum(cached_path, md5sum):
                raise ChecksumError(
                    'MD5 checksum mismatch for cached download '
                    'from %r at %r' % (url, cached_path))
        else:
            self.download(url, md5sum, cached_path)

        return cached_path

    def download(self, url, md5sum=None, path=None):
        """Download a file to a given path.

        If path is None, download to a temporary file.

        See __call__.

        """
        if (self.buildout.get('offline')
            and urlparse.urlparse(url).scheme != 'file'):
            raise zc.buildout.UserError(
                "Couldn't download %r in offline mode." % url)

        urllib._urlopener = url_opener
        path, headers = urllib.urlretrieve(url, path)
        if not check_md5sum(path, md5sum):
            raise ChecksumError(
                'MD5 checksum mismatch downloading %r' % url)
        return path

    def filename(self, url):
        """Determine a file name from a URL according to the configuration.

        """
        if self.hash_name:
            return md5(url).hexdigest()
        else:
            for name in reversed(urlparse.urlparse(url).path.split('/')):
                if name:
                    return name
            else:
                return 'default'


def check_md5sum(path, md5sum):
    """Tell whether the MD5 checksum of the file at path matches.

    No checksum being given is considered a match.

    """
    if md5sum is None:
        return True

    f = open(path)
    checksum = md5()
    try:
        chunk = f.read(2**16)
        while chunk:
            checksum.update(chunk)
            chunk = f.read(2**16)
        return checksum.hexdigest() == md5sum
    finally:
        f.close()
