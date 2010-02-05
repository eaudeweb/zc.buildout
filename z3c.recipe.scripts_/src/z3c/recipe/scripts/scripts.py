##############################################################################
#
# Copyright (c) 2009-2010 Zope Corporation and Contributors.
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
"""Install scripts from eggs.
"""
import os
import zc.buildout
import zc.buildout.easy_install
from zc.recipe.egg.egg import ScriptBase


class Base(ScriptBase):

    def __init__(self, buildout, name, options):
        if 'extends' in options:
            options.update(buildout[options['extends']])
        super(Base, self).__init__(buildout, name, options)
        self.default_eggs = '' # Disables feature from zc.recipe.egg.
        b_options = buildout['buildout']
        options['parts-directory'] = os.path.join(
            b_options['parts-directory'], self.name)

        value = options.setdefault(
            'add-site-packages',
            b_options.get('add-site-packages', 'false'))
        if value not in ('true', 'false'):
            raise zc.buildout.UserError(
                "Invalid value for add-site-packages option: %s" %
                (value,))
        self.add_site_packages = (value == 'true')

        value = options.setdefault(
            'exec-sitecustomize',
            b_options.get('exec-sitecustomize', 'false'))
        if value not in ('true', 'false'):
            raise zc.buildout.UserError(
                "Invalid value for exec-sitecustomize option: %s" %
                (value,))
        self.exec_sitecustomize = (value == 'true')


class Interpreter(Base):

    def __init__(self, buildout, name, options):
        super(Interpreter, self).__init__(buildout, name, options)

        options.setdefault('name', name)

    def install(self):
        reqs, ws = self.working_set()
        options = self.options
        generated = []
        if not os.path.exists(options['parts-directory']):
            os.mkdir(options['parts-directory'])
            generated.append(options['parts-directory'])
        generated.extend(zc.buildout.easy_install.generate_scripts(
            options['bin-directory'], ws, options['executable'],
            options['parts-directory'],
            interpreter=options['name'],
            extra_paths=self.extra_paths,
            initialization=options.get('initialization', ''),
            add_site_packages=self.add_site_packages,
            exec_sitecustomize=self.exec_sitecustomize,
            relative_paths=self._relative_paths,
            ))
        return generated

    update = install


class Scripts(Base):

    def _install(self, reqs, ws, scripts):
        options = self.options
        generated = []
        if not os.path.exists(options['parts-directory']):
            os.mkdir(options['parts-directory'])
            generated.append(options['parts-directory'])
        generated.extend(zc.buildout.easy_install.generate_scripts(
            options['bin-directory'], ws, options['executable'],
            options['parts-directory'], reqs=reqs, scripts=scripts,
            interpreter=options.get('interpreter'),
            extra_paths=self.extra_paths,
            initialization=options.get('initialization', ''),
            add_site_packages=self.add_site_packages,
            exec_sitecustomize=self.exec_sitecustomize,
            relative_paths=self._relative_paths,
            script_arguments=options.get('arguments', ''),
            script_initialization=options.get('script-initialization', '')
            ))
        return generated