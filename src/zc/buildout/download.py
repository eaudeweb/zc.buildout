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
import logging
import os
import os.path
import shutil
import tempfile
import urllib
import urlparse
import zc.buildout


class URLOpener(urllib.FancyURLopener):
    http_error_default = urllib.URLopener.http_error_default


class ChecksumError(zc.buildout.UserError):
    pass


url_opener = URLOpener()


class Download(object):
    """Configurable download utility.

    Handles the download cache and offline mode.

    Download(options=None, cache=None, namespace=None, hash_name=False)

    options: mapping of buildout options (e.g. a ``buildout`` config section)
    cache: path to the download cache (excluding namespaces)
    namespace: namespace directory to use inside the cache
    hash_name: whether to use a hash of the URL as cache file name
    logger: an optional logger to receive download-related log messages

    """

    def __init__(self, options={}, cache=-1, namespace=None,
                 offline=-1, fallback=False, hash_name=False, logger=None):
        self.cache = cache
        if cache == -1:
            self.cache = options.get('download-cache')
        self.namespace = namespace
        self.offline = offline
        if offline == -1:
            self.offline = (options.get('offline') == 'true'
                            or options.get('install-from-cache') == 'true')
        self.fallback = fallback
        self.hash_name = hash_name
        self.logger = logger or logging.getLogger('zc.buildout')

    @property
    def cache_dir(self):
        if self.cache is not None:
            return os.path.join(realpath(self.cache), self.namespace or '')

    def __call__(self, url, md5sum=None, path=None):
        """Download a file according to the utility's configuration.

        url: URL to download
        md5sum: MD5 checksum to match
        path: where to place the downloaded file

        Returns the path to the downloaded file.

        """
        if self.cache:
            local_path = self.download_cached(url, md5sum)
        else:
            local_path = self.download(url, md5sum, path)

        return locate_at(local_path, path)

    def download_cached(self, url, md5sum=None):
        """Download a file from a URL using the cache.

        This method assumes that the cache has been configured. Optionally, it
        raises a ChecksumError if a cached copy of a file has an MD5 mismatch,
        but will not remove the copy in that case.

        """
        cache_dir = self.cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        cache_key = self.filename(url)
        cached_path = os.path.join(cache_dir, cache_key)

        self.logger.debug('Searching cache at %s' % cache_dir)
        if os.path.isfile(cached_path):
            if self.fallback:
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
            self.logger.debug('Using cache file %s' % cached_path)
        else:
            self.logger.debug('Cache miss; will cache %s as %s' %
                              (url, cached_path))
            self.download(url, md5sum, cached_path)

        return cached_path

    def download(self, url, md5sum=None, path=None):
        """Download a file from a URL to a given or temporary path.

        An online resource is always downloaded to a temporary file and moved
        to the specified path only after the download is complete and the
        checksum (if given) matches. If path is None, the temporary file is
        returned and the client code is responsible for cleaning it up.

        """
        parsed_url = urlparse.urlparse(url, 'file')
        url_scheme, _, url_path = parsed_url[:3]
        if url_scheme == 'file':
            self.logger.debug('Using local resource %s' % url)
            if not check_md5sum(url_path, md5sum):
                raise ChecksumError(
                    'MD5 checksum mismatch for local resource at %r.' %
                    url_path)
            return locate_at(url_path, path)

        if self.offline:
            raise zc.buildout.UserError(
                "Couldn't download %r in offline mode." % url)

        self.logger.info('Downloading %s' % url)
        urllib._urlopener = url_opener
        handle, tmp_path = tempfile.mkstemp(prefix='buildout-')
        tmp_path, headers = urllib.urlretrieve(url, tmp_path)
        os.close(handle)
        if not check_md5sum(tmp_path, md5sum):
            os.remove(tmp_path)
            raise ChecksumError(
                'MD5 checksum mismatch downloading %r' % url)

        if path:
            shutil.move(tmp_path, path)
            return path
        else:
            return tmp_path

    def filename(self, url):
        """Determine a file name from a URL according to the configuration.

        """
        if self.hash_name:
            return md5(url).hexdigest()
        else:
            parsed = urlparse.urlparse(url)
            url_path = parsed[2]
            for name in reversed(url_path.split('/')):
                if name:
                    return name
            else:
                url_host, url_port = parsed[-2:]
                return '%s:%s' % (url_host, url_port)


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


def locate_at(source, dest):
    if dest is None or realpath(dest) == realpath(source):
        return source

    try:
        os.link(source, dest)
    except (AttributeError, OSError):
        shutil.copyfile(source, dest)
    return dest
