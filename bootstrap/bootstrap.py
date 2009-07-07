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
"""Bootstrap a buildout-based project

Simply run this script in a directory containing a buildout.cfg.
The script accepts buildout command-line options, so you can
use the -c option to specify an alternate configuration file.

$Id$
"""

import os, re, shutil, sys, tempfile, textwrap, urllib, urllib2

# We have to manually parse our options rather than using one of the stdlib
# tools because we want to pass the ones we don't recognize along to
# zc.buildout.buildout.main.

configuration = {
    '--ez_setup-source': 'http://peak.telecommunity.com/dist/ez_setup.py',
    '--version': '',
    '--download-base': None,
    '--eggs': None}

helpstring = __doc__ + textwrap.dedent('''
    Options: 
      --version=ZC_BUILDOUT_VERSION
                Specify a version number of the zc.buildout to use
      --ez_setup-source=URL_OR_FILE
                Specify a URL or file location for the ez_setup file.
                Defaults to
                %(--ez_setup-source)s
      --download-base=URL_OR_DIRECTORY
                Specify a URL or directory for downloading setuptools and
                zc.buildout.  Defaults to PyPI.
      --eggs=DIRECTORY
                Specify a directory for storing eggs.  Defaults to a temporary
                directory that is deleted when the bootstrap script completes.

    By using --ez_setup-source and --download-base to point to local resources,
    you can keep bootstrap from going over the network.
    ''')
match_equals = re.compile(r'(%s)=(\S*)' % ('|'.join(configuration),)).match
args = sys.argv[1:]
if args == ['--help']:
    print helpstring
    sys.exit(0)

# defaults
tmpeggs = None

while args:
    val = args[0]
    if val in configuration:
        del args[0]
        if not args or args[0].startswith('-'):
            print "ERROR: %s requires an argument."
            print helpstring
            sys.exit(1)
        configuration[val] = args[0]
    else:
        match = match_equals(val)
        if match and match.group(1) in configuration:
            configuration[match.group(1)] = match.group(2)
        else:
            break
    del args[0]

for name in ('--ez_setup-source', '--download-base'):
    val = configuration[name]
    if val is not None and '://' not in val: # we're being lazy.
        configuration[name] = 'file://%s' % (
            urllib.pathname2url(os.path.abspath(os.path.expanduser(val))),)

if not configuration['--eggs']:
    configuration['--eggs'] = tmpeggs = tempfile.mkdtemp()
else:
    configuration['--eggs'] = os.path.abspath(
        os.path.expanduser(configuration['--eggs']))

if configuration['--version']:
    configuration['--version'] = '==' + configuration['--version']

try:
    import pkg_resources
except ImportError:
    ez = {}
    exec urllib2.urlopen(configuration['--ez_setup-source']).read() in ez
    setuptools_args = dict(to_dir=configuration['--eggs'], download_delay=0)
    if configuration['--download-base']:
        setuptools_args['download_base'] = (
            configuration['--download-base'] + '/')
    ez['use_setuptools'](**setuptools_args)

    import pkg_resources

if sys.platform == 'win32':
    def quote(c):
        if ' ' in c:
            return '"%s"' % c # work around spawn lamosity on windows
        else:
            return c
else:
    def quote (c):
        return c
cmd = [quote(sys.executable),
       '-c',
       quote('from setuptools.command.easy_install import main; main()'),
       '-mqNxd',
       quote(configuration['--eggs']),
       'zc.buildout' + configuration['--version']]
ws = pkg_resources.working_set
env = dict(
    os.environ,
    PYTHONPATH=ws.find(pkg_resources.Requirement.parse('setuptools')).location)

try:
    import subprocess
except ImportError:
    exitcode = os.spawnle(*([os.P_WAIT, sys.executable] + cmd + [env]))
else:
    # Jython can use subprocess but not spawn.  We prefer it generally.
    exitcode = subprocess.Popen(cmd, env=env).wait()
if exitcode != 0:
    # we shouldn't need an error message because a failure
    # should have generated a visible traceback in the subprocess.
    sys.exit(exitcode)

ws.add_entry(configuration['--eggs'])
ws.require('zc.buildout' + configuration['--version'])
import zc.buildout.buildout
args.append('bootstrap')
zc.buildout.buildout.main(args)
if tmpeggs is not None:
    shutil.rmtree(tmpeggs)
