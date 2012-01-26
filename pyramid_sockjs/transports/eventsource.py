""" iframe-htmlfile transport """
from gevent.queue import Empty
from pyramid.response import Response
from pyramid_sockjs.transports import StreamingStop
from pyramid_sockjs.protocol import HEARTBEAT
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame


class EventsourceTransport(Response):

    TIMING = 5.0

    def __init__(self, session, request):
        self.__dict__.update(request.response.__dict__)
        self.session = session
        session.open()

    def __call__(self, environ, start_response):
        write = start_response(
            self.status, (('Content-Type','text/event-stream; charset=UTF-8'),))
        write("data: o\r\n\r\n")

        timing = self.TIMING
        session = self.session

        try:
            while True:
                try:
                    message = session.get_transport_message(timeout=timing)
                    if message is None:
                        session.close()
                        write("data: %s\r\n\r\n"%close_frame(1000, 'Go away!'))
                        raise StopIteration()
                except Empty:
                    message = HEARTBEAT
                    session.heartbeat()
                else:
                    message = message_frame(message)

                if not session.connected:
                    write("data: %s\r\n\r\n"%close_frame(1000, 'Go away!'))
                    break

                try:
                    write("data: %s\r\n\r\n" % message)
                except:
                    session.close()
                    raise StreamingStop()
        finally:
            session.manager.release(session)

        return []
