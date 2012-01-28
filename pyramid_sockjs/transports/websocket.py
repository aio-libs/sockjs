""" websocket transport """
import errno
import gevent
from gevent.queue import Empty
from socket import SHUT_RDWR, error
from pyramid.response import Response

from pyramid_sockjs.transports import StopStreaming
from pyramid_sockjs.protocol import OPEN, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame


TIMING = 5.0


def WebSocketTransport(session, request):
    socket = request.environ['gunicorn.socket']
    websocket = request.environ['wsgi.websocket']

    def send():
        if session.is_new():
            try:
                websocket.send('o')
            except:
                return
            session.open()

        if not session.connected:
            websocket.send(close_frame(3000, 'Go away!'))
            websocket.close()
            session.release()
            return

        while True:
            try:
                message = [session.get_transport_message(timeout=TIMING)]
            except Empty:
                message = 'h'
                session.heartbeat()
            else:
                message = message_frame(message)

            if not session.connected:
                try:
                    websocket.send(close_frame(3000, 'Go away!'))
                    websocket.close()
                except:
                    pass
                break

            try:
                websocket.send(message)
            except:
                session.close()
                break

    def receive():
        while True:
            try:
                message = websocket.receive()
            except:
                session.close()
                break

            if not session.connected:
                try:
                    websocket.send(close_frame(3000, 'Go away!'))
                    websocket.close()
                except:
                    pass
                break

            if message == '':
                continue

            if message is None:
                session.close()
                websocket.close()
                break

            try:
                decoded_message = decode(message)
            except:
                session.close()
                websocket.close()
                break

            if decoded_message:
                session.message(decoded_message)

        session.release()

    jobs = [gevent.spawn(send), gevent.spawn(receive)]

    return WebSocketResponse(request.response, jobs)


def RawWebSocketTransport(session, request):
    socket = request.environ['gunicorn.socket']
    websocket = request.environ['wsgi.websocket']

    def send():
        if session.is_new():
            session.open()

        if not session.connected:
            websocket.close()
            session.release()
            return

        while True:
            try:
                message = session.get_transport_message(timeout=TIMING)
            except Empty:
                continue

            if not session.connected:
                try:
                    websocket.close()
                except:
                    pass
                break
            else:
                try:
                    websocket.send(message)
                except:
                    session.close()
                    break

    def receive():
        while True:
            try:
                message = websocket.receive()
            except:
                session.close()
                break

            if not session.connected:
                try:
                    websocket.close()
                except:
                    pass
                break

            if message is None:
                session.close()
                websocket.close()
                break

            session.message(message)

        session.release()

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
        raise StopStreaming()
