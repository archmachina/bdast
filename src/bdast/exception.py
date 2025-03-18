"""
Contains common exceptions used by bdast
"""


class SpecLoadException(Exception):
    """
    Exception representing an error with the loading of the yaml specification file
    """


class SpecRunException(Exception):
    """
    Exception during processing of the specification actions or steps
    """
