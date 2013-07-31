"""websocket transport"""
import tulip
import tulip.http
from tulip.http import websocket

from zope.interface import implementer
from pyramid.interfaces import IResponse
from pyramid.httpexceptions import HTTPClientError
from pyramid_sockjs.protocol import CLOSE, decode, close_frame


@implementer(IResponse)
class WebSocketTransport:

    error = None

    def __init__(self, session, request):
        self.session = session
        self.request = request

    @tulip.coroutine
    def send(self):
        writer = self.writer
        session = self.session

        while True:
            tp, message = yield from session.wait()
            writer.send(message)

            if tp == CLOSE:
                try:
                    writer.close(message='Go away!')
                finally:
                    session.closed()
                break

    @tulip.coroutine
    def receive(self):
        read = self.reader.read
        session = self.session

        while True:
            message = yield from read()
            if message is None:
                break
            elif message.data == '':
                continue
            else:
                try:
                    data = message.data
                    if data.startswith('['):
                        data = data[1:-1]

                    session.message(decode(data))
                except:
                    self.writer.close(message=b'broken json')
                    break

    @tulip.coroutine
    def __call__(self, environ, start_response):
        request = self.request

        # WebSocket accepts only GET
        if request.method != 'GET':
            start_response('405 Method Not Allowed', (('Allow', 'GET'),))
            return ()

        headers = tuple((key.upper(), request.headers[key])
                        for key in websocket.WS_HDRS if key in request.headers)

        # init websocket protocol
        try:
            status, headers, parser, self.writer = websocket.do_handshake(
                request.method, headers, environ['tulip.writer'])
        except tulip.http.BadRequestException as error:
            httperr = HTTPClientError(headers=error.headers)
            httperr.text = error.message
            return httperr(environ, start_response)

        # send handshake headers
        start_response('101 Switching Protocols', headers)

        try:
            self.session.acquire(request)
        except:  # should use specific exception
            self.writer.send(b'o')
            self.writer.send(
                close_frame(2010, b"Another connection still open"))
            self.writer.close(2010)
            return ()

        self.reader = request.environ['tulip.reader'].set_parser(parser)

        try:
            yield from tulip.wait(
                (self.send(), self.receive()),
                return_when=tulip.FIRST_COMPLETED)
        except tulip.CancelledError:
            self.session.interrupt()

        self.session.closed()
        return ()
