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
"""Various test-support utility functions

$Id$
"""


import BaseHTTPServer, ConfigParser, os, random, re, shutil, socket, sys
import tempfile, threading, time, urllib2, unittest

from zope.testing import doctest, renormalizing
import pkg_resources

import zc.buildout.buildout
import zc.buildout.easy_install

fsync = getattr(os, 'fsync', lambda fileno: None)

setuptools_location = pkg_resources.working_set.find(
    pkg_resources.Requirement.parse('setuptools')).location

def cat(dir, *names):
    path = os.path.join(dir, *names)
    if (not os.path.exists(path)
        and sys.platform == 'win32'
        and os.path.exists(path+'-script.py')
        ):
        path = path+'-script.py'
    print open(path).read(),

def ls(dir, *subs):
    if subs:
        dir = os.path.join(dir, *subs)
    names = os.listdir(dir)
    names.sort()
    for name in names:
        if os.path.isdir(os.path.join(dir, name)):
            print 'd ',
        else:
            print '- ',
        print name

def mkdir(*path):
    os.mkdir(os.path.join(*path))

def remove(*path):
    path = os.path.join(*path)
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

def rmdir(*path):
    shutil.rmtree(os.path.join(*path))

def write(dir, *args):
    path = os.path.join(dir, *(args[:-1]))
    f = open(path, 'w')
    f.write(args[-1])
    f.flush()
    fsync(f.fileno())
    f.close()

def system(command, input=''):
    i, o = os.popen4(command)
    if input:
        i.write(input)
    i.close()
    return o.read()

def get(url):
    return urllib2.urlopen(url).read()

def _runsetup(setup, executable, *args):
    if os.path.isdir(setup):
        setup = os.path.join(setup, 'setup.py')
    d = os.path.dirname(setup)

    args = [zc.buildout.easy_install._safe_arg(arg)
            for arg in args]
    args.insert(0, '-q')
    args.append(dict(os.environ, PYTHONPATH=setuptools_location))

    here = os.getcwd()
    try:
        os.chdir(d)
        os.spawnle(os.P_WAIT, executable, executable, setup, *args)
        if os.path.exists('build'):
            shutil.rmtree('build')
    finally:
        os.chdir(here)

def sdist(setup, dest):
    _runsetup(setup, sys.executable, 'sdist', '-d', dest, '--formats=zip')

def bdist_egg(setup, executable, dest):
    _runsetup(setup, executable, 'bdist_egg', '-d', dest)

def find_python(version):
    e = os.environ.get('PYTHON%s' % version)
    if e is not None:
        return e
    if sys.platform == 'win32':
        e = '\Python%s%s\python.exe' % tuple(version.split('.'))
        if os.path.exists(e):
            return e
    else:
        i, o = os.popen4('python%s -c "import sys; print sys.executable"'
                         % version)
        i.close()
        e = o.read().strip()
        o.close()
        if os.path.exists(e):
            return e
        i, o = os.popen4(
            'python -c "import sys; print \'%s.%s\' % sys.version_info[:2]"'
            )
        i.close()
        e = o.read().strip()
        o.close()
        if e == version:
            i, o = os.popen4('python -c "import sys; print sys.executable"')
            i.close()
            e = o.read().strip()
            o.close()
            if os.path.exists(e):
                return e
        
    raise ValueError(
        "Couldn't figure out the executable for Python %(version)s.\n"
        "Set the environment variable PYTHON%(version)s to the location\n"
        "of the Python %(version)s executable before running the tests."
        )

