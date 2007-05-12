##############################################################################
#
# Copyright (c) 2004 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""XXX short summary goes here.

$Id$
"""

import os, re, shutil, sys, tempfile, unittest, zipfile
from zope.testing import doctest, renormalizing
import pkg_resources
import zc.buildout.testing, zc.buildout.easy_install

os_path_sep = os.path.sep
if os_path_sep == '\\':
    os_path_sep *= 2


def develop_w_non_setuptools_setup_scripts():
    """
We should be able to deal with setup scripts that aren't setuptools based.

    >>> mkdir('foo')
    >>> write('foo', 'setup.py',
    ... '''
    ... from distutils.core import setup
    ... setup(name="foo")
    ... ''')

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = foo
    ... parts = 
    ... ''')

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/foo

    >>> ls('develop-eggs')
    -  foo.egg-link
    -  zc.recipe.egg.egg-link

    """

def develop_verbose():
    """
We should be able to deal with setup scripts that aren't setuptools based.

    >>> mkdir('foo')
    >>> write('foo', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name="foo")
    ... ''')

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = foo
    ... parts = 
    ... ''')

    >>> print system(join('bin', 'buildout')+' -vv'), # doctest: +ELLIPSIS
    zc.buildout...
    buildout: Develop: /sample-buildout/foo
    ...
    Installed /sample-buildout/foo
    ...

    >>> ls('develop-eggs')
    -  foo.egg-link
    -  zc.recipe.egg.egg-link

    """

def buildout_error_handling():
    r"""Buildout error handling

Asking for a section that doesn't exist, yields a missing section error:

    >>> import os
    >>> os.chdir(sample_buildout)
    >>> import zc.buildout.buildout
    >>> buildout = zc.buildout.buildout.Buildout('buildout.cfg', [])
    >>> buildout['eek']
    Traceback (most recent call last):
    ...
    MissingSection: The referenced section, 'eek', was not defined.

Asking for an option that doesn't exist, a MissingOption error is raised:

    >>> buildout['buildout']['eek']
    Traceback (most recent call last):
    ...
    MissingOption: Missing option: buildout:eek

It is an error to create a variable-reference cycle:

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... parts =
    ... x = ${buildout:y}
    ... y = ${buildout:z}
    ... z = ${buildout:x}
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    ... # doctest: +NORMALIZE_WHITESPACE +ELLIPSIS
    While:
      Initializing
      Getting section buildout
      Initializing section buildout
      Getting option buildout:y
      Getting option buildout:z
      Getting option buildout:x
      Getting option buildout:y
    Error: Circular reference in substitutions.

It is an error to use funny characters in variable refereces:

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = data_dir debug
    ... x = ${bui$ldout:y}
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    While:
      Initializing
      Getting section buildout
      Initializing section buildout
      Getting option buildout:x
    Error: The section name in substitution, ${bui$ldout:y},
    has invalid characters.

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = data_dir debug
    ... x = ${buildout:y{z}
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    While:
      Initializing
      Getting section buildout
      Initializing section buildout
      Getting option buildout:x
    Error: The option name in substitution, ${buildout:y{z},
    has invalid characters.

and too have too many or too few colons:

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = data_dir debug
    ... x = ${parts}
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    While:
      Initializing
      Getting section buildout
      Initializing section buildout
      Getting option buildout:x
    Error: The substitution, ${parts},
    doesn't contain a colon.

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = data_dir debug
    ... x = ${buildout:y:z}
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    While:
      Initializing
      Getting section buildout
      Initializing section buildout
      Getting option buildout:x
    Error: The substitution, ${buildout:y:z},
    has too many colons.

Al parts have to have a section:

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = x
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    While:
      Installing
      Getting section x
    Error: The referenced section, 'x', was not defined.

and all parts have to have a specified recipe:


    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = x
    ...
    ... [x]
    ... foo = 1
    ... ''')

    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')),
    While:
      Installing
    Error: Missing option: x:recipe

"""

make_dist_that_requires_setup_py_template = """
from setuptools import setup
setup(name=%r, version=%r,
      install_requires=%r,
      )
"""

def make_dist_that_requires(dest, name, requires=[], version=1, egg=''):
    os.mkdir(os.path.join(dest, name))
    open(os.path.join(dest, name, 'setup.py'), 'w').write(
        make_dist_that_requires_setup_py_template
        % (name, version, requires)
        )

def show_who_requires_when_there_is_a_conflict():
    """
    It's a pain when we require eggs that have requirements that are
    incompatible. We want the error we get to tell us what is missing.

    Let's make a few develop distros, some of which have incompatible
    requirements.

    >>> make_dist_that_requires(sample_buildout, 'sampley',
    ...                         ['demoneeded ==1.0']) 
    >>> make_dist_that_requires(sample_buildout, 'samplez',
    ...                         ['demoneeded ==1.1']) 

    Now, let's create a buildout that requires y and z:

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = eggs
    ... develop = sampley samplez
    ... find-links = %(link_server)s
    ...
    ... [eggs]
    ... recipe = zc.recipe.egg
    ... eggs = sampley
    ...        samplez
    ... ''' % globals())

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/sampley
    buildout: Develop: /sample-buildout/samplez
    buildout: Installing eggs
    zc.buildout.easy_install: Getting new distribution for demoneeded==1.1
    zc.buildout.easy_install: Got demoneeded 1.1
    While:
      Installing eggs
    Error: There is a version conflict.
    We already have: demoneeded 1.1
    but sampley 1 requires demoneeded==1.0.

    Here, we see that sampley required an older version of demoneeded.
    What if we hadn't required sampley ourselves:

    >>> make_dist_that_requires(sample_buildout, 'samplea', ['sampleb']) 
    >>> make_dist_that_requires(sample_buildout, 'sampleb',
    ...                         ['sampley', 'samplea'])
    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = eggs
    ... develop = sampley samplez samplea sampleb
    ... find-links = %(link_server)s
    ...
    ... [eggs]
    ... recipe = zc.recipe.egg
    ... eggs = samplea
    ...        samplez
    ... ''' % globals())

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/sampley
    buildout: Develop: /sample-buildout/samplez
    buildout: Develop: /sample-buildout/samplea
    buildout: Develop: /sample-buildout/sampleb
    buildout: Installing eggs
    While:
      Installing eggs
    Error: There is a version conflict.
    We already have: demoneeded 1.1
    but sampley 1 requires demoneeded==1.0.
    sampley 1 is required by sampleb 1.
    sampleb 1 is required by samplea 1.
    """

def show_who_requires_missing_distributions():
    """

    When working with a lot of eggs, which require eggs recursively,
    it can be hard to tell why we're requireing things we can't find.
    Fortunately, buildout will tell us who's asking for something that
    we can't find.

    >>> make_dist_that_requires(sample_buildout, 'sampley', ['demoneeded']) 
    >>> make_dist_that_requires(sample_buildout, 'samplea', ['sampleb']) 
    >>> make_dist_that_requires(sample_buildout, 'sampleb',
    ...                         ['sampley', 'samplea'])
    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = eggs
    ... develop = sampley samplea sampleb
    ...
    ... [eggs]
    ... recipe = zc.recipe.egg
    ... eggs = samplea
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/sampley
    buildout: Develop: /sample-buildout/samplea
    buildout: Develop: /sample-buildout/sampleb
    buildout: Installing eggs
    Couldn't find index page for 'demoneeded' (maybe misspelled?)
    zc.buildout.easy_install: Getting new distribution for demoneeded
    While:
      Installing eggs
      Getting distribution for demoneeded
    Error: Couldn't find a distribution for demoneeded.
    demoneeded is required by sampley 1.
    sampley 1 is required by sampleb 1.
    sampleb 1 is required by samplea 1.

    """
    
 
def test_comparing_saved_options_with_funny_characters():
    """
    If an option has newlines, extra/odd spaces or a %, we need to make
    sure the comparison with the saved value works correctly.

    >>> mkdir(sample_buildout, 'recipes')
    >>> write(sample_buildout, 'recipes', 'debug.py', 
    ... '''
    ... class Debug:
    ...     def __init__(self, buildout, name, options):
    ...         options['debug'] = \"\"\"  <zodb>
    ...
    ...   <filestorage>
    ...     path foo
    ...   </filestorage>
    ...
    ... </zodb>  
    ...      \"\"\"
    ...         options['debug1'] = \"\"\"
    ... <zodb>
    ...
    ...   <filestorage>
    ...     path foo
    ...   </filestorage>
    ...
    ... </zodb>  
    ... \"\"\"
    ...         options['debug2'] = '  x  '
    ...         options['debug3'] = '42'
    ...         options['format'] = '%3d'
    ...
    ...     def install(self):
    ...         open('t', 'w').write('t')
    ...         return 't'
    ...
    ...     update = install
    ... ''')


    >>> write(sample_buildout, 'recipes', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(
    ...     name = "recipes",
    ...     entry_points = {'zc.buildout': ['default = debug:Debug']},
    ...     )
    ... ''')

    >>> write(sample_buildout, 'recipes', 'README.txt', " ")

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = debug
    ...
    ... [debug]
    ... recipe = recipes
    ... ''')

    >>> os.chdir(sample_buildout)
    >>> buildout = os.path.join(sample_buildout, 'bin', 'buildout')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Installing debug

