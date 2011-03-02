##############################################################################
#
# Copyright (c) 2009-2011 Zope Corporation and Contributors.
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
import re
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

    Download(options=None, cache=None, namespace=None,
             offline=False, fallback=False, hash_name=False, logger=None)

    options: mapping of buildout options (e.g. a ``buildout`` config section)
    cache: path to the download cache (excluding namespaces)
    namespace: namespace directory to use inside the cache
    offline: whether to operate in offline mode
    fallback: whether to use the cache as a fallback (try downloading first)
    hash_name: whether to use a hash of the URL as cache file name
    logger: an optional logger to receive download-related log messages

    """

    def __init__(self, options={}, cache=-1, namespace=None,
                 offline=-1, fallback=False, hash_name=False, logger=None):
        self.directory = options.get('directory', '')
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
    def download_cache(self):
        if self.cache is not None:
            return realpath(os.path.join(self.directory, self.cache))

    @property
    def cache_dir(self):
        if self.download_cache is not None:
            return os.path.join(self.download_cache, self.namespace or '')

    def __call__(self, url, md5sum=None, path=None, shared=False):
        """Download a file according to the utility's configuration.

        url: URL to download
        md5sum: MD5 checksum to match
        path: where to place the downloaded file
        shared: whether to attempt hard-linking multiple copies of the
                resource in the file system (cached copy, target path etc)

        Returns the path to the downloaded file.

        """
        if self.cache:
            local_path, is_temp = self.download_cached(url, md5sum, shared)
        else:
            local_path, is_temp = self.download(url, md5sum, path, shared)

        return locate_at(local_path, path, shared), is_temp

    def download_cached(self, url, md5sum=None, shared=False):
        """Download a file from a URL using the cache.

        This method assumes that the cache has been configured. Optionally, it
        raises a ChecksumError if a cached copy of a file has an MD5 mismatch,
        but will not remove the copy in that case. If the resource comes from
        the file system or shall be stored at a target path, an optimisation
        may be attempted to share the file instead of copying it.

        """
        if not os.path.exists(self.download_cache):
            raise zc.buildout.UserError(
                'The directory:\n'
                '%r\n'
                "to be used as a download cache doesn't exist.\n"
                % self.download_cache)
        cache_dir = self.cache_dir
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        cache_key = self.filename(url)
        cached_path = os.path.join(cache_dir, cache_key)

        self.logger.debug('Searching cache at %s' % cache_dir)
        if os.path.exists(cached_path):
            is_temp = False
            if self.fallback:
                try:
                    _, is_temp = self.download(
                        url, md5sum, cached_path, shared)
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
            _, is_temp = self.download(url, md5sum, cached_path, shared)

        return cached_path, is_temp

    def download(self, url, md5sum=None, path=None, shared=False):
        """Download a file from a URL to a given or temporary path.

        An online resource is always downloaded to a temporary file and moved
        to the specified path only after the download is complete and the
        checksum (if given) matches. If path is None, the temporary file is
        returned and the client code is responsible for cleaning it up. If the
        resource comes from the file system, an optimisation may be attempted
        to share the existing file instead of copying it.

        """
        # Make sure the drive letter in windows-style file paths isn't
        # interpreted as a URL scheme.
        if re.match(r"^[A-Za-z]:\\", url):
            url = 'file:' + url

        parsed_url = urlparse.urlparse(url, 'file')
        url_scheme, _, url_path = parsed_url[:3]
        if url_scheme == 'file':
            self.logger.debug('Using local resource %s' % url)
            if not check_md5sum(url_path, md5sum):
                raise ChecksumError(
                    'MD5 checksum mismatch for local resource at %r.' %
                    url_path)
            return locate_at(url_path, path, shared), False

        if self.offline:
            raise zc.buildout.UserError(
                "Couldn't download %r in offline mode." % url)

        self.logger.info('Downloading %s' % url)
        urllib._urlopener = url_opener
        handle, tmp_path = tempfile.mkstemp(prefix='buildout-')
        try:
            try:
                tmp_path, headers = urllib.urlretrieve(url, tmp_path)
                if not check_md5sum(tmp_path, md5sum):
                    raise ChecksumError(
                        'MD5 checksum mismatch downloading %r' % url)
            finally:
                os.close(handle)
        except:
            os.remove(tmp_path)
            raise

        if path:
            shutil.move(tmp_path, path)
            return path, False
        else:
            return tmp_path, True

    def filename(self, url):
        """Determine a file name from a URL according to the configuration.

        """
        if self.hash_name:
            return md5(url).hexdigest()
        else:
            if re.match(r"^[A-Za-z]:\\", url):
                url = 'file:' + url
            parsed = urlparse.urlparse(url, 'file')
            url_path = parsed[2]

            if parsed[0] == 'file':
                while True:
                    url_path, name = os.path.split(url_path)
                    if name:
                        return name
                    if not url_path:
                        break
            else:
                for name in reversed(url_path.split('/')):
                    if name:
                        return name

            url_host, url_port = parsed[-2:]
            return '%s:%s' % (url_host, url_port)


def check_md5sum(path, md5sum):
    """Tell whether the MD5 checksum of the file at path matches.

    No checksum being given is considered a match.

    """
    if md5sum is None:
        return True

    f = open(path, 'rb')
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


def locate_at(source, dest, shared):
    if dest is None or realpath(dest) == realpath(source):
        return source

    if os.path.isdir(source):
        shutil.copytree(source, dest)
    elif shared:
        try:
            if os.path.exists(dest):
                os.unlink(dest)
            os.link(source, dest)
        except (AttributeError, OSError):
            shutil.copyfile(source, dest)
    else:
        shutil.copyfile(source, dest)

    return dest
