"""raw websocket transport."""
import asyncio
from aiohttp import web

try:
    from asyncio import ensure_future
except ImportError:  # pragma: no cover
    ensure_future = asyncio.async

from .base import Transport
from ..exceptions import SessionIsClosed
from ..protocol import FRAME_CLOSE, FRAME_MESSAGE, FRAME_MESSAGE_BLOB, \
    FRAME_HEARTBEAT


class RawWebSocketTransport(Transport):

    async def server(self, ws, session):
        while True:
            try:
                frame, data = await session._wait(pack=False)
            except SessionIsClosed:
                break

            if frame == FRAME_MESSAGE:
                for text in data:
                    await ws.send_str(text)
            elif frame == FRAME_MESSAGE_BLOB:
                data = data[1:]
                if data.startswith('['):
                    data = data[1:-1]
                await ws.send_str(data)
            elif frame == FRAME_HEARTBEAT:
                await ws.ping()
            elif frame == FRAME_CLOSE:
                try:
                    await ws.close(message='Go away!')
                finally:
                    await session._remote_closed()

    async def client(self, ws, session):
        while True:
            msg = await ws.receive()

            if msg.type == web.WSMsgType.text:
                if not msg.data:
                    continue

                await self.session._remote_message(msg.data)

            elif msg.type == web.WSMsgType.close:
                await self.session._remote_close()
            elif msg.type == web.WSMsgType.closed:
                await self.session._remote_closed()
                break

    async def process(self):
        # start websocket connection
        ws = self.ws = web.WebSocketResponse()
        await ws.prepare(self.request)

        try:
            await self.manager.acquire(self.session)
        except Exception:  # should use specific exception
            await ws.close(message='Go away!')
            return ws

        server = ensure_future(self.server(ws, self.session), loop=self.loop)
        client = ensure_future(self.client(ws, self.session), loop=self.loop)
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
