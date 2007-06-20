Installation of distributions as eggs
=====================================

The zc.recipe.egg:eggs recipe can be used to install various types if
distutils distributions as eggs.  It takes a number of options:

eggs
    A list of eggs to install given as one or more setuptools
    requirement strings.  Each string must be given on a separate
    line.

find-links
   A list of URLs, files, or directories to search for distributions.

index
   The URL of an index server, or almost any other valid URL. :)

   If not specified, the Python Package Index,
   http://cheeseshop.python.org/pypi, is used.  You can specify an
   alternate index with this option.  If you use the links option and
   if the links point to the needed distributions, then the index can
   be anything and will be largely ignored.  In the examples, here,
   we'll just point to an empty directory on our link server.  This
   will make our examples run a little bit faster.

python
   The name of a section to get the Python executable from.
   If not specified, then the buildout python option is used.  The
   Python executable is found in the executable option of the named
   section.

We have a link server that has a number of distributions:

    >>> print get(link_server),
    <html><body>
    <a href="demo-0.1-py2.3.egg">demo-0.1-py2.3.egg</a><br>
    <a href="demo-0.2-py2.3.egg">demo-0.2-py2.3.egg</a><br>
    <a href="demo-0.3-py2.3.egg">demo-0.3-py2.3.egg</a><br>
    <a href="demoneeded-1.0.zip">demoneeded-1.0.zip</a><br>
    <a href="demoneeded-1.1.zip">demoneeded-1.1.zip</a><br>
    <a href="extdemo-1.4.zip">extdemo-1.4.zip</a><br>
    <a href="index/">index/</a><br>
    <a href="other-1.0-py2.3.egg">other-1.0-py2.3.egg</a><br>
    </body></html>

We have a sample buildout.  Let's update it's configuration file to
install the demo package.

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg:eggs
    ... eggs = demo<0.3
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... """ % dict(server=link_server))

In this example, we limited ourselves to revisions before 0.3. We also
specified where to find distributions using the find-links option.

Let's run the buildout:

    >>> import os
    >>> print system(buildout),
    Installing demo.
    Getting distribution for 'demo<0.3'.
    Got demo 0.2.
    Getting distribution for 'demoneeded'.
    Got demoneeded 1.1.

Now, if we look at the buildout eggs directory:

    >>> ls(sample_buildout, 'eggs')
    -  demo-0.2-py2.3.egg
    -  demoneeded-1.1-py2.3.egg
    -  setuptools-0.6-py2.3.egg
    -  zc.buildout-1.0-py2.3.egg

We see that we got an egg for demo that met the requirement, as well
as the egg for demoneeded, which demo requires.  (We also see an egg
link for the recipe in the develop-eggs directory.  This egg link was
actually created as part of the sample buildout setup. Normally, when
using the recipe, you'll get a regular egg installation.)

Script generation
-----------------

The demo egg defined a script, but we didn't get one installed:

    >>> ls(sample_buildout, 'bin')
    -  buildout

If we want scripts provided by eggs to be installed, we should use the 
scripts recipe:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg:scripts
    ... eggs = demo<0.3
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... """ % dict(server=link_server))

    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/demo'.

Now we also see the script defined by the dmo script:

    >>> ls(sample_buildout, 'bin')
    -  buildout
    -  demo

The scripts recipe defines some additional options:

entry-points
   A list of entry-point identifiers of the form name=module#attrs,
   name is a script name, module is a module name, and a attrs is a
   (possibly dotted) name of an object wihin the module.  This option
   is useful when working with distributions that don't declare entry
   points, such as distributions not written to work with setuptools.

scripts
   Control which scripts are generated.  The value should be a list of
   zero or more tokens.  Each token is either a name, or a name
   followed by an '=' and a new name.  Only the named scripts are
   generated.  If no tokens are given, then script generation is
   disabled.  If the option isn't given at all, then all scripts
   defined by the named eggs will be generated.

