"""websocket transport"""
import asyncio
from aiohttp import web

from .base import Transport
from ..exceptions import SessionIsClosed
from ..protocol import STATE_CLOSED, FRAME_CLOSE
from ..protocol import loads, close_frame


class WebSocketTransport(Transport):

    @asyncio.coroutine
    def server(self, ws, session):
        while True:
            try:
                frame, data = yield from session._wait()
            except SessionIsClosed:
                break

            ws.send_str(data)

            if frame == FRAME_CLOSE:
                try:
                    yield from ws.close()
                finally:
                    yield from session._remote_closed()

    @asyncio.coroutine
    def client(self, ws, session):
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
                    yield from session._remote_close(exc)
                    yield from session._remote_closed()
                    yield from ws.close(message=b'broken json')
                    break

                yield from session._remote_message(text)

            elif msg.tp == web.MsgType.close:
                yield from session._remote_close()
            elif msg.tp == web.MsgType.closed:
                yield from session._remote_closed()
                break

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
                self.ws.send_str(close_frame(3000, 'Go away!'))
                yield from ws.close()
                return ws

            server = asyncio.async(self.server(ws, self.session))
            client = asyncio.async(self.client(ws, self.session))
            try:
                yield from asyncio.wait(
                    (server, client),
                    return_when=asyncio.FIRST_COMPLETED)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield from self.session._remote_close(exc)
            finally:
                yield from self.manager.release(self.session)
                if not server.done():
                    server.cancel()
                if not client.done():
                    client.cancel()

        return ws
