#############################################################################
#
# Copyright (c) 2005 Zope Corporation and Contributors.
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
"""Python easy_install API

This module provides a high-level Python API for installing packages.
It doesn't install scripts.  It uses setuptools and requires it to be
installed.

$Id$
"""

import distutils.errors
import fnmatch
import glob
import logging
import os
import pkg_resources
import py_compile
import re
import setuptools.archive_util
import setuptools.command.setopt
import setuptools.package_index
import shutil
import subprocess
import sys
import tempfile
import urlparse
import zc.buildout
import zipimport

_oprp = getattr(os.path, 'realpath', lambda path: path)
def realpath(path):
    return os.path.normcase(os.path.abspath(_oprp(path)))

default_index_url = os.environ.get(
    'buildout-testing-index-url',
    'http://pypi.python.org/simple',
    )

logger = logging.getLogger('zc.buildout.easy_install')

url_match = re.compile('[a-z0-9+.-]+://').match

is_win32 = sys.platform == 'win32'
is_jython = sys.platform.startswith('java')

if is_jython:
    import subprocess
    import java.lang.System
    jython_os_name = (java.lang.System.getProperties()['os.name']).lower()


setuptools_loc = pkg_resources.working_set.find(
    pkg_resources.Requirement.parse('setuptools')
    ).location

# Include buildout and setuptools eggs in paths.  We prevent dupes just to
# keep from duplicating any log messages about them.
buildout_loc = pkg_resources.working_set.find(
    pkg_resources.Requirement.parse('zc.buildout')).location
buildout_and_setuptools_path = [setuptools_loc]
if os.path.normpath(setuptools_loc) != os.path.normpath(buildout_loc):
    buildout_and_setuptools_path.append(buildout_loc)

def _get_system_packages(executable):
    """return a pair of the standard lib and site packages for the executable.
    """
    # We want to get a list of the site packages, which is not easy.  The
    # canonical way to do this is to use distutils.sysconfig.get_python_lib(),
    # but that only returns a single path, which does not reflect reality for
    # many system Pythons, which have multiple additions.  Instead, we start
    # Python with -S, which does not import site.py and set up the extra paths
    # like site-packages or (Ubuntu/Debian) dist-packages and python-support.
    # We then compare that sys.path with the normal one.  The set of the normal
    # one minus the set of the ones in ``python -S`` is the set of packages
    # that are effectively site-packages.
    def get_sys_path(clean=False):
        cmd = [executable, "-c",
               "import sys, os;"
               "print repr([os.path.normpath(p) for p in sys.path])"]
        if clean:
            cmd.insert(1, '-S')
        _proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = _proc.communicate();
        if _proc.returncode:
            raise RuntimeError(
                'error trying to get system packages:\n%s' % (stderr,))
        res = eval(stdout)
        try:
            res.remove('.')
        except ValueError:
            pass
        return res
    stdlib = get_sys_path(clean=True)
    # The given executable might not be the current executable, so it is
    # appropriate to do another subprocess to figure out what the additional
    # site-package paths are. Moreover, even if this executable *is* the
    # current executable, this code might be run in the context of code that
    # has manipulated the sys.path--for instance, to add local zc.buildout or
    # setuptools eggs.
    site_packages = [p for p in get_sys_path() if p not in stdlib]
    return (stdlib, site_packages)


class IncompatibleVersionError(zc.buildout.UserError):
    """A specified version is incompatible with a given requirement.
    """

_versions = {sys.executable: '%d.%d' % sys.version_info[:2]}
def _get_version(executable):
    try:
        return _versions[executable]
    except KeyError:
        cmd = _safe_arg(executable) + ' -V'
        p = subprocess.Popen(cmd,
                             shell=True,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             close_fds=not is_win32)
        i, o = (p.stdin, p.stdout)
        i.close()
        version = o.read().strip()
        o.close()
        pystring, version = version.split()
        assert pystring == 'Python'
        version = re.match('(\d[.]\d)([.].*\d)?$', version).group(1)
        _versions[executable] = version
        return version

FILE_SCHEME = re.compile('file://', re.I).match


class AllowHostsPackageIndex(setuptools.package_index.PackageIndex):
    """Will allow urls that are local to the system.

    No matter what is allow_hosts.
    """
    def url_ok(self, url, fatal=False):
        if FILE_SCHEME(url):
            return True
        return setuptools.package_index.PackageIndex.url_ok(self, url, False)


_indexes = {}
def _get_index(executable, index_url, find_links, allow_hosts=('*',),
               path=None):
    # If path is None, the index will use sys.path.  If you provide an empty
    # path ([]), it will complain uselessly about missing index pages for
    # packages found in the paths that you expect to use.  Therefore, this path
    # is always the same as the _env path in the Installer.
    key = executable, index_url, tuple(find_links)
    index = _indexes.get(key)
    if index is not None:
        return index

    if index_url is None:
        index_url = default_index_url
    index = AllowHostsPackageIndex(
        index_url, hosts=allow_hosts, search_path=path,
        python=_get_version(executable)
        )

    if find_links:
        index.add_find_links(find_links)

    _indexes[key] = index
    return index

clear_index_cache = _indexes.clear

