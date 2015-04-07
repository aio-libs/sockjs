"""websocket transport"""
import asyncio
from aiohttp import web
from sockjs.protocol import STATE_CLOSING, STATE_CLOSED, FRAME_OPEN, FRAME_CLOSE
from sockjs.protocol import decode, close_frame, message_frame, messages_frame

from .base import Transport


class WebSocketTransport(Transport):

    @asyncio.coroutine
    def send_open(self):
        print('send open', FRAME_OPEN)
        # self.ws.send_bytes(FRAME_OPEN+b'\n')

    @asyncio.coroutine
    def send_message(self, messsage):
        print('send msg')
        self.ws.send_bytes(message_frame(messsage))

    @asyncio.coroutine
    def send_messages(self, messages):
        print('send msgs')
        self.ws.send_bytes(messages_frame(messages))

    @asyncio.coroutine
    def send_heartbeat(self):
        print('send heartbeat')
        self.ws.send_bytes(b'h')

    @asyncio.coroutine
    def send_close(self, code, reason):
        print('send heartbeat', code, reason)
        self.ws.send_bytes(close_frame(code, reason))

        try:
            yield from self.ws.close(message=reason)
        finally:
            yield from self.session._remote_closed()

    @asyncio.coroutine
    def send_message_blob(self, blob):
        self.ws.send_bytes(blob)

    @asyncio.coroutine
    def process(self):
        # start websocket connection
        ws = self.ws = web.WebSocketResponse()
        ws.start(self.request)

        # session was interrupted
        if self.session.interrupted:
            self.ws.send_bytes(close_frame(1002, b"Connection interrupted"))

        elif self.session.state == STATE_CLOSED:
            self.ws.send_bytes(close_frame(3000, b'Go away!'))

        else:
            try:
                yield from self.manager.acquire(self.session, self)
            except:  # should use specific exception
                yield from self.send_open()
                yield from self.send_close(
                    2010, b"Another connection still open")
                return ws

            while True:
                msg = yield from ws.receive()

                if msg.tp == web.MsgType.text:
                    data = msg.data
                    if not data:
                        continue

                    if data.startswith('['):
                        data = data[1:-1]

                    try:
                        text = decode(data)
                    except Exception as exc:
                        yield from self.session._remote_close(exc)
                        yield from self.session._remote_closed()
                        yield from ws.close(message=b'broken json')
                        break

                    yield from self.session._remote_message(text)

                elif msg.tp == web.MsgType.close:
                    yield from self.session._remote_close()
                elif msg.tp == web.MsgType.closed:
                    yield from self.session._remote_closed()
                    break

            yield from self.manager.release(self.session)

        return ws