If we run the buildout again, we shoudn't get a message about
uninstalling anything because the configuration hasn't changed.

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Updating debug
"""

def finding_eggs_as_local_directories():
    r"""
It is possible to set up find-links so that we could install from
a local directory that may contained unzipped eggs.

    >>> src = tmpdir('src')
    >>> write(src, 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='demo', py_modules=[''],
    ...    zip_safe=False, version='1.0', author='bob', url='bob', 
    ...    author_email='bob')
    ... ''')

    >>> write(src, 't.py', '#\n')
    >>> write(src, 'README.txt', '')
    >>> _ = system(join('bin', 'buildout')+' setup ' + src + ' bdist_egg')

Install it so it gets unzipped:

    >>> d1 = tmpdir('d1')
    >>> ws = zc.buildout.easy_install.install(
    ...     ['demo'], d1, links=[join(src, 'dist')], 
    ...     )

    >>> ls(d1)
    d  demo-1.0-py2.4.egg

Then try to install it again:

    >>> d2 = tmpdir('d2')
    >>> ws = zc.buildout.easy_install.install(
    ...     ['demo'], d2, links=[d1], 
    ...     )

    >>> ls(d2)
    d  demo-1.0-py2.4.egg

    """

def make_sure__get_version_works_with_2_digit_python_versions():
    """

This is a test of an internal function used by higher-level machinery.

We'll start by creating a faux 'python' that executable that prints a
2-digit version. This is a bit of a pain to do portably. :(

    >>> mkdir('demo')
    >>> write('demo', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='demo',
    ...       entry_points = {'console_scripts': ['demo = demo:main']},
    ...       )
    ... ''')
    >>> write('demo', 'demo.py',
    ... '''
    ... def main():
    ...     print 'Python 2.5'
    ... ''')

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = demo
    ... parts = 
    ... ''')

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/demo

    >>> import zc.buildout.easy_install
    >>> ws = zc.buildout.easy_install.working_set(
    ...    ['demo'], sys.executable, ['develop-eggs'])
    >>> zc.buildout.easy_install.scripts(
    ...    ['demo'], ws, sys.executable, 'bin')
    ['bin/demo']

    >>> print system(join('bin', 'demo')),
    Python 2.5

Now, finally, let's test _get_version:

    >>> zc.buildout.easy_install._get_version(join('bin', 'demo'))
    '2.5'

    """

def create_sections_on_command_line():
    """
    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts =
    ... x = ${foo:bar}
    ... ''')

    >>> print system(buildout + ' foo:bar=1 -vD'), # doctest: +ELLIPSIS
    zc.buildout.easy_install: Installing ['zc.buildout', 'setuptools']
    ...
    [foo]
    bar = 1
    ...
    
    """

# Why?
## def error_for_undefined_install_parts():
##     """
## Any parts we pass to install on the command line must be
## listed in the configuration.

##     >>> print system(join('bin', 'buildout') + ' install foo'),
##     buildout: Invalid install parts: foo.
##     Install parts must be listed in the configuration.

##     >>> print system(join('bin', 'buildout') + ' install foo bar'),
##     buildout: Invalid install parts: foo bar.
##     Install parts must be listed in the configuration.
    
##     """


bootstrap_py = os.path.join(
       os.path.dirname(
          os.path.dirname(
             os.path.dirname(
                os.path.dirname(zc.buildout.__file__)
                )
             )
          ),
       'bootstrap', 'bootstrap.py')
if os.path.exists(bootstrap_py):
    def test_bootstrap_py():
        """Make sure the bootstrap script actually works

    >>> sample_buildout = tmpdir('sample')
    >>> os.chdir(sample_buildout)
    >>> write('bootstrap.py', open(bootstrap_py).read())
    >>> print system(sys.executable+' '+'bootstrap.py'), # doctest: +ELLIPSIS
    Downloading ...
    Warning: creating ...buildout.cfg
    buildout: Creating directory ...bin
    buildout: Creating directory ...parts
    buildout: Creating directory ...eggs
    buildout: Creating directory ...develop-eggs
    zc.buildout.easy_install: Generated script /sample/bin/buildout.

    >>> ls(sample_buildout)
    d  bin
    -  bootstrap.py
    -  buildout.cfg
    d  develop-eggs
    d  eggs
    d  parts


    >>> ls(sample_buildout, 'bin')
    -  buildout

    >>> ls(sample_buildout, 'eggs')
    -  setuptools-0.6-py2.4.egg
    d  zc.buildout-1.0-py2.4.egg

    """

