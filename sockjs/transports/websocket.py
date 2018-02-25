"""websocket transport"""
import asyncio
from aiohttp import web

try:
    from asyncio import ensure_future
except ImportError:  # pragma: no cover
    ensure_future = asyncio.async

from .base import Transport
from ..exceptions import SessionIsClosed
from ..protocol import STATE_CLOSED, FRAME_CLOSE
from ..protocol import loads, close_frame


class WebSocketTransport(Transport):

    async def server(self, ws, session):
        while True:
            try:
                frame, data = await session._wait()
            except SessionIsClosed:
                break

            await ws.send_str(data)

            if frame == FRAME_CLOSE:
                try:
                    await ws.close()
                finally:
                    await session._remote_closed()

    async def client(self, ws, session):
        while True:
            msg = await ws.receive()

            if msg.type == web.WSMsgType.text:
                data = msg.data
                if not data:
                    continue

                if data.startswith('['):
                    data = data[1:-1]

                try:
                    text = loads(data)
                except Exception as exc:
                    await session._remote_close(exc)
                    await session._remote_closed()
                    await ws.close(message=b'broken json')
                    break

                await session._remote_message(text)

            elif msg.type == web.WSMsgType.close:
                await session._remote_close()
            elif msg.type in (web.WSMsgType.closed, web.WSMsgType.closing):
                await session._remote_closed()
                break

    async def process(self):
        # start websocket connection
        ws = self.ws = web.WebSocketResponse()
        await ws.prepare(self.request)

        # session was interrupted
        if self.session.interrupted:
            await self.ws.send_str(
                close_frame(1002, 'Connection interrupted'))

        elif self.session.state == STATE_CLOSED:
            await self.ws.send_str(close_frame(3000, 'Go away!'))

        else:
            try:
                await self.manager.acquire(self.session)
            except Exception:  # should use specific exception
                await self.ws.send_str(close_frame(3000, 'Go away!'))
                await ws.close()
                return ws

            server = ensure_future(
                self.server(ws, self.session), loop=self.loop)
            client = ensure_future(
                self.client(ws, self.session), loop=self.loop)
            try:
                await asyncio.wait(
                    (server, client),
                    loop=self.loop,
                    return_when=asyncio.FIRST_COMPLETED)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.session._remote_close(exc)
            finally:
                await self.manager.release(self.session)
                if not server.done():
                    server.cancel()
                if not client.done():
                    client.cancel()

        return ws