interpreter
   The name of a script to generate that allows access to a Python
   interpreter that has the path set based on the eggs installed.

extra-paths
   Extra paths to include in a generates script.

initialization
   Specify some Python initialization code.  This is very limited.  In
   particular, be aware that leading whitespace is stripped from the
   code given.

arguments
   Specify some arguments to be passed to entry points as Python source.

Let's add an interpreter option:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... eggs = demo<0.3
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... interpreter = py-demo
    ... """ % dict(server=link_server))

Note that we ommitted the entry point name from the recipe
specification. We were able to do this because the scripts recipe if
the default entry point for the zc.recipe.egg egg.

   >>> print system(buildout),
   Uninstalling demo.
   Installing demo.
   Generated script '/sample-buildout/bin/demo'.
   Generated interpreter '/sample-buildout/bin/py-demo'.

Now we also get a py-demo script for giving us a Python prompt with
the path for demo and any eggs it depends on included in sys.path.
This is useful for debugging and testing.

    >>> ls(sample_buildout, 'bin')
    -  buildout
    -  demo
    -  py-demo

If we run the demo script, it prints out some minimal data:

    >>> print system(join(sample_buildout, 'bin', 'demo')),
    2 1

The value it prints out happens to be some values defined in the
modules installed.

We can also run the py-demo script.  Here we'll just print out
the bits if the path added to reflect the eggs:

    >>> print system(join(sample_buildout, 'bin', 'py-demo'),
    ... """import os, sys
    ... for p in sys.path:
    ...     if 'demo' in p:
    ...         print os.path.basename(p)
    ...
    ... """).replace('>>> ', '').replace('... ', ''),
    ... # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    demo-0.2-py2.4.egg
    demoneeded-1.1-py2.4.egg

Egg updating
------------

The recipe normally gets the most recent distribution that satisfies the
specification.  It won't do this is the buildout is either in
non-newest mode or in offline mode.  To see how this works, we'll
remove the restriction on demo:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... """ % dict(server=link_server))

and run the buildout in non-newest mode:

    >>> print system(buildout+' -N'),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/demo'.

Note that we removed the eggs option, and the eggs defaulted to the
part name. Because we removed the eggs option, the demo was
reinstalled.

We'll also run the buildout in off-line mode:

    >>> print system(buildout+' -o'),
    Updating demo.

We didn't get an update for demo:

    >>> ls(sample_buildout, 'eggs')
    -  demo-0.2-py2.3.egg
    -  demoneeded-1.1-py2.3.egg
    -  setuptools-0.6-py2.3.egg
    -  zc.buildout-1.0-py2.3.egg

If we run the buildout on the default online and newest modes, 
we'll get an update for demo:

    >>> print system(buildout),
    Updating demo.
    Getting distribution for 'demo'.
    Got demo 0.3.
    Generated script '/sample-buildout/bin/demo'.

Then we'll get a new demo egg:

    >>> ls(sample_buildout, 'eggs')
    -  demo-0.2-py2.3.egg
    -  demo-0.3-py2.3.egg
    -  demoneeded-1.1-py2.3.egg
    -  setuptools-0.6-py2.4.egg
    -  zc.buildout-1.0-py2.4.egg

The script is updated too:

    >>> print system(join(sample_buildout, 'bin', 'demo')),
    3 1

Controlling script generation
-----------------------------

You can control which scripts get generated using the scripts option.
For example, to suppress scripts, use the scripts option without any
arguments:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... scripts =
    ... """ % dict(server=link_server))


    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.

    >>> ls(sample_buildout, 'bin')
    -  buildout

You can also control the name used for scripts:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... scripts = demo=foo
    ... """ % dict(server=link_server))

    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/foo'.

    >>> ls(sample_buildout, 'bin')
    -  buildout
    -  foo

Specifying extra script paths
-----------------------------

