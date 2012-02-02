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
    if 'HTTP_CONNECTION' not in env:
        env['HTTP_CONNECTION'] = self.headers.get('Connection','')
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


###################
# gunicorn
###################

try:
    import gunicorn.util as util
except ImportError: # pragma: no cover
    pass


def default_headers(self): # pragma: no cover
    headers = [
        "HTTP/%s.%s %s\r\n" % (self.req.version[0],
                               self.req.version[1], self.status),
        "Server: %s\r\n" % self.version,
        "Date: %s\r\n" % util.http_date(),
        ]

    if not self.has_connection:
        connection = "keep-alive"
        if self.should_close():
            connection = "close"
        headers.append("Connection: %s\r\n" % connection)

    if self.chunked:
        headers.append("Transfer-Encoding: chunked\r\n")
    return headers

def process_headers(self, headers): # pragma: no cover
    for name, value in headers:
        assert isinstance(name, basestring), "%r is not a string" % name
        lname = name.lower().strip()
        if lname == "content-length":
            self.response_length = int(value)
        elif util.is_hoppish(name):
            if lname == "connection":
                # handle websocket
                if value.lower().strip() != "upgrade":
                    continue
                else:
                    self.has_connection = True
            elif lname == "upgrade":
                if value.lower().strip() != "websocket":
                    continue
            else:
                # ignore hopbyhop headers
                continue
        self.headers.append((name.strip(), str(value).strip()))


def patch_gunicorn(): # pragma: no cover
    try:
        from gunicorn.http.wsgi import Response
    except ImportError:
        return

    Response.has_connection = False
    Response.default_headers = default_headers
    Response.process_headers = process_headers