def test_help():
    """
>>> print system(os.path.join(sample_buildout, 'bin', 'buildout')+' -h'),
Usage: buildout [options] [assignments] [command [command arguments]]
<BLANKLINE>
Options:
<BLANKLINE>
  -h, --help
<BLANKLINE>
     Print this message and exit.
<BLANKLINE>
  -v
<BLANKLINE>
     Increase the level of verbosity.  This option can be used multiple times.
<BLANKLINE>
  -q
<BLANKLINE>
     Decrease the level of verbosity.  This option can be used multiple times.
<BLANKLINE>
  -c config_file
<BLANKLINE>
     Specify the path to the buildout configuration file to be used.
     This defaults to the file named "buildout.cfg" in the current
     working directory.
<BLANKLINE>
  -U
<BLANKLINE>
     Don't read user defaults.
<BLANKLINE>
  -o
<BLANKLINE>
    Run in off-line mode.  This is equivalent to the assignment 
    buildout:offline=true.
<BLANKLINE>
  -O
<BLANKLINE>
    Run in non-off-line mode.  This is equivalent to the assignment 
    buildout:offline=false.  This is the default buildout mode.  The
    -O option would normally be used to override a true offline
    setting in a configuration file.
<BLANKLINE>
  -n
<BLANKLINE>
    Run in newest mode.  This is equivalent to the assignment
    buildout:newest=true.  With this setting, which is the default,
    buildout will try to find the newest versions of distributions
    available that satisfy its requirements.
<BLANKLINE>
  -N
<BLANKLINE>
    Run in non-newest mode.  This is equivalent to the assignment 
    buildout:newest=false.  With this setting, buildout will not seek
    new distributions if installed distributions satisfy it's
    requirements. 
<BLANKLINE>
  -D
<BLANKLINE>
    Debug errors.  If an error occurs, then the post-mortem debugger
    will be started. This is especially useful for debuging recipe
    problems.
<BLANKLINE>
Assignments are of the form: section:option=value and are used to
provide configuration options that override those given in the
configuration file.  For example, to run the buildout in offline mode,
use buildout:offline=true.
<BLANKLINE>
Options and assignments can be interspersed.
<BLANKLINE>
Commands:
<BLANKLINE>
  install [parts]
<BLANKLINE>
    Install parts.  If no command arguments are given, then the parts
    definition from the configuration file is used.  Otherwise, the
    arguments specify the parts to be installed.
<BLANKLINE>
  bootstrap
<BLANKLINE>
    Create a new buildout in the current working directory, copying
    the buildout and setuptools eggs and, creating a basic directory
    structure and a buildout-local buildout script.
<BLANKLINE>
<BLANKLINE>

>>> print system(os.path.join(sample_buildout, 'bin', 'buildout')
...              +' --help'),
Usage: buildout [options] [assignments] [command [command arguments]]
<BLANKLINE>
Options:
<BLANKLINE>
  -h, --help
<BLANKLINE>
     Print this message and exit.
<BLANKLINE>
  -v
<BLANKLINE>
     Increase the level of verbosity.  This option can be used multiple times.
<BLANKLINE>
  -q
<BLANKLINE>
     Decrease the level of verbosity.  This option can be used multiple times.
<BLANKLINE>
  -c config_file
<BLANKLINE>
     Specify the path to the buildout configuration file to be used.
     This defaults to the file named "buildout.cfg" in the current
     working directory.
<BLANKLINE>
  -U
<BLANKLINE>
     Don't read user defaults.
<BLANKLINE>
  -o
<BLANKLINE>
    Run in off-line mode.  This is equivalent to the assignment 
    buildout:offline=true.
<BLANKLINE>
  -O
<BLANKLINE>
    Run in non-off-line mode.  This is equivalent to the assignment 
    buildout:offline=false.  This is the default buildout mode.  The
    -O option would normally be used to override a true offline
    setting in a configuration file.
<BLANKLINE>
  -n
<BLANKLINE>
    Run in newest mode.  This is equivalent to the assignment
    buildout:newest=true.  With this setting, which is the default,
    buildout will try to find the newest versions of distributions
    available that satisfy its requirements.
<BLANKLINE>
  -N
<BLANKLINE>
    Run in non-newest mode.  This is equivalent to the assignment 
    buildout:newest=false.  With this setting, buildout will not seek
    new distributions if installed distributions satisfy it's
    requirements. 
<BLANKLINE>
  -D
<BLANKLINE>
    Debug errors.  If an error occurs, then the post-mortem debugger
    will be started. This is especially useful for debuging recipe
    problems.
<BLANKLINE>
Assignments are of the form: section:option=value and are used to
provide configuration options that override those given in the
configuration file.  For example, to run the buildout in offline mode,
use buildout:offline=true.
<BLANKLINE>
Options and assignments can be interspersed.
<BLANKLINE>
Commands:
<BLANKLINE>
  install [parts]
<BLANKLINE>
    Install parts.  If no command arguments are given, then the parts
    definition from the configuration file is used.  Otherwise, the
    arguments specify the parts to be installed.
<BLANKLINE>
  bootstrap
<BLANKLINE>
    Create a new buildout in the current working directory, copying
    the buildout and setuptools eggs and, creating a basic directory
    structure and a buildout-local buildout script.
<BLANKLINE>
<BLANKLINE>
    """

def test_bootstrap_with_extension():
    """
We had a problem running a bootstrap with an extension.  Let's make
sure it is fixed.  Basically, we don't load extensions when
bootstrapping.

    >>> d = tmpdir('sample-bootstrap')
    
    >>> write(d, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... extensions = some_awsome_extension
    ... parts = 
    ... ''')

    >>> os.chdir(d)
    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')
    ...              + ' bootstrap'),
    buildout: Creating directory /sample-bootstrap/bin
    buildout: Creating directory /sample-bootstrap/parts
    buildout: Creating directory /sample-bootstrap/eggs
    buildout: Creating directory /sample-bootstrap/develop-eggs
    zc.buildout.easy_install: Generated script /sample-bootstrap/bin/buildout.
    """


def bug_92891_bootstrap_crashes_with_egg_recipe_in_buildout_section():
    """
    >>> d = tmpdir('sample-bootstrap')
    
    >>> write(d, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = buildout
    ... eggs-directory = eggs
    ...
    ... [buildout]
    ... recipe = zc.recipe.egg
    ... eggs = zc.buildout
    ... scripts = buildout=buildout
    ... ''')

    >>> os.chdir(d)
    >>> print system(os.path.join(sample_buildout, 'bin', 'buildout')
    ...              + ' bootstrap'),
    buildout: Creating directory /sample-bootstrap/bin
    buildout: Creating directory /sample-bootstrap/parts
    buildout: Creating directory /sample-bootstrap/eggs
    buildout: Creating directory /sample-bootstrap/develop-eggs
    zc.buildout.easy_install: Generated script /sample-bootstrap/bin/buildout.

    >>> print system(os.path.join('bin', 'buildout')),
    buildout: Unused options for buildout: 'scripts' 'eggs'

    """

def removing_eggs_from_develop_section_causes_egg_link_to_be_removed():
    '''
    >>> cd(sample_buildout)

Create a develop egg:

    >>> mkdir('foo')
    >>> write('foo', 'setup.py',
    ... """
    ... from setuptools import setup
    ... setup(name='foox')
    ... """)
    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... develop = foo
    ... parts =
    ... """)

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/foo

    >>> ls('develop-eggs')
    -  foox.egg-link
    -  zc.recipe.egg.egg-link

Create another:

    >>> mkdir('bar')
    >>> write('bar', 'setup.py',
    ... """
    ... from setuptools import setup
    ... setup(name='fooy')
    ... """)
    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... develop = foo bar
    ... parts =
    ... """)

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/foo
    buildout: Develop: /sample-buildout/bar

    >>> ls('develop-eggs')
    -  foox.egg-link
    -  fooy.egg-link
    -  zc.recipe.egg.egg-link

Remove one:

    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... develop = bar
    ... parts =
    ... """)
    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/bar

It is gone

    >>> ls('develop-eggs')
    -  fooy.egg-link
    -  zc.recipe.egg.egg-link

Remove the other:

    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... parts =
    ... """)
    >>> print system(join('bin', 'buildout')),

All gone

    >>> ls('develop-eggs')
    -  zc.recipe.egg.egg-link
    '''


