""" websocket transport """
import gevent
from gevent.queue import Empty
from pyramid.response import Response
from pyramid_sockjs.protocol import OPEN, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame


def WebSocketTransport(session, request):
    websocket = request.environ['wsgi.websocket']

    def send():
        websocket.send(OPEN)
        session.open()

        while True:
            try:
                message = session.get_transport_message(5.0)
            except Empty:
                message = HEARTBEAT
                session.heartbeat()
            else:
                message = message_frame(message)

            if message is None:
                websocket.send(close_frame('Go away'))
                websocket.close()
                session.close()
                break

            if not session.connected:
                break

            try:
                websocket.send(message)
            except:
                session.close()
                import traceback
                traceback.print_exc()
                break

    def receive():
        while True:
            message = websocket.receive()

            if not message:
                session.close()
                break
            else:
                decoded_message = decode(message)
                if decoded_message is not None:
                    session.message(decoded_message)

    jobs = [gevent.spawn(send), gevent.spawn(receive)]

    return WebSocketResponse(request.response, jobs)


class WebSocketResponse(Response):

    def __init__(self, response, jobs):
        self.__dict__.update(response.__dict__)
        self.jobs = jobs

    def __call__(self, environ, start_response):
        write = start_response(
            self.status, self._abs_headerlist(environ))
        write('')

        gevent.joinall(self.jobs)
        return []