if is_win32:
    # work around spawn lamosity on windows
    # XXX need safe quoting (see the subproces.list2cmdline) and test
    def _safe_arg(arg):
        return '"%s"' % arg
else:
    _safe_arg = str

_easy_install_cmd = _safe_arg(
    'from setuptools.command.easy_install import main; main()'
    )

class Installer:

    _versions = {}
    _download_cache = None
    _install_from_cache = False
    _prefer_final = True
    _use_dependency_links = True
    _allow_picked_versions = True
    _always_unzip = False
    _include_site_packages = True
    _allowed_eggs_from_site_packages = ('*',)

    def __init__(self,
                 dest=None,
                 links=(),
                 index=None,
                 executable=sys.executable,
                 always_unzip=None,
                 path=None,
                 newest=True,
                 versions=None,
                 use_dependency_links=None,
                 include_site_packages=None,
                 allowed_eggs_from_site_packages=None,
                 allow_hosts=('*',)
                 ):
        self._dest = dest
        self._allow_hosts = allow_hosts

        if self._install_from_cache:
            if not self._download_cache:
                raise ValueError("install_from_cache set to true with no"
                                 " download cache")
            links = ()
            index = 'file://' + self._download_cache

        if use_dependency_links is not None:
            self._use_dependency_links = use_dependency_links
        self._links = links = list(_fix_file_links(links))
        if self._download_cache and (self._download_cache not in links):
            links.insert(0, self._download_cache)

        self._index_url = index
        self._executable = executable
        if always_unzip is not None:
            self._always_unzip = always_unzip
        path = (path and path[:] or [])
        if include_site_packages is not None:
            self._include_site_packages = include_site_packages
        if allowed_eggs_from_site_packages is not None:
            self._allowed_eggs_from_site_packages = tuple(
                allowed_eggs_from_site_packages)
        stdlib, self._site_packages = _get_system_packages(executable)
        if self._include_site_packages:
            path.extend(buildout_and_setuptools_path)
            path.extend(self._site_packages)
        # else we could try to still include the buildout_and_setuptools_path
        # if the elements are not in site_packages, but we're not bothering
        # with this optimization for now, in the name of code simplicity.
        if dest is not None and dest not in path:
            path.insert(0, dest)
        self._path = path
        if self._dest is None:
            newest = False
        self._newest = newest
        self._env = pkg_resources.Environment(path,
                                              python=_get_version(executable))
        self._index = _get_index(executable, index, links, self._allow_hosts,
                                 self._path)

        if versions is not None:
            self._versions = versions

    _allowed_eggs_from_site_packages_regex = None
    def allow_site_package_egg(self, name):
        if (not self._include_site_packages or
            not self._allowed_eggs_from_site_packages):
            # If the answer is a blanket "no," perform a shortcut.
            return False
        if self._allowed_eggs_from_site_packages_regex is None:
            pattern = '(%s)' % (
                '|'.join(
                    fnmatch.translate(name)
                    for name in self._allowed_eggs_from_site_packages),
                )
            self._allowed_eggs_from_site_packages_regex = re.compile(pattern)
        return bool(self._allowed_eggs_from_site_packages_regex.match(name))

    def _satisfied(self, req, source=None):
        # We get all distributions that match the given requirement.  If we are
        # not supposed to include site-packages for the given egg, we also
        # filter those out. Even if include_site_packages is False and so we
        # have excluded site packages from the _env's paths (see
        # Installer.__init__), we need to do the filtering here because an
        # .egg-link, such as one for setuptools or zc.buildout installed by
        # zc.buildout.buildout.Buildout.bootstrap, can indirectly include a
        # path in our _site_packages.
        dists = [dist for dist in self._env[req.project_name] if (
                    dist in req and (
                        dist.location not in self._site_packages or
                        self.allow_site_package_egg(dist.project_name))
                    )
                ]
        if not dists:
            logger.debug('We have no distributions for %s that satisfies %r.',
                         req.project_name, str(req))

            return None, self._obtain(req, source)

        # Note that dists are sorted from best to worst, as promised by
        # env.__getitem__

        for dist in dists:
            if (dist.precedence == pkg_resources.DEVELOP_DIST):
                logger.debug('We have a develop egg: %s', dist)
                return dist, None

        # Special common case, we have a specification for a single version:
        specs = req.specs
        if len(specs) == 1 and specs[0][0] == '==':
            logger.debug('We have the distribution that satisfies %r.',
                         str(req))
            return dists[0], None

        if self._prefer_final:
            fdists = [dist for dist in dists
                      if _final_version(dist.parsed_version)
                      ]
            if fdists:
                # There are final dists, so only use those
                dists = fdists

        if not self._newest:
            # We don't need the newest, so we'll use the newest one we
            # find, which is the first returned by
            # Environment.__getitem__.
            return dists[0], None

        best_we_have = dists[0] # Because dists are sorted from best to worst

        # We have some installed distros.  There might, theoretically, be
        # newer ones.  Let's find out which ones are available and see if
        # any are newer.  We only do this if we're willing to install
        # something, which is only true if dest is not None:

        if self._dest is not None:
            best_available = self._obtain(req, source)
        else:
            best_available = None

        if best_available is None:
            # That's a bit odd.  There aren't any distros available.
            # We should use the best one we have that meets the requirement.
            logger.debug(
                'There are no distros available that meet %r.\n'
                'Using our best, %s.',
                str(req), best_available)
            return best_we_have, None

        if self._prefer_final:
            if _final_version(best_available.parsed_version):
                if _final_version(best_we_have.parsed_version):
                    if (best_we_have.parsed_version
                        <
                        best_available.parsed_version
                        ):
                        return None, best_available
                else:
                    return None, best_available
            else:
                if (not _final_version(best_we_have.parsed_version)
                    and
                    (best_we_have.parsed_version
                     <
                     best_available.parsed_version
                     )
                    ):
                    return None, best_available
        else:
            if (best_we_have.parsed_version
                <
                best_available.parsed_version
                ):
                return None, best_available

        logger.debug(
            'We have the best distribution that satisfies %r.',
            str(req))
        return best_we_have, None

    def _load_dist(self, dist):
        dists = pkg_resources.Environment(
            dist.location,
            python=_get_version(self._executable),
            )[dist.project_name]
        assert len(dists) == 1
        return dists[0]

    def _call_easy_install(self, spec, ws, dest, dist):

        tmp = tempfile.mkdtemp(dir=dest)
        try:
            path = self._get_dist(
                self._constrain(pkg_resources.Requirement.parse('setuptools')),
                ws, False,
                )[0].location

            args = ('-c', _easy_install_cmd, '-mUNxd', _safe_arg(tmp))
            if self._always_unzip:
                args += ('-Z', )
            level = logger.getEffectiveLevel()
            if level > 0:
                args += ('-q', )
            elif level < 0:
                args += ('-v', )

            args += (_safe_arg(spec), )

            if level <= logging.DEBUG:
                logger.debug('Running easy_install:\n%s "%s"\npath=%s\n',
                             self._executable, '" "'.join(args), path)

            if is_jython:
                extra_env = dict(os.environ, PYTHONPATH=path)
            else:
                args += (dict(os.environ, PYTHONPATH=path), )

            sys.stdout.flush() # We want any pending output first

            if is_jython:
                exit_code = subprocess.Popen(
                [_safe_arg(self._executable)] + list(args),
                env=extra_env).wait()
            else:
                exit_code = os.spawnle(
                    os.P_WAIT, self._executable, _safe_arg (self._executable),
                    *args)

            dists = []
            env = pkg_resources.Environment(
                [tmp],
                python=_get_version(self._executable),
                )
            for project in env:
                dists.extend(env[project])

            if exit_code:
                logger.error(
                    "An error occured when trying to install %s. "
                    "Look above this message for any errors that "
                    "were output by easy_install.",
                    dist)

            if not dists:
                raise zc.buildout.UserError("Couldn't install: %s" % dist)

            if len(dists) > 1:
                logger.warn("Installing %s\n"
                            "caused multiple distributions to be installed:\n"
                            "%s\n",
                            dist, '\n'.join(map(str, dists)))
            else:
                d = dists[0]
                if d.project_name != dist.project_name:
                    logger.warn("Installing %s\n"
                                "Caused installation of a distribution:\n"
                                "%s\n"
                                "with a different project name.",
                                dist, d)
                if d.version != dist.version:
                    logger.warn("Installing %s\n"
                                "Caused installation of a distribution:\n"
                                "%s\n"
                                "with a different version.",
                                dist, d)

            result = []
            for d in dists:
                newloc = os.path.join(dest, os.path.basename(d.location))
                if os.path.exists(newloc):
                    if os.path.isdir(newloc):
                        shutil.rmtree(newloc)
                    else:
                        os.remove(newloc)
                os.rename(d.location, newloc)

                [d] = pkg_resources.Environment(
                    [newloc],
                    python=_get_version(self._executable),
                    )[d.project_name]

                result.append(d)

            return result

        finally:
            shutil.rmtree(tmp)

    def _obtain(self, requirement, source=None):
        # initialize out index for this project:
        index = self._index

        if index.obtain(requirement) is None:
            # Nothing is available.
            return None

        # Filter the available dists for the requirement and source flag.  If
        # we are not supposed to include site-packages for the given egg, we
        # also filter those out. Even if include_site_packages is False and so
        # we have excluded site packages from the _env's paths (see
        # Installer.__init__), we need to do the filtering here because an
        # .egg-link, such as one for setuptools or zc.buildout installed by
        # zc.buildout.buildout.Buildout.bootstrap, can indirectly include a
        # path in our _site_packages.
        dists = [dist for dist in index[requirement.project_name]
                 if ((dist in requirement)
                     and
                     (dist.location not in self._site_packages or
                      self.allow_site_package_egg(dist.project_name))
                     and
                     ((not source) or
                      (dist.precedence == pkg_resources.SOURCE_DIST)
                      )
                     )
                 ]

        # If we prefer final dists, filter for final and use the
        # result if it is non empty.
        if self._prefer_final:
            fdists = [dist for dist in dists
                      if _final_version(dist.parsed_version)
                      ]
            if fdists:
                # There are final dists, so only use those
                dists = fdists

        # Now find the best one:
        best = []
        bestv = ()
        for dist in dists:
            distv = dist.parsed_version
            if distv > bestv:
                best = [dist]
                bestv = distv
            elif distv == bestv:
                best.append(dist)

        if not best:
            return None

        if len(best) == 1:
            return best[0]

        if self._download_cache:
            for dist in best:
                if (realpath(os.path.dirname(dist.location))
                    ==
                    self._download_cache
                    ):
                    return dist

        best.sort()
        return best[-1]

    def _fetch(self, dist, tmp, download_cache):
        if (download_cache
            and (realpath(os.path.dirname(dist.location)) == download_cache)
            ):
            return dist

        new_location = self._index.download(dist.location, tmp)
        if (download_cache
            and (realpath(new_location) == realpath(dist.location))
            and os.path.isfile(new_location)
            ):
            # setuptools avoids making extra copies, but we want to copy
            # to the download cache
            shutil.copy2(new_location, tmp)
            new_location = os.path.join(tmp, os.path.basename(new_location))

        return dist.clone(location=new_location)

    def _get_dist(self, requirement, ws, always_unzip):

        __doing__ = 'Getting distribution for %r.', str(requirement)

        # Maybe an existing dist is already the best dist that satisfies the
        # requirement
        dist, avail = self._satisfied(requirement)

        if dist is None:
            if self._dest is not None:
                logger.info(*__doing__)

            # Retrieve the dist:
            if avail is None:
                raise MissingDistribution(requirement, ws)

            # We may overwrite distributions, so clear importer
            # cache.
            sys.path_importer_cache.clear()

            tmp = self._download_cache
            if tmp is None:
                tmp = tempfile.mkdtemp('get_dist')

            try:
                dist = self._fetch(avail, tmp, self._download_cache)

                if dist is None:
                    raise zc.buildout.UserError(
                        "Couln't download distribution %s." % avail)

                if dist.precedence == pkg_resources.EGG_DIST:
                    # It's already an egg, just fetch it into the dest

                    newloc = os.path.join(
                        self._dest, os.path.basename(dist.location))

                    if os.path.isdir(dist.location):
                        # we got a directory. It must have been
                        # obtained locally.  Just copy it.
                        shutil.copytree(dist.location, newloc)
                    else:

                        if self._always_unzip:
                            should_unzip = True
                        else:
                            metadata = pkg_resources.EggMetadata(
                                zipimport.zipimporter(dist.location)
                                )
                            should_unzip = (
                                metadata.has_metadata('not-zip-safe')
                                or
                                not metadata.has_metadata('zip-safe')
                                )

                        if should_unzip:
                            setuptools.archive_util.unpack_archive(
                                dist.location, newloc)
                        else:
                            shutil.copyfile(dist.location, newloc)

                    redo_pyc(newloc)

                    # Getting the dist from the environment causes the
                    # distribution meta data to be read.  Cloning isn't
                    # good enough.
                    dists = pkg_resources.Environment(
                        [newloc],
                        python=_get_version(self._executable),
                        )[dist.project_name]
                else:
                    # It's some other kind of dist.  We'll let easy_install
                    # deal with it:
                    dists = self._call_easy_install(
                        dist.location, ws, self._dest, dist)
                    for dist in dists:
                        redo_pyc(dist.location)

            finally:
                if tmp != self._download_cache:
                    shutil.rmtree(tmp)

            self._env.scan([self._dest])
            dist = self._env.best_match(requirement, ws)
            logger.info("Got %s.", dist)

        else:
            dists = [dist]

        for dist in dists:
            if (dist.has_metadata('dependency_links.txt')
                and not self._install_from_cache
                and self._use_dependency_links
                ):
                for link in dist.get_metadata_lines('dependency_links.txt'):
                    link = link.strip()
                    if link not in self._links:
                        logger.debug('Adding find link %r from %s', link, dist)
                        self._links.append(link)
                        self._index = _get_index(self._executable,
                                                 self._index_url, self._links,
                                                 self._allow_hosts, self._path)

        for dist in dists:
            # Check whether we picked a version and, if we did, report it:
            if not (
                dist.precedence == pkg_resources.DEVELOP_DIST
                or
                (len(requirement.specs) == 1
                 and
                 requirement.specs[0][0] == '==')
                ):
                logger.debug('Picked: %s = %s',
                             dist.project_name, dist.version)
                if not self._allow_picked_versions:
                    raise zc.buildout.UserError(
                        'Picked: %s = %s' % (dist.project_name, dist.version)
                        )

        return dists

    def _maybe_add_setuptools(self, ws, dist):
        if dist.has_metadata('namespace_packages.txt'):
            for r in dist.requires():
                if r.project_name == 'setuptools':
                    break
            else:
                # We have a namespace package but no requirement for setuptools
                if dist.precedence == pkg_resources.DEVELOP_DIST:
                    logger.warn(
                        "Develop distribution: %s\n"
                        "uses namespace packages but the distribution "
                        "does not require setuptools.",
                        dist)
                requirement = self._constrain(
                    pkg_resources.Requirement.parse('setuptools')
                    )
                if ws.find(requirement) is None:
                    for dist in self._get_dist(requirement, ws, False):
                        ws.add(dist)


    def _constrain(self, requirement):
        version = self._versions.get(requirement.project_name)
        if version:
            if version not in requirement:
                logger.error("The version, %s, is not consistent with the "
                             "requirement, %r.", version, str(requirement))
                raise IncompatibleVersionError("Bad version", version)

            requirement = pkg_resources.Requirement.parse(
                "%s ==%s" % (requirement.project_name, version))

        return requirement

    def install(self, specs, working_set=None):

        logger.debug('Installing %s.', repr(specs)[1:-1])

        path = self._path
        destination = self._dest
        if destination is not None and destination not in path:
            path.insert(0, destination)

        requirements = [self._constrain(pkg_resources.Requirement.parse(spec))
                        for spec in specs]



        if working_set is None:
            ws = pkg_resources.WorkingSet([])
        else:
            ws = working_set

        for requirement in requirements:
            for dist in self._get_dist(requirement, ws, self._always_unzip):
                ws.add(dist)
                self._maybe_add_setuptools(ws, dist)

        # OK, we have the requested distributions and they're in the working
        # set, but they may have unmet requirements.  We'll resolve these
        # requirements. This is code modified from
        # pkg_resources.WorkingSet.resolve.  We can't reuse that code directly
        # because we have to constrain our requirements (see
        # versions_section_ignored_for_dependency_in_favor_of_site_packages in
        # zc.buildout.tests).
        #
        requirements.reverse() # Set up the stack.
        processed = {}  # This is a set of processed requirements.
        best = {}  # This is a mapping of key -> dist.
        #
        # Note that we don't use the existing environment, because we want
        # to look for new eggs unless what we have is the best that
        # matches the requirement.
        env = pkg_resources.Environment(ws.entries)
        while requirements:
            # Process dependencies breadth-first.
            req = self._constrain(requirements.pop(0))
            if req in processed:
                # Ignore cyclic or redundant dependencies.
                continue
            dist = best.get(req.key)
            if dist is None:
                # Find the best distribution and add it to the map.
                dist = ws.by_key.get(req.key)
                if dist is None:
                    try:
                        dist = best[req.key] = env.best_match(req, ws)
                    except pkg_resources.VersionConflict, err:
                        raise VersionConflict(err, ws)
                    if dist is None:
                        if destination:
                            logger.debug('Getting required %r', str(req))
                        else:
                            logger.debug('Adding required %r', str(req))
                        _log_requirement(ws, req)
                        for dist in self._get_dist(req,
                                                   ws, self._always_unzip):
                            ws.add(dist)
                            self._maybe_add_setuptools(ws, dist)
            if dist not in req:
                # Oops, the "best" so far conflicts with a dependency.
                raise VersionConflict(
                    pkg_resources.VersionConflict(dist, req), ws)
            requirements.extend(dist.requires(req.extras)[::-1])
            processed[req] = True
            if dist.location in self._site_packages:
                logger.debug('Egg from site-packages: %s', dist)

        return ws

    def build(self, spec, build_ext):

        requirement = self._constrain(pkg_resources.Requirement.parse(spec))

        dist, avail = self._satisfied(requirement, 1)
        if dist is not None:
            return [dist.location]

        # Retrieve the dist:
        if avail is None:
            raise zc.buildout.UserError(
                "Couldn't find a source distribution for %r."
                % str(requirement))

        logger.debug('Building %r', spec)

        tmp = self._download_cache
        if tmp is None:
            tmp = tempfile.mkdtemp('get_dist')

        try:
            dist = self._fetch(avail, tmp, self._download_cache)

            build_tmp = tempfile.mkdtemp('build')
            try:
                setuptools.archive_util.unpack_archive(dist.location,
                                                       build_tmp)
                if os.path.exists(os.path.join(build_tmp, 'setup.py')):
                    base = build_tmp
                else:
                    setups = glob.glob(
                        os.path.join(build_tmp, '*', 'setup.py'))
                    if not setups:
                        raise distutils.errors.DistutilsError(
                            "Couldn't find a setup script in %s"
                            % os.path.basename(dist.location)
                            )
                    if len(setups) > 1:
                        raise distutils.errors.DistutilsError(
                            "Multiple setup scripts in %s"
                            % os.path.basename(dist.location)
                            )
                    base = os.path.dirname(setups[0])

                setup_cfg = os.path.join(base, 'setup.cfg')
                if not os.path.exists(setup_cfg):
                    f = open(setup_cfg, 'w')
                    f.close()
                setuptools.command.setopt.edit_config(
                    setup_cfg, dict(build_ext=build_ext))

                dists = self._call_easy_install(
                    base, pkg_resources.WorkingSet(),
                    self._dest, dist)

                for dist in dists:
                    redo_pyc(dist.location)

                return [dist.location for dist in dists]
            finally:
                shutil.rmtree(build_tmp)

        finally:
            if tmp != self._download_cache:
                shutil.rmtree(tmp)

