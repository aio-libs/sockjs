"""raw websocket transport."""
import asyncio
from aiohttp import hdrs, web, errors

from sockjs.protocol import decode

from .base import Transport


class RawWebSocketTransport(Transport):

    @asyncio.coroutine
    def send_open(self):
        pass
        
    @asyncio.coroutine
    def send_message(self, msg):
        self.ws.send_str(msg)

    @asyncio.coroutine
    def send_messages(self, messages):
        for msg in messages:
            self.ws.send_str(msg)

    @asyncio.coroutine
    def send_heartbeat(self):
        self.ws.send_bytes(b'h')

    @asyncio.coroutine
    def send_close(self, code, reason):
        try:
            yield from self.ws.close(message=reason)
        finally:
            yield from self.session._remote_closed()

    @asyncio.coroutine
    def process(self):
        # start websocket connection
        ws = self.ws = web.WebSocketResponse()
        ws.start(self.request)

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
                if not msg.data:
                    continue

                yield from self.session._remote_message(msg.data)

            elif msg.tp == web.MsgType.close:
                yield from self.session._remote_close()
            elif msg.tp == web.MsgType.closed:
                yield from self.session._remote_closed()
                break

        yield from self.manager.release(self.session)
        return ws
