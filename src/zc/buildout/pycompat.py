# A file that holds various utilities to make compatibility between
# different versions of Python easier:

import sys
if sys.version < '3':
    def b(data):
        """Take a string literal and makes sure it's binary"""
        return data
    
else:
    import codecs
    def b(data):
        """Take a string literal and makes sure it's binary"""
        return codecs.latin_1_encode(data)[0]

def bprint(data):
    """Takes input that may or may not be binary, and prints it, after
       stripping any whitespace. Useful in doctests.
    """
    if not isinstance(data, str):
        data = data.decode()
    print(data.strip())