def default_versions(versions=None):
    old = Installer._versions
    if versions is not None:
        Installer._versions = versions
    return old

def download_cache(path=-1):
    old = Installer._download_cache
    if path != -1:
        if path:
            path = realpath(path)
        Installer._download_cache = path
    return old

def install_from_cache(setting=None):
    old = Installer._install_from_cache
    if setting is not None:
        Installer._install_from_cache = bool(setting)
    return old

def prefer_final(setting=None):
    old = Installer._prefer_final
    if setting is not None:
        Installer._prefer_final = bool(setting)
    return old

def include_site_packages(setting=None):
    old = Installer._include_site_packages
    if setting is not None:
        Installer._include_site_packages = bool(setting)
    return old

def allowed_eggs_from_site_packages(setting=None):
    old = Installer._allowed_eggs_from_site_packages
    if setting is not None:
        Installer._allowed_eggs_from_site_packages = tuple(setting)
    return old

def use_dependency_links(setting=None):
    old = Installer._use_dependency_links
    if setting is not None:
        Installer._use_dependency_links = bool(setting)
    return old

def allow_picked_versions(setting=None):
    old = Installer._allow_picked_versions
    if setting is not None:
        Installer._allow_picked_versions = bool(setting)
    return old

def always_unzip(setting=None):
    old = Installer._always_unzip
    if setting is not None:
        Installer._always_unzip = bool(setting)
    return old