If we need to include extra paths in a script, we can use the
extra-paths option:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... scripts = demo=foo
    ... extra-paths =
    ...    /foo/bar
    ...    /spam/eggs
    ... """ % dict(server=link_server))

    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/foo'.

Let's look at the script that was generated:

    >>> cat(sample_buildout, 'bin', 'foo') # doctest: +NORMALIZE_WHITESPACE
    #!/usr/local/bin/python2.4
    <BLANKLINE>
    import sys
    sys.path[0:0] = [
      '/sample-buildout/eggs/demo-0.3-py2.4.egg',
      '/sample-buildout/eggs/demoneeded-1.1-py2.4.egg',
      '/foo/bar',
      '/spam/eggs',
      ]
    <BLANKLINE>
    import eggrecipedemo
    <BLANKLINE>
    if __name__ == '__main__':
        eggrecipedemo.main()

Specifying initialialization code and arguments
-----------------------------------------------

Sometimes, we ned to do more than just calling entry points.  We can
use the initialialization and arguments options to specify extra code
to be included in generated scripts:


    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... scripts = demo=foo
    ... extra-paths =
    ...    /foo/bar
    ...    /spam/eggs
    ... initialization = a = (1, 2
    ...                       3, 4)
    ... arguments = a, 2
    ... """ % dict(server=link_server))

    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/foo'.

    >>> cat(sample_buildout, 'bin', 'foo') # doctest: +NORMALIZE_WHITESPACE
    #!/usr/local/bin/python2.4
    <BLANKLINE>
    import sys
    sys.path[0:0] = [
      '/sample-buildout/eggs/demo-0.3-py2.4.egg',
      '/sample-buildout/eggs/demoneeded-1.1-py2.4.egg',
      '/foo/bar',
      '/spam/eggs',
      ]
    <BLANKLINE>
    a = (1, 2
    3, 4)
    <BLANKLINE>
    import eggrecipedemo
    <BLANKLINE>
    if __name__ == '__main__':
        eggrecipedemo.main(a, 2)

Here we see that the initialization code we specified was added after
setting the path.  Note, as mentioennd above, that leading whitespace
has been stripped.  Similarly, the argument code we specified was
added in the entry point call (to main).

Specifying entry points
-----------------------

Scripts can be generated for entry points declared explicitly.  We can
declare entry points using the entry-points option:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... find-links = %(server)s
    ... index = %(server)s/index
    ... extra-paths =
    ...    /foo/bar
    ...    /spam/eggs
    ... entry-points = alt=eggrecipedemo:alt other=foo.bar:a.b.c
    ... """ % dict(server=link_server))

    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/demo'.
    Generated script '/sample-buildout/bin/alt'.
    Generated script '/sample-buildout/bin/other'.

    >>> ls(sample_buildout, 'bin')
    -  alt
    -  buildout
    -  demo
    -  other

    >>> cat(sample_buildout, 'bin', 'other')
    #!/usr/local/bin/python2.4
    <BLANKLINE>
    import sys
    sys.path[0:0] = [
      '/sample-buildout/eggs/demo-0.3-py2.4.egg',
      '/sample-buildout/eggs/demoneeded-1.1-py2.4.egg',
      '/foo/bar',
      '/spam/eggs',
      ]
    <BLANKLINE>
    import foo.bar
    <BLANKLINE>
    if __name__ == '__main__':
        foo.bar.a.b.c()

Offline mode
------------

If the buildout offline option is set to "true", then no attempt will
be made to contact an index server:

    >>> write(sample_buildout, 'buildout.cfg',
    ... """
    ... [buildout]
    ... parts = demo
    ... offline = true
    ...
    ... [demo]
    ... recipe = zc.recipe.egg
    ... index = eek!
    ... scripts = demo=foo
    ... """ % dict(server=link_server))

    >>> print system(buildout),
    Uninstalling demo.
    Installing demo.
    Generated script '/sample-buildout/bin/foo'.
