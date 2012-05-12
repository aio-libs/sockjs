import logging
import pyramid_sockjs
from gevent.pywsgi import WSGIHandler
from pyramid_sockjs.transports import StopStreaming

orig_get_environ = WSGIHandler.get_environ
orig_handle_error = WSGIHandler.handle_error


def handle_error(self, type, value, tb): # pragma: no cover
    if issubclass(type, StopStreaming):
        del tb
        return

    return orig_handle_error(self, type, value, tb)


def get_environ(self): # pragma: no cover
    env = orig_get_environ(self)
    env['gunicorn.socket'] = self.socket
    return env


def patch_gevent(): # pragma: no cover
    log = logging.getLogger('pyramid_sockjs')

    if WSGIHandler.handle_error is handle_error:
        # skip patch
        return

    WSGIHandler.get_environ = get_environ
    WSGIHandler.handle_error = handle_error

    log.info('Patching gevent WSGIHandler.get_environ')
    log.info('Patching gevent WSGIHandler.handle_error')
