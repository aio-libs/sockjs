""" iframe-htmlfile transport """
from gevent.queue import Empty
from pyramid.response import Response

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs.transports import StopStreaming
from pyramid_sockjs.protocol import HEARTBEAT
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame

from .utils import session_cookie


class EventsourceTransport(Response):

    timing = 5.0
    maxsize = 131072 # 128K bytes

    def __init__(self, session, request):
        self.__dict__.update(request.response.__dict__)
        self.session = session
        self.request = request

    def __call__(self, environ, start_response):
        write = start_response(
            self.status,
            (('Content-Type','text/event-stream; charset=UTF-8'),
             ('Cache-Control',
              'no-store, no-cache, must-revalidate, max-age=0'),
             session_cookie(self.request)))
        write('\r\n')

        timing = self.timing
        session = self.session

        if session.state == STATE_NEW:
            write("data: o\r\n\r\n")
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
                    write("data: %s\r\n\r\n"%close_frame(1000, 'Go away!'))
                    session.closed()
                    break

                if session.state != STATE_OPEN:
                    break

                try:
                    write("data: %s\r\n\r\n" % message)
                except:
                    session.closed()
                    raise StopStreaming()

                size += len(message)
                if size >= self.maxsize:
                    break
        finally:
            session.release()

        return []