def install(specs, dest,
            links=(), index=None,
            executable=sys.executable, always_unzip=None,
            path=None, working_set=None, newest=True, versions=None,
            use_dependency_links=None, include_site_packages=None,
            allowed_eggs_from_site_packages=None, allow_hosts=('*',)):
    installer = Installer(dest, links, index, executable, always_unzip, path,
                          newest, versions, use_dependency_links,
                          include_site_packages,
                          allowed_eggs_from_site_packages,
                          allow_hosts=allow_hosts)
    return installer.install(specs, working_set)


def build(spec, dest, build_ext,
          links=(), index=None,
          executable=sys.executable,
          path=None, newest=True, versions=None, include_site_packages=None,
          allowed_eggs_from_site_packages=None, allow_hosts=('*',)):
    installer = Installer(dest, links, index, executable, True, path, newest,
                          versions, include_site_packages,
                          allowed_eggs_from_site_packages,
                          allow_hosts=allow_hosts)
    return installer.build(spec, build_ext)



def _rm(*paths):
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)

def _copyeggs(src, dest, suffix, undo):
    result = []
    undo.append(lambda : _rm(*result))
    for name in os.listdir(src):
        if name.endswith(suffix):
            new = os.path.join(dest, name)
            _rm(new)
            os.rename(os.path.join(src, name), new)
            result.append(new)

    assert len(result) == 1, str(result)
    undo.pop()

    return result[0]

