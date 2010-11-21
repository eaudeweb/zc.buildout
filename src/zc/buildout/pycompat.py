# A file that holds various utilities to make compatibility between
# different versions of Python easier:

import sys
if sys.version < '3':
    def b(x):
        return x
else:
    import codecs
    def b(x):
        return codecs.latin_1_encode(x)[0]