def add_setuptools_to_dependencies_when_namespace_packages():
    '''    
Often, a package depends on setuptools soley by virtue of using
namespace packages. In this situation, package authors often forget to
declare setuptools as a dependency. This is a mistake, but,
unfortunately, a common one that we need to work around.  If an egg
uses namespace packages and does not include setuptools as a depenency,
we will still include setuptools in the working set.  If we see this for
a devlop egg, we will also generate a warning.

    >>> mkdir('foo')
    >>> mkdir('foo', 'src')
    >>> mkdir('foo', 'src', 'stuff')
    >>> write('foo', 'src', 'stuff', '__init__.py',
    ... """__import__('pkg_resources').declare_namespace(__name__)
    ... """)
    >>> mkdir('foo', 'src', 'stuff', 'foox')
    >>> write('foo', 'src', 'stuff', 'foox', '__init__.py', '')
    >>> write('foo', 'setup.py',
    ... """
    ... from setuptools import setup
    ... setup(name='foox',
    ...       namespace_packages = ['stuff'],
    ...       package_dir = {'': 'src'},
    ...       packages = ['stuff', 'stuff.foox'],
    ...       )
    ... """)
    >>> write('foo', 'README.txt', '')
    
    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... develop = foo
    ... parts = 
    ... """)

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/foo

Now, if we generate a working set using the egg link, we will get a warning
and we will get setuptools included in the working set.

    >>> import logging, zope.testing.loggingsupport
    >>> handler = zope.testing.loggingsupport.InstalledHandler(
    ...        'zc.buildout', level=logging.WARNING)
    >>> logging.getLogger('zc').propagate = False
    
    >>> [dist.project_name
    ...  for dist in zc.buildout.easy_install.working_set(
    ...    ['foox'], sys.executable,
    ...    [join(sample_buildout, 'eggs'),
    ...     join(sample_buildout, 'develop-eggs'),
    ...     ])]
    ['foox', 'setuptools']

    >>> print handler
    zc.buildout.easy_install WARNING
      Develop distribution for foox 0.0.0
    uses namespace packages but the distribution does not require setuptools.

    >>> handler.clear()

On the other hand, if we have a regular egg, rather than a develop egg:

    >>> os.remove(join('develop-eggs', 'foox.egg-link'))

    >>> _ = system(join('bin', 'buildout') + ' setup foo bdist_egg -d'
    ...            + join(sample_buildout, 'eggs'))

    >>> ls('develop-eggs')
    -  zc.recipe.egg.egg-link
    
    >>> ls('eggs') # doctest: +ELLIPSIS
    -  foox-0.0.0-py2.4.egg
    ...
    
We do not get a warning, but we do get setuptools included in the working set:

    >>> [dist.project_name
    ...  for dist in zc.buildout.easy_install.working_set(
    ...    ['foox'], sys.executable,
    ...    [join(sample_buildout, 'eggs'),
    ...     join(sample_buildout, 'develop-eggs'),
    ...     ])]
    ['foox', 'setuptools']

    >>> print handler,

We get the same behavior if the it is a depedency that uses a
namespace package.


    >>> mkdir('bar')
    >>> write('bar', 'setup.py',
    ... """
    ... from setuptools import setup
    ... setup(name='bar', install_requires = ['foox'])
    ... """)
    >>> write('bar', 'README.txt', '')
    
    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... develop = foo bar
    ... parts = 
    ... """)

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/foo
    buildout: Develop: /sample-buildout/bar

    >>> [dist.project_name
    ...  for dist in zc.buildout.easy_install.working_set(
    ...    ['bar'], sys.executable,
    ...    [join(sample_buildout, 'eggs'),
    ...     join(sample_buildout, 'develop-eggs'),
    ...     ])]
    ['bar', 'foox', 'setuptools']

    >>> print handler,
    zc.buildout.easy_install WARNING
      Develop distribution for foox 0.0.0
    uses namespace packages but the distribution does not require setuptools.


    >>> logging.getLogger('zc').propagate = True
    >>> handler.uninstall()

    '''

def develop_preserves_existing_setup_cfg():
    """
    
See "Handling custom build options for extensions in develop eggs" in
easy_install.txt.  This will be very similar except that we'll have an
existing setup.cfg:

    >>> write(extdemo, "setup.cfg",
    ... '''
    ... # sampe cfg file
    ...
    ... [foo]
    ... bar = 1
    ...
    ... [build_ext]
    ... define = X,Y
    ... ''')

    >>> mkdir('include')
    >>> write('include', 'extdemo.h',
    ... '''
    ... #define EXTDEMO 42
    ... ''')

    >>> dest = tmpdir('dest')
    >>> zc.buildout.easy_install.develop(
    ...   extdemo, dest, 
    ...   {'include-dirs': os.path.join(sample_buildout, 'include')})
    '/dest/extdemo.egg-link'

    >>> ls(dest)
    -  extdemo.egg-link

    >>> cat(extdemo, "setup.cfg")
    <BLANKLINE>
    # sampe cfg file
    <BLANKLINE>
    [foo]
    bar = 1
    <BLANKLINE>
    [build_ext]
    define = X,Y

"""

def uninstall_recipes_used_for_removal():
    """
Uninstall recipes need to be called when a part is removed too:

    >>> mkdir("recipes")
    >>> write("recipes", "setup.py",
    ... '''
    ... from setuptools import setup
    ... setup(name='recipes',
    ...       entry_points={
    ...          'zc.buildout': ["demo=demo:Install"],
    ...          'zc.buildout.uninstall': ["demo=demo:uninstall"],
    ...          })
    ... ''')

    >>> write("recipes", "demo.py",
    ... '''
    ... class Install:
    ...     def __init__(*args): pass
    ...     def install(self):
    ...         print 'installing'
    ...         return ()
    ... def uninstall(name, options): print 'uninstalling'
    ... ''')

    >>> write('buildout.cfg', '''
    ... [buildout]
    ... develop = recipes
    ... parts = demo
    ... [demo]
    ... recipe = recipes:demo
    ... ''')

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/recipes
    buildout: Installing demo
    installing


    >>> write('buildout.cfg', '''
    ... [buildout]
    ... develop = recipes
    ... parts = demo
    ... [demo]
    ... recipe = recipes:demo
    ... x = 1
    ... ''')

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/recipes
    buildout: Uninstalling demo
    buildout: Running uninstall recipe
    uninstalling
    buildout: Installing demo
    installing


    >>> write('buildout.cfg', '''
    ... [buildout]
    ... develop = recipes
    ... parts = 
    ... ''')

    >>> print system(join('bin', 'buildout')),
    buildout: Develop: /sample-buildout/recipes
    buildout: Uninstalling demo
    buildout: Running uninstall recipe
    uninstalling

"""

def extensions_installed_as_eggs_work_in_offline_mode():
    '''
    >>> mkdir('demo')

    >>> write('demo', 'demo.py', 
    ... """
    ... def ext(buildout):
    ...     print 'ext', list(buildout)
    ... """)

    >>> write('demo', 'setup.py',
    ... """
    ... from setuptools import setup
    ... 
    ... setup(
    ...     name = "demo",
    ...     py_modules=['demo'],
    ...     entry_points = {'zc.buildout.extension': ['ext = demo:ext']},
    ...     )
    ... """)

    >>> bdist_egg(join(sample_buildout, "demo"), sys.executable,
    ...           join(sample_buildout, "eggs"))

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... extensions = demo
    ... parts =
    ... offline = true
    ... """)

    >>> print system(join(sample_buildout, 'bin', 'buildout')),
    ext ['buildout']
    

    '''

def changes_in_svn_or_CVS_dont_affect_sig():
    """
    
If we have a develop recipe, it's signature shouldn't be affected to
changes in .svn or CVS directories.

    >>> mkdir('recipe')
    >>> write('recipe', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='recipe',
    ...       entry_points={'zc.buildout': ['default=foo:Foo']})
    ... ''')
    >>> write('recipe', 'foo.py',
    ... '''
    ... class Foo:
    ...     def __init__(*args): pass
    ...     def install(*args): return ()
    ...     update = install
    ... ''')
    
    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipe
    ... parts = foo
    ... 
    ... [foo]
    ... recipe = recipe
    ... ''')


    >>> print system(join(sample_buildout, 'bin', 'buildout')),
    buildout: Develop: /sample-buildout/recipe
    buildout: Installing foo

    >>> mkdir('recipe', '.svn')
    >>> mkdir('recipe', 'CVS')
    >>> print system(join(sample_buildout, 'bin', 'buildout')),
    buildout: Develop: /sample-buildout/recipe
    buildout: Updating foo

    >>> write('recipe', '.svn', 'x', '1')
    >>> write('recipe', 'CVS', 'x', '1')

    >>> print system(join(sample_buildout, 'bin', 'buildout')),
    buildout: Develop: /sample-buildout/recipe
    buildout: Updating foo

    """

