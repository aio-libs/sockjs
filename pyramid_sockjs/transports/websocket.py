""" websocket transport """
import struct
import errno
import gevent
from gevent.queue import Empty
from hashlib import md5
from socket import SHUT_RDWR, error
from pyramid.response import Response

from pyramid_sockjs import STATE_NEW
from pyramid_sockjs import STATE_OPEN
from pyramid_sockjs import STATE_CLOSING
from pyramid_sockjs import STATE_CLOSED
from pyramid_sockjs.transports import StopStreaming
from pyramid_sockjs.protocol import OPEN, HEARTBEAT
from pyramid_sockjs.protocol import encode, decode, close_frame, message_frame


TIMING = 5.0


def WebSocketTransport(session, request):
    socket = request.environ['gunicorn.socket']
    websocket = request.environ['wsgi.websocket']

    def send():
        if session.state == STATE_NEW:
            try:
                websocket.send('o')
            except:
                return
            session.open()

        if session.state == STATE_CLOSING:
            websocket.send(close_frame(3000, 'Go away!'))
            websocket.close()
            session.closed()
            return

        while True:
            try:
                message = [session.get_transport_message(timeout=TIMING)]
            except Empty:
                message = 'h'
                session.heartbeat()
            else:
                message = message_frame(message)

            if session.state == STATE_CLOSING:
                try:
                    websocket.send(close_frame(3000, 'Go away!'))
                    websocket.close()
                except:
                    pass
                session.closed()
                break

            try:
                websocket.send(message)
            except:
                session.closed()
                break

    def receive():
        while True:
            try:
                message = websocket.receive()
            except:
                session.closed()
                break

            if session.state == STATE_CLOSING:
                try:
                    websocket.send(close_frame(3000, 'Go away!'))
                    websocket.close()
                except:
                    pass
                session.closed()
                break

            if message == '':
                continue

            if message is None:
                session.closed()
                websocket.close()
                break

            try:
                if message.startswith('['):
                    message = message[1:-1]
                decoded_message = decode(message)
            except:
                try:
                    websocket.close(message='broken json')
                except:
                    import traceback
                    traceback.print_exc()
                session.closed()
                break

            if decoded_message:
                session.message(decoded_message)

        session.release()

    jobs = [gevent.spawn(send), gevent.spawn(receive)]

    return WebSocketResponse(session, request, jobs, websocket)


def RawWebSocketTransport(session, request):
    socket = request.environ['gunicorn.socket']
    websocket = request.environ['wsgi.websocket']

    def send():
        if session.state == STATE_NEW:
            session.open()

        while True:
            if session.state == STATE_CLOSING:
                try:
                    websocket.close()
                except:
                    pass
                session.closed()
                break

            try:
                message = session.get_transport_message(timeout=TIMING)
            except Empty:
                continue

            if session.state != STATE_OPEN:
                try:
                    websocket.close()
                except:
                    pass
                session.closed()
                break
            else:
                try:
                    websocket.send(message)
                except:
                    session.closed()
                    break

    def receive():
        while True:
            try:
                message = websocket.receive()
            except:
                session.closed()
                break

            if session.state == STATE_CLOSED:
                break

            if session.state == STATE_CLOSING:
                try:
                    websocket.close()
                except:
                    pass
                session.closed()
                break

            if message is None:
                session.closed()
                websocket.close()
                break

            session.message(message)

        session.release()

    jobs = [gevent.spawn(send), gevent.spawn(receive)]

    return WebSocketResponse(session, request, jobs, websocket)


class WebSocketResponse(Response):

    def __init__(self, session, request, jobs, websocket):
        self.__dict__.update(request.response.__dict__)
        self.jobs = jobs
        self.session = session
        self.request = request
        self.websocket = websocket

    def __call__(self, environ, start_response):
        write = start_response(
            self.status, self._abs_headerlist(environ))

        # WebsocketHixie76.test_haproxy
        if environ['wsgi.websocket_version'] == 'hixie-76':
            part1, part2 = environ['wsgi.hixie-keys']
            key3 = environ['wsgi.input'].rfile.read(8)

            write(md5(struct.pack("!II", part1, part2) + key3).digest())
        else:
            write(self.body)

        try:
            self.session.acquire(self.request)
        except: # should use specific exception
            self.websocket.send('o')
            self.websocket.send(
                close_frame(2010, "Another connection still open", '\n'))
            self.websocket.close()
            return StopStreaming()

        gevent.joinall(self.jobs)
        raise StopStreaming()
