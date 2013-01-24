""" raw websocket transport """
import hashlib
import logging
import struct
import tulip
from zope.interface import implementer
from pyramid.interfaces import IResponse
from pyramid.httpexceptions import HTTPException
from pyramid_sockjs.protocol import CLOSE, MESSAGE, decode

from .wsproto import init_websocket


@implementer(IResponse)

class RawWebSocketTransport:

    def __init__(self, session, request):
        self.session = session
        self.request = request

    @tulip.coroutine
    def send(self):
        ws = self.proto
        session = self.session

        while True:
            tp, message = yield from session.wait()
            if tp == MESSAGE:
                ws.send(decode(message[2:-1]).encode('utf-8'))
            elif tp == CLOSE:
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

            if message is None:
                break

            session.message(message)

    def __call__(self, environ, start_response):
        request = self.request

        # init websocket protocol
        try:
            status, headers, self.proto = init_websocket(request)
        except HTTPException as error: 
            return error(environ, start_response)

        # send handshake headers
        write = start_response(status, headers)
        write(b'')

        self.session.acquire(request)

        yield from tulip.wait(
            (self.send(), self.receive()), return_when=tulip.FIRST_COMPLETED)

        self.session.closed()

        # ugly hack
        environ['tulip.closed'] = True
        return ()
