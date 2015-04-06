"""Exceptions"""


class SockjsException(Exception):
    """ Base sockjs exception """


class SessionIsAcquired(SockjsException):
    """ Session is acquired """


class WebSocketError(SockjsException):
    pass


class FrameTooLargeException(WebSocketError):
    pass
