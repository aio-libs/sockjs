import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest
from pyramid_sockjs.transports import StreamingStop
from pyramid_sockjs.protocol import OPEN, MESSAGE, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame


def XHRStreamingTransport(session, request,
                          INIT_STREAM = 'h' *  2048 + '\n' + OPEN):
    meth = request.method
    request.response.headers = (
        ('Content-Type', 'application/javascript; charset=UTF-8'),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Credentials", "true"),
        ("Access-Control-Allow-Methods", "POST, GET, OPTIONS"),
        ("Access-Control-Max-Age", 3600),
        ("Connection", "close"))

    if not session.connected and not session.expired:
        session.open()
        return StreamingResponse(request.response, session, INIT_STREAM)

    elif meth in ('GET', 'POST'):
        return StreamingResponse(request.response, session)

    else:
        raise Exception("No support for such method: %s"%meth)


class StreamingResponse(Response):

    TIMING = 5.0

    def __init__(self, response, session, start=''):
        self.__dict__.update(response.__dict__)
        self.session = session
        self.start = start

    def __call__(self, environ, start_response):
        write = start_response(
            self.status, self._abs_headerlist(environ))
        write(self.start)

        timing = self.TIMING
        session = self.session

        while True:
            try:
                message = session.get_transport_message(timeout=timing)
                if message is None:
                    session.close()
                    raise StopIteration()
            except Empty:
                message = HEARTBEAT
                session.heartbeat()
            else:
                message = message_frame(message)

            if not session.connected:
                break

            try:
                write(message)
            except:
                session.close()
                raise StreamingStop()

        return []
