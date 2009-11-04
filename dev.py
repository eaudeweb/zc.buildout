##############################################################################
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
"""Bootstrap the buildout project itself.

This is different from a normal boostrapping process because the
buildout egg itself is installed as a develop egg.

$Id$
"""

import os, shutil, sys, subprocess
from optparse import OptionParser

try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen


def execute(source, globals=None, locals=None, filename="<string>"):
    code = compile(source, filename, "exec")
    if globals is None:
        globals = {}
    if locals is None:
        locals = globals
    if sys.version_info[0] == 2:
        run = compile("exec code in globals, locals ", "<string>", "exec")
        exec(run)
    else:
        exec(code, globals, locals)


is_jython = sys.platform.startswith('java')

# parsing arguments
parser = OptionParser()
parser.add_option("-d", "--distribute",
                   action="store_true", dest="distribute", default=False,
                   help="Use Disribute rather than Setuptools.")

parser.add_option("-c", None, action="store", dest="config_file",
                   help=("Specify the path to the buildout configuration "
                         "file to be used."))

options, args = parser.parse_args()
USE_DISTRIBUTE = options.distribute

# if -c was provided, we push it back into args for buildout' main function
if options.config_file is not None:
    args += ['-c', options.config_file]

for d in 'eggs', 'develop-eggs', 'bin':
    if not os.path.exists(d):
        os.mkdir(d)

if os.path.isdir('build'):
    shutil.rmtree('build')

to_reload = False
try:
    import pkg_resources
    if not hasattr(pkg_resources, '_distribute'):
        to_reload = True
        raise ImportError
except ImportError:
    ez = {}
    opts = {"to_dir": "eggs", "download_delay": 0}
    if USE_DISTRIBUTE:
        url = 'http://python-distribute.org/distribute_setup.py'
        opts["no_fake"] = True
    else:
        url = 'http://peak.telecommunity.com/dist/ez_setup.py'

    execute(urlopen(url).read(), ez, filename=url)
    ez['use_setuptools'](**opts)
    if to_reload:
        reload(pkg_resources)
    else:
        import pkg_resources

subprocess.Popen(
    [sys.executable] +
    ['setup.py', '-q', 'develop', '-m', '-x', '-d', 'develop-eggs'],
    env = {'PYTHONPATH': os.path.dirname(pkg_resources.__file__)}).wait()

pkg_resources.working_set.add_entry('src')

import zc.buildout.easy_install
zc.buildout.easy_install.scripts(
    ['zc.buildout'], pkg_resources.working_set , sys.executable, 'bin')

bin_buildout = os.path.join('bin', 'buildout')

if is_jython:
    # Jython needs the script to be called twice via sys.executable
    assert subprocess.Popen([sys.executable] + [bin_buildout]).wait() == 0

sys.exit(subprocess.Popen(bin_buildout).wait())
