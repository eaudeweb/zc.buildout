"""\
Cross-version helper functions.

"""
__docformat__ = "reStructuredText"

import sys


# We can't use print as a function in Python before 2.6, so we'll create
# a new name for it.  This is otherwise the equivalent of the Python 3
# print() function.

def write(*args, **kw):
    sep = kw.pop("sep", " ")
    end = kw.pop("end", "\n")
    file = kw.pop("file", sys.stdout)
    file.write(sep.join([str(v) for v in args]), + end)
