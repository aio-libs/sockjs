""" websocket transport """
import hashlib
import logging
import struct
import time
import tulip
from zope.interface import implementer
from gunicorn.util import http_date
from pyramid.interfaces import IResponse
from pyramid.httpexceptions import HTTPException
from pyramid_sockjs.protocol import CLOSE, decode, close_frame

from .wsproto import init_websocket, init_websocket_hixie


@implementer(IResponse)

class WebSocketTransport:

    error = None

    def __init__(self, session, request):
        self.session = session
        self.request = request

    @tulip.coroutine
    def send(self):
        ws = self.proto
        session = self.session

        while True:
            tp, message = yield from session.wait()
            ws.send(message)

            if tp == CLOSE:
                ws.close()
                session.closed()
                break

    @tulip.coroutine
    def receive(self):
        ws = self.proto
        session = self.session

        while True:
            try:
                message = yield from ws.receive()
            except Exception as err:
                logging.exception(err)
                break

            if message == '':
                continue

            elif message is None:
                break
            else:
                try:
                    if message.startswith('['):
                        message = message[1:-1]

                    session.message(decode(message))
                except:
                    ws.close(message=b'broken json')
                    break

    def __call__(self, environ, start_response):
        request = self.request

        # init websocket protocol
        hixie_76 = False
        try:
            if 'HTTP_SEC_WEBSOCKET_VERSION' in request.environ:
                status, headers, self.proto = init_websocket(request)
            elif 'HTTP_ORIGIN' in request.environ:
                status, headers, self.proto = init_websocket_hixie(request)
                hixie_76 = environ['wsgi.websocket_version'] == 'hixie-76'
            else:
                status, headers, self.proto = init_websocket(request)
        except HTTPException as error: 
            return error(environ, start_response)

        # send handshake headers
        if hixie_76:
            write = request.environ['tulip.write']
            towrite = [
                ('HTTP/1.1 %s\r\n'%status).encode(),
                ('Date: %s\r\n'%http_date(time.time())).encode()]

            for key, val in headers:
                towrite.append(b''.join(
                    (key.encode('utf-8'), b': ', val.encode('utf-8'), b'\r\n')))

            towrite.append(b"\r\n")
            write(b''.join(towrite))

            part1, part2 = environ['wsgi.hixie_keys']

            key3 = environ['wsgi.input'].read(8)
            body = hashlib.md5(struct.pack("!II", part1, part2) + key3).digest()
            write(body)
        else:
            write = start_response(status, headers)
            write(b'')

        try:
            self.session.acquire(request)
        except: # should use specific exception
            self.proto.send(b'o')
            self.proto.send(close_frame(2010, b"Another connection still open"))
            self.proto.close()
            environ['tulip.closed'] = True
            return ()

        yield from tulip.wait(
            (self.send(), self.receive()), return_when=tulip.FIRST_COMPLETED)

        self.session.closed()

        # ugly hack
        environ['tulip.closed'] = True
        return ()