def o_option_sets_offline():
    """
    >>> print system(join(sample_buildout, 'bin', 'buildout')+' -vvo'),
    ... # doctest: +ELLIPSIS
    <BLANKLINE>
    ...
    offline = true
    ...
    """

def recipe_upgrade():
    """

The buildout will upgrade recipes in newest (and non-offline) mode.

Let's create a recipe egg

    >>> mkdir('recipe')
    >>> write('recipe', 'recipe.py',
    ... '''
    ... class Recipe:
    ...     def __init__(*a): pass
    ...     def install(self):
    ...         print 'recipe v1'
    ...         return ()
    ...     update = install
    ... ''')

    >>> write('recipe', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='recipe', version='1', py_modules=['recipe'],
    ...       entry_points={'zc.buildout': ['default = recipe:Recipe']},
    ...       )
    ... ''')

    >>> write('recipe', 'README', '')

    >>> print system(buildout+' setup recipe bdist_egg'), # doctest: +ELLIPSIS
    buildout: Running setup script recipe/setup.py
    ...

    >>> rmdir('recipe', 'build')

And update our buildout to use it.

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = foo
    ... find-links = %s
    ...
    ... [foo]
    ... recipe = recipe
    ... ''' % join('recipe', 'dist'))

    >>> print system(buildout),
    zc.buildout.easy_install: Getting new distribution for recipe
    zc.buildout.easy_install: Got recipe 1
    buildout: Installing foo
    recipe v1

Now, if we update the recipe egg:

    >>> write('recipe', 'recipe.py',
    ... '''
    ... class Recipe:
    ...     def __init__(*a): pass
    ...     def install(self):
    ...         print 'recipe v2'
    ...         return ()
    ...     update = install
    ... ''')

    >>> write('recipe', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='recipe', version='2', py_modules=['recipe'],
    ...       entry_points={'zc.buildout': ['default = recipe:Recipe']},
    ...       )
    ... ''')


    >>> print system(buildout+' setup recipe bdist_egg'), # doctest: +ELLIPSIS
    buildout: Running setup script recipe/setup.py
    ...

We won't get the update if we specify -N:

    >>> print system(buildout+' -N'),
    buildout: Updating foo
    recipe v1

or if we use -o:

    >>> print system(buildout+' -o'),
    buildout: Updating foo
    recipe v1

But we will if we use neither of these:

    >>> print system(buildout),
    zc.buildout.easy_install: Getting new distribution for recipe
    zc.buildout.easy_install: Got recipe 2
    buildout: Uninstalling foo
    buildout: Installing foo
    recipe v2

We can also select a particular recipe version:

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = foo
    ... find-links = %s
    ...
    ... [foo]
    ... recipe = recipe ==1
    ... ''' % join('recipe', 'dist'))

    >>> print system(buildout),
    buildout: Uninstalling foo
    buildout: Installing foo
    recipe v1
    
    """

def update_adds_to_uninstall_list():
    """

Paths returned by the update method are added to the list of paths to
uninstall

    >>> mkdir('recipe')
    >>> write('recipe', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='recipe',
    ...       entry_points={'zc.buildout': ['default = recipe:Recipe']},
    ...       )
    ... ''')

    >>> write('recipe', 'recipe.py',
    ... '''
    ... import os
    ... class Recipe:
    ...     def __init__(*_): pass
    ...     def install(self):
    ...         r = ('a', 'b', 'c')
    ...         for p in r: os.mkdir(p)
    ...         return r
    ...     def update(self):
    ...         r = ('c', 'd', 'e')
    ...         for p in r:
    ...             if not os.path.exists(p):
    ...                os.mkdir(p)
    ...         return r
    ... ''')

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipe
    ... parts = foo
    ...
    ... [foo]
    ... recipe = recipe
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /tmp/tmpbHOHnU/_TEST_/sample-buildout/recipe
    buildout: Installing foo

    >>> print system(buildout),
    buildout: Develop: /tmp/tmpbHOHnU/_TEST_/sample-buildout/recipe
    buildout: Updating foo

    >>> cat('.installed.cfg') # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    [buildout]
    ...
    [foo]
    __buildout_installed__ = a
    	b
    	c
    	d
    	e
    __buildout_signature__ = ...

"""

def log_when_there_are_not_local_distros():
    """
    >>> from zope.testing.loggingsupport import InstalledHandler
    >>> handler = InstalledHandler('zc.buildout.easy_install')
    >>> import logging
    >>> logger = logging.getLogger('zc.buildout.easy_install')
    >>> old_propogate = logger.propagate
    >>> logger.propagate = False

    >>> dest = tmpdir('sample-install')
    >>> import zc.buildout.easy_install
    >>> ws = zc.buildout.easy_install.install(
    ...     ['demo==0.2'], dest,
    ...     links=[link_server], index=link_server+'index/')

    >>> print handler # doctest: +ELLIPSIS
    zc.buildout.easy_install DEBUG
      Installing ['demo==0.2']
    zc.buildout.easy_install DEBUG
      We have no distributions for demo that satisfies demo==0.2.
    ...

    >>> handler.uninstall()
    >>> logger.propagate = old_propogate
    
    """

def internal_errors():
    """Internal errors are clearly marked and don't generate tracebacks:

    >>> mkdir(sample_buildout, 'recipes')

    >>> write(sample_buildout, 'recipes', 'mkdir.py', 
    ... '''
    ... class Mkdir:
    ...     def __init__(self, buildout, name, options):
    ...         self.name, self.options = name, options
    ...         options['path'] = os.path.join(
    ...                               buildout['buildout']['directory'],
    ...                               options['path'],
    ...                               )
    ... ''')

    >>> write(sample_buildout, 'recipes', 'setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name = "recipes",
    ...       entry_points = {'zc.buildout': ['mkdir = mkdir:Mkdir']},
    ...       )
    ... ''')

    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = data-dir
    ...
    ... [data-dir]
    ... recipe = recipes:mkdir
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    While:
      Installing
      Getting section data-dir
      Initializing part data-dir
    <BLANKLINE>
    An internal error occured due to a bug in either zc.buildout or in a
    recipe being used:
    <BLANKLINE>
    NameError:
    global name 'os' is not defined
    """

def download_errors():
    """
    >>> write(sample_buildout, 'buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = 
    ... find-links = http://127.0.0.1/no-shuch-thing
    ... ''')

    >>> print system(buildout), # doctest: +ELLIPSIS
    While:
      Installing
      Checking for upgrades
      Getting distribution for setuptools
    Error: Download error...
    """

def whine_about_unused_options():
    '''

    >>> write('foo.py', 
    ... """
    ... class Foo:
    ...
    ...     def __init__(self, buildout, name, options):
    ...         self.name, self.options = name, options
    ...         options['x']
    ...
    ...     def install(self):
    ...         self.options['y']
    ...         return ()
    ... """)

    >>> write('setup.py',
    ... """
    ... from setuptools import setup
    ... setup(name = "foo",
    ...       entry_points = {'zc.buildout': ['default = foo:Foo']},
    ...       )
    ... """)

    >>> write('buildout.cfg',
    ... """
    ... [buildout]
    ... develop = .
    ... parts = foo
    ... a = 1
    ...
    ... [foo]
    ... recipe = foo
    ... x = 1
    ... y = 1
    ... z = 1
    ... """)

    >>> print system(buildout),
    buildout: Develop: /tmp/tmpsueWpG/_TEST_/sample-buildout/.
    buildout: Unused options for buildout: 'a'
    buildout: Installing foo
    buildout: Unused options for foo: 'z'
    '''