def develop(setup, dest,
            build_ext=None,
            executable=sys.executable):

    if os.path.isdir(setup):
        directory = setup
        setup = os.path.join(directory, 'setup.py')
    else:
        directory = os.path.dirname(setup)

    undo = []
    try:
        if build_ext:
            setup_cfg = os.path.join(directory, 'setup.cfg')
            if os.path.exists(setup_cfg):
                os.rename(setup_cfg, setup_cfg+'-develop-aside')
                def restore_old_setup():
                    if os.path.exists(setup_cfg):
                        os.remove(setup_cfg)
                    os.rename(setup_cfg+'-develop-aside', setup_cfg)
                undo.append(restore_old_setup)
            else:
                open(setup_cfg, 'w')
                undo.append(lambda: os.remove(setup_cfg))
            setuptools.command.setopt.edit_config(
                setup_cfg, dict(build_ext=build_ext))

        fd, tsetup = tempfile.mkstemp()
        undo.append(lambda: os.remove(tsetup))
        undo.append(lambda: os.close(fd))

        os.write(fd, runsetup_template % dict(
            sys_path=',\n    '.join(repr(p) for p in sys.path),
            setupdir=directory,
            setup=setup,
            __file__ = setup,
            ))

        tmp3 = tempfile.mkdtemp('build', dir=dest)
        undo.append(lambda : shutil.rmtree(tmp3))

        args = [
            zc.buildout.easy_install._safe_arg(tsetup),
            '-q', 'develop', '-mxN',
            '-d', _safe_arg(tmp3),
            ]

        log_level = logger.getEffectiveLevel()
        if log_level <= 0:
            if log_level == 0:
                del args[1]
            else:
                args[1] == '-v'
        if log_level < logging.DEBUG:
            logger.debug("in: %r\n%s", directory, ' '.join(args))

        if is_jython:
            assert subprocess.Popen([_safe_arg(executable)] + args).wait() == 0
        else:
            assert os.spawnl(os.P_WAIT, executable, _safe_arg(executable),
                             *args) == 0

        return _copyeggs(tmp3, dest, '.egg-link', undo)

    finally:
        undo.reverse()
        [f() for f in undo]