def buildoutSetUp(test):

    test.globs['__tear_downs'] = __tear_downs = []
    test.globs['register_teardown'] = register_teardown = __tear_downs.append

    here = os.getcwd()
    register_teardown(lambda: os.chdir(here))

    old_home = os.environ.get('HOME')
    if old_home is not None:
        del os.environ['HOME'] # pop doesn't truly remove it :(
        register_teardown(lambda: os.environ.__setitem__('HOME', old_home))

    base = tempfile.mkdtemp('buildoutSetUp')
    register_teardown(lambda base=base: shutil.rmtree(base))
    base = os.path.join(base, '_TEST_')
    os.mkdir(base)

    tmp = tempfile.mkdtemp('buildouttests')
    register_teardown(lambda: shutil.rmtree(tmp))
    
    zc.buildout.easy_install.default_index_url = 'file://'+tmp
    os.environ['buildout-testing-index-url'] = (
        zc.buildout.easy_install.default_index_url)

    def tmpdir(name):
        path = os.path.join(base, name)
        mkdir(path)
        return path

    sample = tmpdir('sample-buildout')

    os.chdir(sample)

    # Create a basic buildout.cfg to avoid a warning from buildout:
    open('buildout.cfg', 'w').write(
        "[buildout]\nparts =\n"
        )

    # Use the buildout bootstrap command to create a buildout
    zc.buildout.buildout.Buildout(
        'buildout.cfg',
        [('buildout', 'log-level', 'WARNING'),
         # trick bootstrap into putting the buildout develop egg
         # in the eggs dir.
         ('buildout', 'develop-eggs-directory', 'eggs'),
         ]
        ).bootstrap([])
    
    # Create the develop-eggs dir, which didn't get created the usual
    # way due to thr trick above:
    os.mkdir('develop-eggs')

    def start_server(path):
        port, thread = _start_server(path, name=path)
        url = 'http://localhost:%s/' % port
        register_teardown(lambda: stop_server(url, thread))
        return url

    test.globs.update(dict(
        sample_buildout = sample,
        ls = ls,
        cat = cat,
        mkdir = mkdir,
        rmdir = rmdir,
        remove = remove,
        tmpdir = tmpdir,
        write = write,
        system = system,
        get = get,
        cd = (lambda *path: os.chdir(os.path.join(*path))),
        join = os.path.join,
        sdist = sdist,
        bdist_egg = bdist_egg,
        start_server = start_server,
        buildout = os.path.join(sample, 'bin', 'buildout'),
        ))

def buildoutTearDown(test):
    for f in test.globs['__tear_downs']:
        f()
    
class Server(BaseHTTPServer.HTTPServer):

    def __init__(self, tree, *args):
        BaseHTTPServer.HTTPServer.__init__(self, *args)
        self.tree = os.path.abspath(tree)

    __run = True
    def serve_forever(self):
        while self.__run:
            self.handle_request()

    def handle_error(self, *_):
        self.__run = False

class Handler(BaseHTTPServer.BaseHTTPRequestHandler):

    Server.__log = False

    def __init__(self, request, address, server):
        self.__server = server
        self.tree = server.tree
        BaseHTTPServer.BaseHTTPRequestHandler.__init__(
            self, request, address, server)

    def do_GET(self):
        if '__stop__' in self.path:
            raise SystemExit
        
        if self.path == '/enable_server_logging':
            self.__server.__log = True
            self.send_response(200)
            return
            
        if self.path == '/disable_server_logging':
            self.__server.__log = False
            self.send_response(200)
            return

        path = os.path.abspath(os.path.join(self.tree, *self.path.split('/')))
        if not (
            ((path == self.tree) or path.startswith(self.tree+os.path.sep))
            and
            os.path.exists(path)
            ):
            self.send_response(404, 'Not Found')
            #self.send_response(200)
            out = '<html><body>Not Found</body></html>'
            #out = '\n'.join(self.tree, self.path, path)
            self.send_header('Content-Length', str(len(out)))
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(out)
            return

        self.send_response(200)
        if os.path.isdir(path):
            out = ['<html><body>\n']
            names = os.listdir(path)
            names.sort()
            for name in names:
                if os.path.isdir(os.path.join(path, name)):
                    name += '/'
                out.append('<a href="%s">%s</a><br>\n' % (name, name))
            out.append('</body></html>\n')
            out = ''.join(out)
            self.send_header('Content-Length', str(len(out)))
            self.send_header('Content-Type', 'text/html')
        else:
            out = open(path, 'rb').read()
            self.send_header('Content-Length', len(out))
            if path.endswith('.egg'):
                self.send_header('Content-Type', 'application/zip')
            elif path.endswith('.gz'):
                self.send_header('Content-Type', 'application/x-gzip')
            elif path.endswith('.zip'):
                self.send_header('Content-Type', 'application/x-gzip')
            else:
                self.send_header('Content-Type', 'text/html')
        self.end_headers()

        self.wfile.write(out)
                
    def log_request(self, code):
        if self.__server.__log:
            print '%s %s %s' % (self.command, code, self.path)

