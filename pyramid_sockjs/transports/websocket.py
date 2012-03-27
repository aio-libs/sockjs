""" websocket transport """
import time
import struct
import errno
import gevent
from gevent.queue import Empty
from gevent.pywsgi import format_date_time
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

    return WebSocketResponse(session, request, send, receive, websocket)


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

    return WebSocketResponse(session, request, send, receive, websocket)


class WebSocketResponse(Response):

    def __init__(self, session, request, send, receive, websocket):
        self.__dict__.update(request.response.__dict__)
        self.session = session
        self.request = request
        self.websocket = websocket
        self.send = send
        self.receive = receive

    def __call__(self, environ, start_response):
        # WebsocketHixie76 handshake (test_haproxy)
        if environ['wsgi.websocket_version'] == 'hixie-76':
            part1, part2, socket = environ['wsgi.hixie-keys']

            towrite = [
                'HTTP/1.1 %s\r\n'%self.status,
                'Date: %s\r\n'%format_date_time(time.time())]

            for header in self._abs_headerlist(environ):
                towrite.append("%s: %s\r\n" % header)

            towrite.append("\r\n")
            socket.sendall(''.join(towrite))

            key3 = environ['wsgi.input'].read(8)
            if not key3:
                key3 = environ['wsgi.input'].rfile.read(8)

            socket.sendall(
                md5(struct.pack("!II", part1, part2) + key3).digest())
        else:
            write = start_response(
                self.status, self._abs_headerlist(environ))
            write(self.body)

        try:
            self.session.acquire(self.request)
        except: # should use specific exception
            self.websocket.send('o')
            self.websocket.send(
                close_frame(2010, "Another connection still open", '\n'))
            self.websocket.close()
            return StopStreaming()

        gevent.joinall((gevent.spawn(self.send), gevent.spawn(self.receive)))
        raise StopStreaming()