def working_set(specs, executable, path, include_site_packages=None,
                allowed_eggs_from_site_packages=None):
    return install(
        specs, None, executable=executable, path=path,
        include_site_packages=include_site_packages,
        allowed_eggs_from_site_packages=allowed_eggs_from_site_packages)

def get_path(working_set, executable, extra_paths=(),
             include_site_packages=True):
    """Given working set and path to executable, return value for sys.path.

    Distribution locations from the working set come first in the list.  Within
    that collection, this function pushes site-packages-based distribution
    locations to the end of the list, so that they don't mask eggs.

    This expects that the working_set has already been created to honor a
    include_site_packages setting.  That is, if include_site_packages is False,
    this function does *not* verify that the working_set's distributions are
    not in site packages.

    However, it does explicitly include site packages if include_site_packages
    is True.

    The standard library (defined as what the given Python executable has on
    the path before its site.py is run) is always included.
    """
    stdlib, site_packages = _get_system_packages(executable)
    postponed = []
    path = []
    for dist in working_set:
        location = os.path.normpath(dist.location)
        if location in path:
            path.remove(location)
            postponed.append(location)
        elif location in site_packages:
            postponed.append(location)
            site_packages.remove(location)
        elif location not in postponed:
            path.append(location)
    path.extend(postponed)
    path.extend(extra_paths)
    # now we add in all paths
    if include_site_packages:
        path.extend(site_packages) # these are the remaining site_packages
    path.extend(stdlib)
    path = map(realpath, path)
    return path

