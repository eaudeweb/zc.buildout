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
from zc.buildout.easy_install import realpath
import atexit
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
            self.cache = os.path.join(
                realpath(self.buildout['download-cache']), namespace or '')
        else:
            self.cache = None

    def __call__(self, url, md5sum=None, path=None):
        """Download a file according to the utility's configuration.

        url: URL to download
        md5sum: MD5 checksum to match
        path: where to place the downloaded file

        Returns the path to the downloaded file.

        """
        if urlparse.urlparse(url, 'file').scheme == 'file':
            local_path = self.use_local(url, md5sum)
        elif self.cache:
            local_path = self.download_cached(url, md5sum)
        else:
            local_path = self.download(url, md5sum, path)

        if path is None or realpath(path) == realpath(local_path):
            return local_path

        try:
            os.link(local_path, path)
        except (AttributeError, OSError):
            shutil.copyfile(local_path, path)
        return path

    def use_local(self, url, md5sum=None):
        """Locate and verify the MD5 checksum of a local resource.
        """
        path = urlparse.urlparse(url).path
        if not check_md5sum(path, md5sum):
            raise ChecksumError(
                'MD5 checksum mismatch for local resource at %r.' % path)
        return path

    def download_cached(self, url, md5sum=None):
        """Download a file from a URL using the cache.

        This method assumes that the cache has been configured. Optionally, it
        raises a ChecksumError if a cached copy of a file has an MD5 mismatch,
        but will not remove the copy in that case.

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
        """Download a file from a URL to a given or temporary path.

        Note: The url is assumed to point to an online resource; this method
        might try to move or remove local resources.

        The resource is always downloaded to a temporary file and moved to the
        specified path only after the download is complete and the checksum
        (if given) matches. If path is None, the temporary file is returned
        and scheduled for deletion at process exit.

        """
        if self.buildout.get('offline'):
            raise zc.buildout.UserError(
                "Couldn't download %r in offline mode." % url)

        urllib._urlopener = url_opener
        tmp_path, headers = urllib.urlretrieve(url)
        if not check_md5sum(tmp_path, md5sum):
            os.remove(tmp_path)
            raise ChecksumError(
                'MD5 checksum mismatch downloading %r' % url)

        if path:
            shutil.move(tmp_path, path)
            return path
        else:
            atexit.register(remove, tmp_path)
            return tmp_path

    def filename(self, url):
        """Determine a file name from a URL according to the configuration.

        """
        if self.hash_name:
            return md5(url).hexdigest()
        else:
            parsed = urlparse.urlparse(url)
            for name in reversed(parsed.path.split('/')):
                if name:
                    return name
            else:
                return '%s:%s' % (parsed.host, parsed.port)


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


def remove(path):
    if os.path.exists(path):
        os.remove(path)
