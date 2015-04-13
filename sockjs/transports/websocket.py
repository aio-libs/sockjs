"""websocket transport"""
import asyncio
from aiohttp import web

from .base import Transport
from ..protocol import STATE_CLOSED, FRAME_OPEN, FRAME_HEARTBEAT
from ..protocol import loads, close_frame, message_frame, messages_frame


class WebSocketTransport(Transport):

    @asyncio.coroutine
    def send_open(self):
        self.ws.send_str(FRAME_OPEN)

    @asyncio.coroutine
    def send_message(self, messsage):
        self.ws.send_str(message_frame(messsage))

    @asyncio.coroutine
    def send_messages(self, messages):
        self.ws.send_str(messages_frame(messages))

    @asyncio.coroutine
    def send_message_frame(self, blob):
        self.ws.send_str(blob)

    @asyncio.coroutine
    def send_heartbeat(self):
        self.ws.send_str(FRAME_HEARTBEAT)

    @asyncio.coroutine
    def send_close(self, code, reason):
        self.ws.send_str(close_frame(code, reason))

        try:
            yield from self.ws.close(message=reason)
        finally:
            yield from self.session._remote_closed()

    @asyncio.coroutine
    def process(self):
        # start websocket connection
        ws = self.ws = web.WebSocketResponse()
        ws.start(self.request)

        # session was interrupted
        if self.session.interrupted:
            self.ws.send_str(close_frame(1002, 'Connection interrupted'))

        elif self.session.state == STATE_CLOSED:
            self.ws.send_str(close_frame(3000, 'Go away!'))

        else:
            try:
                yield from self.manager.acquire(self.session, self)
            except:  # should use specific exception
                yield from self.send_open()
                yield from self.send_close(
                    2010, "Another connection still open")
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
                        text = loads(data)
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