def abnormal_exit():
    """
People sometimes hit control-c while running a builout. We need to make
sure that the installed database Isn't corrupted.  To test this, we'll create
some evil recipes that exit uncleanly:

    >>> mkdir('recipes')
    >>> write('recipes', 'recipes.py',
    ... '''
    ... import os
    ...
    ... class Clean:
    ...     def __init__(*_): pass
    ...     def install(_): return ()
    ...     def update(_): pass
    ...
    ... class EvilInstall(Clean):
    ...     def install(_): os._exit(1)
    ...
    ... class EvilUpdate(Clean):
    ...     def update(_): os._exit(1)
    ... ''')

    >>> write('recipes', 'setup.py',
    ... '''
    ... import setuptools
    ... setuptools.setup(name='recipes',
    ...    entry_points = {
    ...      'zc.buildout': [
    ...          'clean = recipes:Clean',
    ...          'evil_install = recipes:EvilInstall',
    ...          'evil_update = recipes:EvilUpdate',
    ...          'evil_uninstall = recipes:Clean',
    ...          ],
    ...       },
    ...     )
    ... ''')

Now let's look at 3 cases:

1. We exit during installation after installing some other parts:

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = p1 p2 p3 p4
    ...
    ... [p1]
    ... recipe = recipes:clean
    ...
    ... [p2]
    ... recipe = recipes:clean
    ...
    ... [p3]
    ... recipe = recipes:evil_install
    ...
    ... [p4]
    ... recipe = recipes:clean
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Installing p1
    buildout: Installing p2
    buildout: Installing p3

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Updating p1
    buildout: Updating p2
    buildout: Installing p3

    >>> print system(buildout+' buildout:parts='),
    buildout: Develop: /sample-buildout/recipes
    buildout: Uninstalling p2
    buildout: Uninstalling p1

2. We exit while updating:

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = p1 p2 p3 p4
    ...
    ... [p1]
    ... recipe = recipes:clean
    ...
    ... [p2]
    ... recipe = recipes:clean
    ...
    ... [p3]
    ... recipe = recipes:evil_update
    ...
    ... [p4]
    ... recipe = recipes:clean
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Installing p1
    buildout: Installing p2
    buildout: Installing p3
    buildout: Installing p4

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Updating p1
    buildout: Updating p2
    buildout: Updating p3

    >>> print system(buildout+' buildout:parts='),
    buildout: Develop: /sample-buildout/recipes
    buildout: Uninstalling p2
    buildout: Uninstalling p1
    buildout: Uninstalling p4
    buildout: Uninstalling p3

3. We exit while installing or updating after uninstalling:

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = p1 p2 p3 p4
    ...
    ... [p1]
    ... recipe = recipes:evil_update
    ...
    ... [p2]
    ... recipe = recipes:clean
    ...
    ... [p3]
    ... recipe = recipes:clean
    ...
    ... [p4]
    ... recipe = recipes:clean
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Installing p1
    buildout: Installing p2
    buildout: Installing p3
    buildout: Installing p4

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = p1 p2 p3 p4
    ...
    ... [p1]
    ... recipe = recipes:evil_update
    ...
    ... [p2]
    ... recipe = recipes:clean
    ...
    ... [p3]
    ... recipe = recipes:clean
    ...
    ... [p4]
    ... recipe = recipes:clean
    ... x = 1
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Uninstalling p4
    buildout: Updating p1

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = recipes
    ... parts = p1 p2 p3 p4
    ...
    ... [p1]
    ... recipe = recipes:clean
    ...
    ... [p2]
    ... recipe = recipes:clean
    ...
    ... [p3]
    ... recipe = recipes:clean
    ...
    ... [p4]
    ... recipe = recipes:clean
    ... ''')

    >>> print system(buildout),
    buildout: Develop: /sample-buildout/recipes
    buildout: Uninstalling p1
    buildout: Installing p1
    buildout: Updating p2
    buildout: Updating p3
    buildout: Installing p4

    """

def install_source_dist_with_bad_py():
    """

    >>> mkdir('badegg')
    >>> mkdir('badegg', 'badegg')
    >>> write('badegg', 'badegg', '__init__.py', '#\\n')
    >>> mkdir('badegg', 'badegg', 'scripts')
    >>> write('badegg', 'badegg', 'scripts', '__init__.py', '#\\n')
    >>> write('badegg', 'badegg', 'scripts', 'one.py',
    ... '''
    ... return 1
    ... ''')

    >>> write('badegg', 'setup.py',
    ... '''
    ... from setuptools import setup, find_packages
    ... setup(
    ...     name='badegg',
    ...     version='1',
    ...     packages = find_packages('.'),
    ...     zip_safe=False)
    ... ''')

    >>> print system(buildout+' setup badegg sdist'), # doctest: +ELLIPSIS
    buildout: Running setup script badegg/setup.py
    ...
    
    >>> dist = join('badegg', 'dist')

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = eggs bo
    ... find-links = %(dist)s
    ...
    ... [eggs]
    ... recipe = zc.recipe.egg
    ... eggs = badegg
    ...
    ... [bo]
    ... recipe = zc.recipe.egg
    ... eggs = zc.buildout
    ... scripts = buildout=bo
    ... ''' % globals())

    >>> print system('buildout'),
    buildout: Not upgrading because not running a local buildout command
    buildout: Installing eggs
    zc.buildout.easy_install: Getting new distribution for badegg
      File "build/bdist.linux-i686/egg/badegg/scripts/one.py", line 2
        return 1
    SyntaxError: 'return' outside function
      File "/sample-buildout/eggs/badegg-1-py2.4.egg/badegg/scripts/one.py", line 2
        return 1
    SyntaxError: 'return' outside function
    zc.buildout.easy_install: Got badegg 1
    buildout: Installing bo

    >>> ls('eggs') # doctest: +ELLIPSIS
    d  badegg-1-py2.4.egg
    ...
    
    >>> ls('bin')
    -  bo
    -  buildout
    """

def version_requirements_in_build_honored():
    '''

    >>> update_extdemo()
    >>> dest = tmpdir('sample-install')
    >>> mkdir('include')
    >>> write('include', 'extdemo.h',
    ... """
    ... #define EXTDEMO 42
    ... """)

    >>> zc.buildout.easy_install.build(
    ...   'extdemo ==1.4', dest, 
    ...   {'include-dirs': os.path.join(sample_buildout, 'include')},
    ...   links=[link_server], index=link_server+'index/',
    ...   newest=False)
    ['/sample-install/extdemo-1.4-py2.4-linux-i686.egg']

    '''

def bug_105081_Specific_egg_versions_are_ignored_when_newer_eggs_are_around():
    """
    Buildout might ignore a specific egg requirement for a recipe:

    - Have a newer version of an egg in your eggs directory
    - Use 'recipe==olderversion' in your buildout.cfg to request an
      older version

    Buildout will go and fetch the older version, but it will *use*
    the newer version when installing a part with this recipe.

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = x
    ... find-links = %(sample_eggs)s
    ...
    ... [x]
    ... recipe = zc.recipe.egg
    ... eggs = demo
    ... ''' % globals())

    >>> print system(buildout),
    buildout: Installing x
    zc.buildout.easy_install: Getting new distribution for demo
    zc.buildout.easy_install: Got demo 0.3
    zc.buildout.easy_install: Getting new distribution for demoneeded
    zc.buildout.easy_install: Got demoneeded 1.1
    zc.buildout.easy_install: Generated script /sample-buildout/bin/demo.

    >>> print system(join('bin', 'demo')),
    3 1

    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... parts = x
    ... find-links = %(sample_eggs)s
    ...
    ... [x]
    ... recipe = zc.recipe.egg
    ... eggs = demo ==0.1
    ... ''' % globals())
    
    >>> print system(buildout),
    buildout: Uninstalling x
    buildout: Installing x
    zc.buildout.easy_install: Getting new distribution for demo==0.1
    zc.buildout.easy_install: Got demo 0.1
    zc.buildout.easy_install: Generated script /sample-buildout/bin/demo.

    >>> print system(join('bin', 'demo')),
    1 1
    """