def _run(tree, port):
    server_address = ('localhost', port)
    httpd = Server(tree, server_address, Handler)
    httpd.serve_forever()

def get_port():
    for i in range(10):
        port = random.randrange(20000, 30000)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                s.connect(('localhost', port))
            except socket.error:
                return port
        finally:
            s.close()
    raise RuntimeError, "Can't find port"

def _start_server(tree, name=''):
    port = get_port()
    thread = threading.Thread(target=_run, args=(tree, port), name=name)
    thread.setDaemon(True)
    thread.start()
    wait(port, up=True)
    return port, thread

def start_server(tree):
    return _start_server(tree)[0]

def stop_server(url, thread=None):
    try:
        urllib2.urlopen(url+'__stop__')
    except Exception:
        pass
    if thread is not None:
        thread.join() # wait for thread to stop

def wait(port, up):
    addr = 'localhost', port
    for i in range(120):
        time.sleep(0.25)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(addr)
            s.close()
            if up:
                break
        except socket.error, e:
            if e[0] not in (errno.ECONNREFUSED, errno.ECONNRESET):
                raise
            s.close()
            if not up:
                break
    else:
        if up:
            raise
        else:
            raise SystemError("Couln't stop server")

def install(project, destination):
    if not isinstance(destination, basestring):
        destination = os.path.join(destination.globs['sample_buildout'],
                                   'eggs')

    dist = pkg_resources.working_set.find(
        pkg_resources.Requirement.parse(project))
    if dist.location.endswith('.egg'):
        destination = os.path.join(destination,
                                   os.path.basename(dist.location),
                                   )
        if os.path.isdir(dist.location):
            shutil.copytree(dist.location, destination)
        else:
            shutil.copyfile(dist.location, destination)
    else:
        # copy link
        open(os.path.join(destination, project+'.egg-link'), 'w'
             ).write(dist.location)

def install_develop(project, destination):
    if not isinstance(destination, basestring):
        destination = os.path.join(destination.globs['sample_buildout'],
                                   'develop-eggs')

    dist = pkg_resources.working_set.find(
        pkg_resources.Requirement.parse(project))
    open(os.path.join(destination, project+'.egg-link'), 'w'
         ).write(dist.location)

def _normalize_path(match):
    path = match.group(1)
    if os.path.sep == '\\':
        path = path.replace('\\\\', '/')
        if path.startswith('\\'):
            path = path[1:]
    return '/' + path.replace(os.path.sep, '/')
    
normalize_path = (
    re.compile(
        r'''[^'" \t\n\r]+\%(sep)s_[Tt][Ee][Ss][Tt]_\%(sep)s([^"' \t\n\r]+)'''
        % dict(sep=os.path.sep)),
    _normalize_path,
    )

normalize_script = (
    re.compile('(\n?)-  ([a-zA-Z_.-]+)-script.py\n-  \\2.exe\n'),
    '\\1-  \\2\n')

normalize_egg_py = (
    re.compile('-py\d[.]\d(-\S+)?.egg'),
    '-pyN.N.egg',
    )
