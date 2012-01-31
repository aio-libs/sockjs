import gevent
from gevent.queue import Empty
from pyramid.compat import url_unquote
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.transports import StopStreaming
from pyramid_sockjs.protocol import OPEN, MESSAGE, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame

from .utils import session_cookie, cors_headers, cache_headers


class XHRStreamingTransport(Response):

    timing = 5.0
    maxsize = 131072 # 128K bytes
    open_seq = 'h' *  2048 + '\n'

    def __init__(self, session, request):
        self.__dict__.update(request.response.__dict__)

        self.session = session
        self.request = request

        meth = request.method
        self.headers = (
            ('Content-Type', 'application/javascript; charset=UTF-8'),
            ("Connection", "close"),
            session_cookie(request),
            ) + cors_headers(request)

        if meth not in ('GET', 'POST', 'OPTIONS'):
            raise Exception("No support for such method: %s"%meth)

    def __call__(self, environ, start_response):
        request = self.request
        if request.method == 'OPTIONS':
            self.status = 204
            self.content_type = 'application/javascript; charset=UTF-8'
            self.headerlist.append(
                ("Access-Control-Allow-Methods", "OPTIONS, POST"))
            self.headerlist.extend(cache_headers(request))
            return super(XHRStreamingTransport, self).__call__(
                environ, start_response)

        write = start_response(
            self.status, self._abs_headerlist(environ))
        write(self.open_seq)

        session = self.session

        #if session.state == STATE_CLOSED:
        #    write('%s\n'%close_frame(1002, "Connection interrupted"))
        #    return ()

        try:
            session.acquire(self.request)
        except: # should use specific exception
            write(close_frame(2010, "Another connection still open", '\n'))
            return ()

        if session.state == STATE_NEW:
            write(OPEN)
            session.open()

        if session.state in (STATE_CLOSING, STATE_CLOSED):
            write(close_frame(3000, 'Go away!', '\n'))
            if session.state == STATE_CLOSING:
                session.closed()
            return ()

        stream_size = 0
        timing = self.timing

        try:
            while True:
                try:
                    message = [session.get_transport_message(timeout=timing)]
                except Empty:
                    message = HEARTBEAT
                    session.heartbeat()
                else:
                    message = message_frame(message, '\n')

                if session.state == STATE_CLOSING:
                    write(close_frame(3000, 'Go away!', '\n'))
                    session.closed()
                    raise StopStreaming()

                if session.state != STATE_OPEN:
                    break

                try:
                    write(message)
                except:
                    session.closed()
                    raise StopStreaming()

                stream_size += len(message)
                if stream_size > self.maxsize:
                    break
        finally:
            session.release()

        return []
