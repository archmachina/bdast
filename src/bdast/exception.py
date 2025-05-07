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

class BdastArgumentException(Exception):
    """
    Invalid argument supplied to a bdast function
    """

class BdastLoadException(Exception):
    """
    Error parsing or loading the bdast specification
    """

class BdastRunException(Exception):
    """
    Runtime error encountered while processing the bdast specification
    """