if sys.version_info > (2, 4):
    def test_exit_codes():
        """
        >>> import subprocess
        >>> def call(s):
        ...     p = subprocess.Popen(s, stdin=subprocess.PIPE,
        ...                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ...     p.stdin.close()
        ...     print p.stdout.read()
        ...     print 'Exit:', bool(p.wait())
        
        >>> call(buildout)
        <BLANKLINE>
        Exit: False

        >>> write('buildout.cfg',
        ... '''
        ... [buildout]
        ... parts = x
        ... ''')

        >>> call(buildout)
        While:
          Installing
          Getting section x
        Error: The referenced section, 'x', was not defined.
        <BLANKLINE>
        Exit: True

        >>> write('setup.py',
        ... '''
        ... from setuptools import setup
        ... setup(name='zc.buildout.testexit', entry_points={
        ...    'zc.buildout': ['default = testexitrecipe:x']})
        ... ''')

        >>> write('testexitrecipe.py',
        ... '''
        ... x y
        ... ''')

        >>> write('buildout.cfg',
        ... '''
        ... [buildout]
        ... parts = x
        ... develop = .
        ...
        ... [x]
        ... recipe = zc.buildout.testexit
        ... ''')

        >>> call(buildout)
        buildout: Develop: /sample-buildout/.
        While:
          Installing
          Getting section x
          Initializing section x
          Loading zc.buildout recipe entry zc.buildout.testexit:default
        <BLANKLINE>
        An internal error occured due to a bug in either zc.buildout or in a
        recipe being used:
        <BLANKLINE>
        SyntaxError:
        invalid syntax (testexitrecipe.py, line 2)
        <BLANKLINE>
        Exit: True

        """

def bug_59270_recipes_always_start_in_buildout_dir():
    """
    Recipes can rely on running from buildout directory

    >>> mkdir('bad_start')
    >>> write('bad_recipe.py',
    ... '''
    ... import os
    ... class Bad:
    ...     def __init__(self, *_):
    ...         print os.getcwd()
    ...     def install(self):
    ...         print os.getcwd()
    ...         os.chdir('bad_start')
    ...         print os.getcwd()
    ...         return ()
    ... ''')

    >>> write('setup.py',
    ... '''
    ... from setuptools import setup
    ... setup(name='bad.test',
    ...       entry_points={'zc.buildout': ['default=bad_recipe:Bad']},)
    ... ''')
    
    >>> write('buildout.cfg',
    ... '''
    ... [buildout]
    ... develop = .
    ... parts = b1 b2
    ... [b1]
    ... recipe = bad.test
    ... [b2]
    ... recipe = bad.test
    ... ''')

    >>> os.chdir('bad_start')
    >>> print system(join(sample_buildout, 'bin', 'buildout')
    ...              +' -c '+join(sample_buildout, 'buildout.cfg')),
    buildout: Develop: /tmp/tmpV9ptXUbuildoutSetUp/_TEST_/sample-buildout/.
    /sample-buildout
    /sample-buildout
    buildout: Installing b1
    /sample-buildout
    /sample-buildout/bad_start
    buildout: Installing b2
    /sample-buildout
    /sample-buildout/bad_start
    
    """

def bug_61890_file_urls_dont_seem_to_work_in_find_dash_links():
    """
    
    This bug arises from the fact that setuptools is over restrictive
    about file urls, requiring that file urls pointing at directories
    must end in a slash.

    >>> dest = tmpdir('sample-install')
    >>> import zc.buildout.easy_install
    >>> ws = zc.buildout.easy_install.install(
    ...     ['demo==0.2'], dest,
    ...     links=['file://'+sample_eggs], index=link_server+'index/')


    >>> for dist in ws:
    ...     print dist
    demo 0.2
    demoneeded 1.1

    >>> ls(dest)
    -  demo-0.2-py2.4.egg
    -  demoneeded-1.1-py2.4.egg
    
    """

######################################################################
    
def create_sample_eggs(test, executable=sys.executable):
    write = test.globs['write']
    dest = test.globs['sample_eggs']
    tmp = tempfile.mkdtemp()
    try:
        write(tmp, 'README.txt', '')

        for i in (0, 1):
            write(tmp, 'eggrecipedemobeeded.py', 'y=%s\n' % i)
            write(
                tmp, 'setup.py',
                "from setuptools import setup\n"
                "setup(name='demoneeded', py_modules=['eggrecipedemobeeded'],"
                " zip_safe=True, version='1.%s', author='bob', url='bob', "
                "author_email='bob')\n"
                % i
                )
            zc.buildout.testing.sdist(tmp, dest)

        write(
            tmp, 'setup.py',
            "from setuptools import setup\n"
            "setup(name='other', zip_safe=False, version='1.0', "
            "py_modules=['eggrecipedemobeeded'])\n"
            )
        zc.buildout.testing.bdist_egg(tmp, executable, dest)

        os.remove(os.path.join(tmp, 'eggrecipedemobeeded.py'))

        for i in (1, 2, 3):
            write(
                tmp, 'eggrecipedemo.py',
                'import eggrecipedemobeeded\n'
                'x=%s\n'
                'def main(): print x, eggrecipedemobeeded.y\n'
                % i)
            write(
                tmp, 'setup.py',
                "from setuptools import setup\n"
                "setup(name='demo', py_modules=['eggrecipedemo'],"
                " install_requires = 'demoneeded',"
                " entry_points={'console_scripts': "
                     "['demo = eggrecipedemo:main']},"
                " zip_safe=True, version='0.%s')\n" % i
                )
            zc.buildout.testing.bdist_egg(tmp, executable, dest)
    finally:
        shutil.rmtree(tmp)

extdemo_c = """
#include <Python.h>
#include <extdemo.h>

static PyMethodDef methods[] = {{NULL}};

PyMODINIT_FUNC
initextdemo(void)
{
    PyObject *m;
    m = Py_InitModule3("extdemo", methods, "");
#ifdef TWO
    PyModule_AddObject(m, "val", PyInt_FromLong(2));
#else
    PyModule_AddObject(m, "val", PyInt_FromLong(EXTDEMO));
#endif
}
"""

extdemo_setup_py = """
from distutils.core import setup, Extension

setup(name = "extdemo", version = "%s", url="http://www.zope.org",
      author="Demo", author_email="demo@demo.com",
      ext_modules = [Extension('extdemo', ['extdemo.c'])],
      )
"""

def add_source_dist(test, version=1.4):

    if 'extdemo' not in test.globs:
        test.globs['extdemo'] = test.globs['tmpdir']('extdemo')

    tmp = test.globs['extdemo']
    write = test.globs['write']
    try:
        write(tmp, 'extdemo.c', extdemo_c);
        write(tmp, 'setup.py', extdemo_setup_py % version);
        write(tmp, 'README', "");
        write(tmp, 'MANIFEST.in', "include *.c\n");
        test.globs['sdist'](tmp, test.globs['sample_eggs'])
    except:
        shutil.rmtree(tmp)

