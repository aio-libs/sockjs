"""Exceptions"""


class SockjsException(Exception):
    """Base sockjs exception."""


class SessionIsAcquired(SockjsException):
    """Session is acquired."""


class SessionIsClosed(SockjsException):
    """Session is closed."""
