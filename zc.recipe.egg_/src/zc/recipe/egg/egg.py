##############################################################################
#
# Copyright (c) 2006 Zope Corporation and Contributors.
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
"""Install packages as eggs

$Id$
"""

import logging, os, re, zipfile
import zc.buildout.easy_install


class Eggs(object):

    def __init__(self, buildout, name, options):
        self.buildout = buildout
        self.name = name
        self.options = options
        b_options = buildout['buildout']
        links = options.get('find-links', b_options['find-links'])
        if links:
            links = links.split()
            options['find-links'] = '\n'.join(links)
        else:
            links = ()
        self.links = links

        index = options.get('index', b_options.get('index'))
        if index is not None:
            options['index'] = index
        self.index = index

        allow_hosts = b_options['allow-hosts']
        allow_hosts = tuple([host.strip() for host in allow_hosts.split('\n')
                               if host.strip()!=''])
        self.allow_hosts = allow_hosts

        options['eggs-directory'] = b_options['eggs-directory']
        options['_e'] = options['eggs-directory'] # backward compat.
        options['develop-eggs-directory'] = b_options['develop-eggs-directory']
        options['_d'] = options['develop-eggs-directory'] # backward compat.

        # verify that this is None, 'true' or 'false'
        get_bool(options, 'unzip')

        python = options.setdefault('python', b_options['python'])
        options['executable'] = buildout[python]['executable']

    def working_set(self, extra=()):
        """Separate method to just get the working set

        This is intended for reuse by similar recipes.
        """
        options = self.options
        b_options = self.buildout['buildout']

        distributions = [
            r.strip()
            for r in options.get('eggs', self.name).split('\n')
            if r.strip()]
        orig_distributions = distributions[:]
        distributions.extend(extra)

        if b_options.get('offline') == 'true':
            ws = zc.buildout.easy_install.working_set(
                distributions, options['executable'],
                [options['develop-eggs-directory'],
                 options['eggs-directory']],
                )
        else:
            kw = {}
            if 'unzip' in options:
                kw['always_unzip'] = get_bool(options, 'unzip')
            ws = zc.buildout.easy_install.install(
                distributions, options['eggs-directory'],
                links=self.links,
                index=self.index,
                executable=options['executable'],
                path=[options['develop-eggs-directory']],
                newest=b_options.get('newest') == 'true',
                allow_hosts=self.allow_hosts,
                **kw)

        return orig_distributions, ws

    def install(self):
        reqs, ws = self.working_set()
        return ()

    update = install


class ScriptBase(Eggs):

    def __init__(self, buildout, name, options):
        super(ScriptBase, self).__init__(buildout, name, options)

        b_options = buildout['buildout']

        options['bin-directory'] = b_options['bin-directory']
        options['_b'] = options['bin-directory'] # backward compat.

        self.extra_paths = [
            os.path.join(b_options['directory'], p.strip())
            for p in options.get('extra-paths', '').split('\n')
            if p.strip()
            ]
        if self.extra_paths:
            options['extra-paths'] = '\n'.join(self.extra_paths)


        relative_paths = options.get(
            'relative-paths', b_options.get('relative-paths', 'false'))
        if relative_paths == 'true':
            options['buildout-directory'] = b_options['directory']
            self._relative_paths = options['buildout-directory']
        else:
            self._relative_paths = ''
            assert relative_paths == 'false'

        value = options.setdefault(
            'include-site-packages',
            b_options.get('include-site-packages', 'false'))
        if value not in ('true', 'false'):
            raise zc.buildout.UserError(
                "Invalid value for include-site-packages option: %s" %
                (value,))
        self.include_site_packages = (value == 'true')


class Scripts(ScriptBase):

    parse_entry_point = re.compile(
        '([^=]+)=(\w+(?:[.]\w+)*):(\w+(?:[.]\w+)*)$'
        ).match
    def install(self):
        reqs, ws = self.working_set()
        options = self.options

        scripts = options.get('scripts')
        if scripts or scripts is None:
            if scripts is not None:
                scripts = scripts.split()
                scripts = dict([
                    ('=' in s) and s.split('=', 1) or (s, s)
                    for s in scripts
                    ])

            for s in options.get('entry-points', '').split():
                parsed = self.parse_entry_point(s)
                if not parsed:
                    logging.getLogger(self.name).error(
                        "Cannot parse the entry point %s.", s)
                    raise zc.buildout.UserError("Invalid entry point")
                reqs.append(parsed.groups())

            if get_bool(options, 'dependent-scripts'):
                # Generate scripts for all packages in the working set,
                # except setuptools.
                reqs = list(reqs)
                for dist in ws:
                    name = dist.project_name
                    if name != 'setuptools' and name not in reqs:
                        reqs.append(name)

            return zc.buildout.easy_install.scripts(
                reqs, ws, options['executable'],
                options['bin-directory'],
                scripts=scripts,
                extra_paths=self.extra_paths,
                interpreter=options.get('interpreter'),
                initialization=options.get('initialization', ''),
                arguments=options.get('arguments', ''),
                relative_paths=self._relative_paths,
                import_site=self.include_site_packages,
                )

        return ()

    update = install


class Interpreter(ScriptBase):

    def __init__(self, buildout, name, options):
        if 'extends' in options:
            options.update(buildout[options['extends']])
        super(Interpreter, self).__init__(buildout, name, options)
        b_options = buildout['buildout']
        options['parts-directory'] = os.path.join(
            b_options['parts-directory'], self.name)

        value = options.setdefault(
            'include-site-customization',
            b_options.get('include-site-customization', 'false'))
        if value not in ('true', 'false'):
            raise zc.buildout.UserError(
                "Invalid value for include-site-customization option: %s" %
                (value,))
        self.include_site_customization = (value == 'true')

        options.setdefault('name', name)

    def install(self):
        reqs, ws = self.working_set()
        options = self.options
        if not os.path.exists(options['parts-directory']):
            os.mkdir(options['parts-directory'])
            dir_made = True
        else:
            dir_made = False
        generated = zc.buildout.easy_install.interpreter(
            options['name'], ws, options['executable'],
            options['bin-directory'], options['parts-directory'],
            extra_paths=self.extra_paths,
            initialization=options.get('initialization', ''),
            relative_paths=self._relative_paths,
            import_site=self.include_site_packages,
            import_sitecustomize=self.include_site_customization,
            )
        if dir_made:
            generated.append(options['parts-directory'])
        return generated


def get_bool(options, name, default=False):
    value = options.get(name)
    if not value:
        return default
    if value == 'true':
        return True
    elif value == 'false':
        return False
    else:
        raise zc.buildout.UserError(
            "Invalid value for %s option: %s" % (name, value))

Egg = Scripts
