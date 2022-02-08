"""websocket transport"""
import asyncio
import logging
from asyncio import ensure_future
from typing import Optional
from uuid import uuid4

from aiohttp import web
from aiohttp.web_exceptions import HTTPMethodNotAllowed
from async_timeout import timeout

from .base import Transport
from .utils import cancel_tasks
from ..exceptions import SessionIsClosed
from ..protocol import FRAME_CLOSE, FRAME_HEARTBEAT, STATE_CLOSED, close_frame, loads
from ..session import Session, SessionManager


log = logging.getLogger("sockjs")


class WebSocketTransport(Transport):
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
        while session_id in manager:
            session_id = "%s-%s" % (orig_session_id, uuid4().hex[-8:])
        return super().get_session(manager, session_id)

    def __init__(self, manager: SessionManager, session: Session, request: web.Request):
        super().__init__(manager, session, request)
        self._pong_event = asyncio.Event()
        self._wait_pong_task: Optional[asyncio.Task] = None

    async def server(self, ws: web.WebSocketResponse):
        while True:
            try:
                frame, data = await self.session._get_frame()
            except SessionIsClosed:
                break

            if frame == FRAME_HEARTBEAT:
                await ws.ping()
                log.debug("Send WS PING")
                if self._wait_pong_task is None:
                    self._wait_pong_task = asyncio.create_task(self._wait_pong())
                    self._wait_pong_task.add_done_callback(self._wait_done_callback)
                continue

            await ws.send_str(data)

            if frame == FRAME_CLOSE:
                try:
                    await ws.close()
                finally:
                    await self.session._remote_closed()

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
                data = msg.data
                if not data:
                    continue

                try:
                    text = loads(data)
                except Exception as exc:
                    await self.session._remote_close(exc)
                    await self.session._remote_closed()
                    await ws.close(message=b"broken json")
                    break

                if data.startswith("["):
                    await self.session._remote_messages(text)
                else:
                    await self.session._remote_message(text)
            elif msg.type == web.WSMsgType.PONG:
                log.debug("Received WS PONG")
                self.session._tick()
            elif msg.type == web.WSMsgType.PING:
                log.debug("Received WS PING")
                await ws.pong(msg.data)
                self.session._tick()
            elif msg.type == web.WSMsgType.close:
                await self.session._remote_close()
            elif msg.type in (web.WSMsgType.closed, web.WSMsgType.closing):
                await self.session._remote_closed()
                break

    async def process(self):
        if self.request.method != "GET":
            # WebSocket should only accept GET
            raise HTTPMethodNotAllowed(
                self.request.method,
                ["GET"],
                body=b"",
                content_type="",
            )

        # start websocket connection
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(self.request)

        # session was interrupted
        if self.session.interrupted:
            await ws.send_str(close_frame(1002, "Connection interrupted"))
        elif self.session.state == STATE_CLOSED:
            await ws.send_str(close_frame(3000, "Go away!"))
        else:
            try:
                await self.manager.acquire(self.session, self.request)
            except Exception:  # should use specific exception
                await ws.send_str(close_frame(3000, "Go away!"))
                await ws.close()
                return ws
            server = ensure_future(self.server(ws))
            client = ensure_future(self.client(ws))
            try:
                await asyncio.wait(
                    (server, client), return_when=asyncio.FIRST_COMPLETED
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.session._remote_close(exc)
            finally:
                self.session.expire()
                await self.manager.release(self.session)
                await cancel_tasks(server, client, self._wait_pong_task)

        return ws