def scripts(reqs, working_set, executable, dest,
            scripts=None,
            extra_paths=(),
            arguments='',
            interpreter=None,
            initialization='',
            include_site_packages=True,
            relative_paths=False
            ):
    path = get_path(
        working_set, executable, extra_paths, include_site_packages)
    generated = []

    if isinstance(reqs, str):
        raise TypeError('Expected iterable of requirements or entry points,'
                        ' got string.')

    if initialization:
        initialization = '\n'+initialization+'\n'

    entry_points = []
    for req in reqs:
        if isinstance(req, str):
            req = pkg_resources.Requirement.parse(req)
            dist = working_set.find(req)
            for name in pkg_resources.get_entry_map(dist, 'console_scripts'):
                entry_point = dist.get_entry_info('console_scripts', name)
                entry_points.append(
                    (name, entry_point.module_name,
                     '.'.join(entry_point.attrs))
                    )
        else:
            entry_points.append(req)

    for name, module_name, attrs in entry_points:
        if scripts is not None:
            sname = scripts.get(name)
            if sname is None:
                continue
        else:
            sname = name

        sname = os.path.join(dest, sname)
        spath, rpsetup = _relative_path_and_setup(sname, path, relative_paths)

        generated.extend(
            _script(module_name, attrs, spath, sname, executable, arguments,
                    initialization, rpsetup)
            )

    if interpreter:
        sname = os.path.join(dest, interpreter)
        spath, rpsetup = _relative_path_and_setup(sname, path, relative_paths)
        generated.extend(_pyscript(spath, sname, executable, rpsetup))

    return generated

def _relative_path_and_setup(sname, path, relative_paths):
    if relative_paths:
        relative_paths = os.path.normcase(relative_paths)
        sname = os.path.normcase(os.path.abspath(sname))
        spath = ',\n    '.join(
            [_relativitize(os.path.normcase(path_item), sname, relative_paths)
             for path_item in path]
            )
        rpsetup = relative_paths_setup
        for i in range(_relative_depth(relative_paths, sname)):
            rpsetup += "base = os.path.dirname(base)\n"
    else:
        spath = repr(path)[1:-1].replace(', ', ',\n    ')
        rpsetup = ''
    return spath, rpsetup


def _relative_depth(common, path):
    n = 0
    while 1:
        dirname = os.path.dirname(path)
        if dirname == path:
            raise AssertionError("dirname of %s is the same" % dirname)
        if dirname == common:
            break
        n += 1
        path = dirname
    return n

def _relative_path(common, path):
    r = []
    while 1:
        dirname, basename = os.path.split(path)
        r.append(basename)
        if dirname == common:
            break
        if dirname == path:
            raise AssertionError("dirname of %s is the same" % dirname)
        path = dirname
    r.reverse()
    return os.path.join(*r)

def _relativitize(path, script, relative_paths):
    if path == script:
        raise AssertionError("path == script")
    common = os.path.dirname(os.path.commonprefix([path, script]))
    if (common == relative_paths or
        common.startswith(os.path.join(relative_paths, ''))
        ):
        return "join(base, %r)" % _relative_path(common, path)
    else:
        return repr(path)


relative_paths_setup = """
import os

join = os.path.join
base = os.path.dirname(os.path.abspath(__file__))
"""

def _script(module_name, attrs, path, dest, executable, arguments,
            initialization, rsetup):
    generated = []
    script = dest
    if is_win32:
        dest += '-script.py'

    contents = script_template % dict(
        python = _safe_arg(executable),
        path = path,
        module_name = module_name,
        attrs = attrs,
        arguments = arguments,
        initialization = initialization,
        relative_paths_setup = rsetup,
        )
    changed = not (os.path.exists(dest) and open(dest).read() == contents)

    if is_win32:
        # generate exe file and give the script a magic name:
        exe = script+'.exe'
        new_data = pkg_resources.resource_string('setuptools', 'cli.exe')
        if not os.path.exists(exe) or (open(exe, 'rb').read() != new_data):
            # Only write it if it's different.
            open(exe, 'wb').write(new_data)
        generated.append(exe)

    if changed:
        open(dest, 'w').write(contents)
        logger.info("Generated script %r.", script)

        try:
            os.chmod(dest, 0755)
        except (AttributeError, os.error):
            pass

    generated.append(dest)
    return generated

