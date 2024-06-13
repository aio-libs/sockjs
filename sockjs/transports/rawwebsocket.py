"""raw websocket transport."""

import asyncio
from asyncio import ensure_future
from typing import Optional
from uuid import uuid4

from aiohttp import web
from async_timeout import timeout

from .base import Transport
from .utils import cancel_tasks
from ..exceptions import SessionIsClosed
from ..protocol import Frame
from ..session import Session, SessionManager


class RawWebSocketTransport(Transport):
    name = "websocket-raw"
    heartbeat_timeout = 10

    @classmethod
    def get_session(cls, manager: SessionManager, session_id: str) -> Session:
        # For WebSockets, as opposed to other transports, it is valid to
        # reuse `session_id`. The lifetime of SockJS WebSocket session is
        # defined by a lifetime of underlying WebSocket connection. It is
        # correct to have two separate sessions sharing the same
        # `session_id` at the same time.

        # Generate unique session_id based on given ID.
        orig_session_id = session_id
        while session_id in manager.sessions:
            session_id = "%s-%s" % (orig_session_id, uuid4().hex[-8:])
        return super().get_session(manager, session_id)

    def __init__(self, manager: SessionManager, session: Session, request: web.Request):
        super().__init__(manager, session, request)
        self._pong_event = asyncio.Event()
        self._wait_pong_task: Optional[asyncio.Task] = None

    async def server(self, ws: web.WebSocketResponse):
        while True:
            try:
                frame, data = await self.session.get_frame(pack=False)
            except SessionIsClosed:
                break

            if frame == Frame.MESSAGE:
                for text in data:
                    await ws.send_str(text)
            elif frame == Frame.MESSAGE_BLOB:
                data = data[1:]
                if data.startswith("["):
                    data = data[1:-1]
                await ws.send_str(data)
            elif frame == Frame.HEARTBEAT:
                await ws.ping()
                if self._wait_pong_task is None:
                    self._wait_pong_task = asyncio.create_task(self._wait_pong())
                    self._wait_pong_task.add_done_callback(self._wait_done_callback)
            elif frame == Frame.CLOSE:
                try:
                    await ws.close(message=b"Go away!")
                finally:
                    await self.manager.remote_closed(self.session)

    async def _wait_pong(self):
        try:
            async with timeout(self.heartbeat_timeout):
                await self._pong_event.wait()
        except asyncio.TimeoutError:
            self.session.close(3000, "No response from heartbeat")
        finally:
            self._pong_event.clear()

    def _wait_done_callback(self, _):
        self._wait_pong_task = None

    async def client(self, ws: web.WebSocketResponse):
        while True:
            msg = await ws.receive()
            if self._wait_pong_task is not None:
                self._pong_event.set()

            if msg.type == web.WSMsgType.text:
                if not msg.data:
                    continue
                await self.manager.remote_message(self.session, msg.data)
            elif msg.type == web.WSMsgType.close:
                await self.manager.remote_close(self.session)
            elif msg.type in (web.WSMsgType.closed, web.WSMsgType.closing):
                await self.manager.remote_closed(self.session)
                break
            elif msg.type == web.WSMsgType.PONG:
                self.session.tick()
            elif msg.type == web.WSMsgType.PING:
                await ws.pong(msg.data)
                self.session.tick()

    async def process(self):
        # start websocket connection
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(self.request)

        try:
            await self.manager.acquire(self.session, self.request)
        except Exception:  # should use specific exception
            await ws.close(message=b"Go away!")
            return ws

        server = ensure_future(self.server(ws))
        client = ensure_future(self.client(ws))
        try:
            await asyncio.wait(
                (server, client),
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.manager.remote_close(self.session, exc)
        finally:
            self.session.expire()
            await self.manager.release(self.session)
            await cancel_tasks(server, client, self._wait_pong_task)

        return ws