def easy_install_SetUp(test):
    zc.buildout.testing.buildoutSetUp(test)
    sample_eggs = test.globs['tmpdir']('sample_eggs')
    test.globs['sample_eggs'] = sample_eggs
    os.mkdir(os.path.join(sample_eggs, 'index'))
    create_sample_eggs(test)
    add_source_dist(test)
    test.globs['link_server'] = test.globs['start_server'](
        test.globs['sample_eggs'])
    test.globs['update_extdemo'] = lambda : add_source_dist(test, 1.5)
    zc.buildout.testing.install_develop('zc.recipe.egg', test)
        
egg_parse = re.compile('([0-9a-zA-Z_.]+)-([0-9a-zA-Z_.]+)-py(\d[.]\d).egg$'
                       ).match
def makeNewRelease(project, ws, dest):
    dist = ws.find(pkg_resources.Requirement.parse(project))
    eggname, oldver, pyver = egg_parse(
        os.path.basename(dist.location)
        ).groups()
    dest = os.path.join(dest, "%s-99.99-py%s.egg" % (eggname, pyver)) 
    if os.path.isfile(dist.location):
        shutil.copy(dist.location, dest)
        zip = zipfile.ZipFile(dest, 'a')
        zip.writestr(
            'EGG-INFO/PKG-INFO',
            zip.read('EGG-INFO/PKG-INFO').replace("Version: %s" % oldver, 
                                                  "Version: 99.99")
            )
        zip.close()
    else:
        shutil.copytree(dist.location, dest)
        info_path = os.path.join(dest, 'EGG-INFO', 'PKG-INFO')
        info = open(info_path).read().replace("Version: %s" % oldver, 
                                              "Version: 99.99")
        open(info_path, 'w').write(info)


def updateSetup(test):
    zc.buildout.testing.buildoutSetUp(test)
    new_releases = test.globs['tmpdir']('new_releases')
    test.globs['new_releases'] = new_releases
    sample_buildout = test.globs['sample_buildout']
    eggs = os.path.join(sample_buildout, 'eggs')

    # If the zc.buildout dist is a develo dist, convert it to a
    # regular egg in the sample buildout
    req = pkg_resources.Requirement.parse('zc.buildout')
    dist = pkg_resources.working_set.find(req)
    if dist.precedence == pkg_resources.DEVELOP_DIST:
        # We have a develop egg, create a real egg for it:
        here = os.getcwd()
        os.chdir(os.path.dirname(dist.location))
        assert os.spawnle(
            os.P_WAIT, sys.executable, sys.executable,
            os.path.join(os.path.dirname(dist.location), 'setup.py'),
            '-q', 'bdist_egg', '-d', eggs,
            dict(os.environ,
                 PYTHONPATH=pkg_resources.working_set.find(
                               pkg_resources.Requirement.parse('setuptools')
                               ).location,
                 ),
            ) == 0
        os.chdir(here)
        os.remove(os.path.join(eggs, 'zc.buildout.egg-link'))

        # Rebuild the buildout script
        ws = pkg_resources.WorkingSet([eggs])
        ws.require('zc.buildout')
        zc.buildout.easy_install.scripts(
            ['zc.buildout'], ws, sys.executable,
            os.path.join(sample_buildout, 'bin'))
    else:
        ws = pkg_resources.working_set

    # now let's make the new releases
    makeNewRelease('zc.buildout', ws, new_releases)
    makeNewRelease('setuptools', ws, new_releases)

    os.mkdir(os.path.join(new_releases, 'zc.buildout'))
    os.mkdir(os.path.join(new_releases, 'setuptools'))

    
    
normalize_bang = (
    re.compile(re.escape('#!'+sys.executable)),
    '#!/usr/local/bin/python2.4',
    )

def test_suite():
    import zc.buildout.testselectingpython
    suite = unittest.TestSuite((
        doctest.DocFileSuite(
            'buildout.txt', 'runsetup.txt', 'repeatable.txt',
            setUp=zc.buildout.testing.buildoutSetUp,
            tearDown=zc.buildout.testing.buildoutTearDown,
            checker=renormalizing.RENormalizing([
               zc.buildout.testing.normalize_path,
               zc.buildout.testing.normalize_script,
               zc.buildout.testing.normalize_egg_py,
               (re.compile('__buildout_signature__ = recipes-\S+'),
                '__buildout_signature__ = recipes-SSSSSSSSSSS'),
               (re.compile('executable = \S+python\S*'),
                'executable = python'),
               (re.compile('[-d]  setuptools-\S+[.]egg'), 'setuptools.egg'),
               (re.compile('zc.buildout(-\S+)?[.]egg(-link)?'),
                'zc.buildout.egg'),
               (re.compile('creating \S*setup.cfg'), 'creating setup.cfg'),
               (re.compile('hello\%ssetup' % os.path.sep), 'hello/setup'),
               (re.compile('zc.buildout.easy_install.picked: (\S+) = \S+'),
                'picked \\1 = V.V'),
               ])
            ),
        doctest.DocFileSuite(
            'debugging.txt',
            setUp=zc.buildout.testing.buildoutSetUp,
            tearDown=zc.buildout.testing.buildoutTearDown,
            checker=renormalizing.RENormalizing([
               zc.buildout.testing.normalize_path,
               (re.compile(r'\S+buildout.py'), 'buildout.py'),
               (re.compile(r'line \d+'), 'line NNN'),
               (re.compile(r'py\(\d+\)'), 'py(NNN)'),
               ])
            ),

        doctest.DocFileSuite(
            'update.txt',
            setUp=updateSetup,
            tearDown=zc.buildout.testing.buildoutTearDown,
            checker=renormalizing.RENormalizing([
               zc.buildout.testing.normalize_path,
               zc.buildout.testing.normalize_script,
               zc.buildout.testing.normalize_egg_py,
               normalize_bang,
               (re.compile('99[.]99'), 'NINETYNINE.NINETYNINE'),
               (re.compile('(zc.buildout|setuptools)-\d+[.]\d+\S*'
                           '-py\d.\d.egg'),
                '\\1.egg'),
               (re.compile('(zc.buildout|setuptools)( version)? \d+[.]\d+\S*'),
                '\\1 V.V'),
               (re.compile('[-d]  setuptools'), '-  setuptools'),
               ])
            ),
        
        doctest.DocFileSuite(
            'easy_install.txt', 'downloadcache.txt',
            setUp=easy_install_SetUp,
            tearDown=zc.buildout.testing.buildoutTearDown,

            checker=renormalizing.RENormalizing([
               zc.buildout.testing.normalize_path,
               zc.buildout.testing.normalize_script,
               zc.buildout.testing.normalize_egg_py,
               normalize_bang,
               (re.compile('extdemo[.]pyd'), 'extdemo.so')
               ]),
            ),
        doctest.DocTestSuite(
            setUp=easy_install_SetUp,
            tearDown=zc.buildout.testing.buildoutTearDown,
            checker=renormalizing.RENormalizing([
               zc.buildout.testing.normalize_path,
               zc.buildout.testing.normalize_script,
               zc.buildout.testing.normalize_egg_py,
               (re.compile("buildout: Running \S*setup.py"),
                'buildout: Running setup.py'),
               (re.compile('setuptools-\S+-'),
                'setuptools.egg'),
               (re.compile('zc.buildout-\S+-'),
                'zc.buildout.egg'),
               (re.compile('File "\S+one.py"'),
                'File "one.py"'),
               ]),
            ),
        ))

    if sys.version_info[:2] != (2, 3):
        # Only run selecting python tests if not 2.3, since
        # 2.3 is the alternate python used in the tests.
        suite.addTest(zc.buildout.testselectingpython.test_suite())

    return suite