if is_jython and jython_os_name == 'linux':
    script_header = '#!/usr/bin/env %(python)s'
else:
    script_header = '#!%(python)s'


script_template = script_header + '''\

%(relative_paths_setup)s
import sys
sys.path[:] = [
    %(path)s,
    ]
%(initialization)s
import %(module_name)s

if __name__ == '__main__':
    %(module_name)s.%(attrs)s(%(arguments)s)
'''


def _pyscript(path, dest, executable, rsetup):
    generated = []
    script = dest
    if is_win32:
        dest += '-script.py'

    contents = py_script_template % dict(
        python = _safe_arg(executable),
        path = path,
        relative_paths_setup = rsetup,
        )
    changed = not (os.path.exists(dest) and open(dest).read() == contents)

    if is_win32:
        # generate exe file and give the script a magic name:
        exe = script + '.exe'
        open(exe, 'wb').write(
            pkg_resources.resource_string('setuptools', 'cli.exe')
            )
        generated.append(exe)

    if changed:
        open(dest, 'w').write(contents)
        try:
            os.chmod(dest,0755)
        except (AttributeError, os.error):
            pass
        logger.info("Generated interpreter %r.", script)

    generated.append(dest)
    return generated

py_script_template = script_header + '''\

globs = globals().copy() # get a clean copy early

%(relative_paths_setup)s
import sys

_set_path = _interactive = True
_force_interactive = False

_command = None
_args = sys.argv[1:]

while _args:
    if _args[0].startswith('-'):
        _arg = _args.pop(0)
        for _ix, _opt in enumerate(_arg[1:]):
            if _opt == 'i':
                _force_interactive = True
            elif _opt == 'c':
                _interactive = False
                _command = _args.pop(0) # Argument expected for the -c option
                _args.insert(0, '-c')
                break
            elif _opt == 'S':
                # We'll approximate this.  It is mostly convenient for tests.
                _set_path = False
            elif _opt == 'V':
                print 'Python ' + sys.version.split()[0]
                _interactive = False
                break
        else:
            continue
        break
    else:
        break

if _set_path:
    sys.path[:] = [
    %(path)s,
    ]
sys.path.insert(0, '.')

sys.argv[:] = _args

if _command:
    exec _command
elif _args:
    _interactive = False
    globs['__file__'] = sys.argv[0]
    execfile(sys.argv[0], globs)

if _interactive or _force_interactive:
    import code
    del globs['__file__']
    code.interact(banner="", local=globs)
'''

runsetup_template = """
import sys
sys.path[:] = [
    %(setupdir)r,
    %(sys_path)s
    ]
import os, setuptools

__file__ = %(__file__)r

os.chdir(%(setupdir)r)
sys.argv[0] = %(setup)r
execfile(%(setup)r)
"""

class VersionConflict(zc.buildout.UserError):

    def __init__(self, err, ws):
        ws = list(ws)
        ws.sort()
        self.err, self.ws = err, ws

    def __str__(self):
        existing_dist, req = self.err
        result = ["There is a version conflict.",
                  "We already have: %s" % existing_dist,
                  ]
        for dist in self.ws:
            if req in dist.requires():
                result.append("but %s requires %r." % (dist, str(req)))
        return '\n'.join(result)

class MissingDistribution(zc.buildout.UserError):

    def __init__(self, req, ws):
        ws = list(ws)
        ws.sort()
        self.data = req, ws

    def __str__(self):
        req, ws = self.data
        return "Couldn't find a distribution for %r." % str(req)

def _log_requirement(ws, req):
    ws = list(ws)
    ws.sort()
    for dist in ws:
        if req in dist.requires():
            logger.debug("  required by %s." % dist)

def _fix_file_links(links):
    for link in links:
        if link.startswith('file://') and link[-1] != '/':
            if os.path.isdir(link[7:]):
                # work around excessive restriction in setuptools:
                link += '/'
        yield link

_final_parts = '*final-', '*final'
def _final_version(parsed_version):
    for part in parsed_version:
        if (part[:1] == '*') and (part not in _final_parts):
            return False
    return True

def redo_pyc(egg):
    if not os.path.isdir(egg):
        return
    for dirpath, dirnames, filenames in os.walk(egg):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(dirpath, filename)
            if not (os.path.exists(filepath+'c')
                    or os.path.exists(filepath+'o')):
                # If it wasn't compiled, it may not be compilable
                continue

            # OK, it looks like we should try to compile.

            # Remove old files.
            for suffix in 'co':
                if os.path.exists(filepath+suffix):
                    os.remove(filepath+suffix)

            # Compile under current optimization
            try:
                py_compile.compile(filepath)
            except py_compile.PyCompileError:
                logger.warning("Couldn't compile %s", filepath)
            else:
                # Recompile under other optimization. :)
                args = [_safe_arg(sys.executable)]
                if __debug__:
                    args.append('-O')
                args.extend(['-m', 'py_compile', _safe_arg(filepath)])

                if is_jython:
                    subprocess.call([sys.executable, args])
                else:
                    os.spawnv(os.P_WAIT, sys.executable, args)
