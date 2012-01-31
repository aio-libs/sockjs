""" iframe-htmlfile transport """
import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest, HTTPServerError

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs.transports import StopStreaming
from pyramid_sockjs.protocol import HEARTBEAT
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame

from .utils import get_messages, session_cookie, cors_headers


PRELUDE = r"""
<!doctype html>
<html><head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head><body><h2>Don't panic!</h2>
  <script>
    document.domain = document.domain;
    var c = parent.%s;
    c.start();
    function p(d) {c.message(d);};
    window.onload = function() {c.stop();};
  </script>
""".strip()


class HTMLFileTransport(Response):

    timing = 5.0
    maxsize = 131072 # 128K bytes

    def __init__(self, session, request):
        response = request.response
        self.__dict__.update(response.__dict__)
        self.session = session
        self.request = request

        self.headers = (
            ('Content-Type', 'text/html; charset=UTF-8'),
            ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'),
            ("Connection", "close"),
            session_cookie(request),
            ) + cors_headers(request)

    def __call__(self, environ, start_response):
        request = self.request
        callback = request.GET.get('c', None)
        if callback is None:
            self.status = 500
            self.body = '"callback" parameter required'
            return super(HTMLFileTransport, self).__call__(
                environ, start_response)

        write = start_response(self.status, self.headerlist)
        prelude = PRELUDE % callback
        prelude += ' ' * 1024
        write(prelude)

        timing = self.timing
        session = self.session

        if session.state == STATE_NEW:
            write('<script>\np("o");\n</script>\r\n')
            session.open()

        size = 0

        try:
            while True:
                try:
                    message = [session.get_transport_message(timeout=timing)]
                except Empty:
                    message = HEARTBEAT
                    session.heartbeat()
                else:
                    message = message_frame(message)

                if session.state == STATE_CLOSING:
                    write("<script>\np(%s);\n</script>\r\n" %
                          encode(close_frame('Go away!')))
                    session.closed()
                    break

                message = "<script>\np(%s);\n</script>\r\n" % encode(message)
                try:
                    write(message)
                except:
                    session.closed()
                    raise StopStreaming()

                size += len(message)
                if size > self.maxsize:
                    break
        finally:
            session.release()

        return []
