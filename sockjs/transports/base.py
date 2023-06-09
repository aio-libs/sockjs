import abc
import asyncio

import aiohttp
from aiohttp import web

from ..exceptions import SessionIsAcquired, SessionIsClosed
from ..protocol import (
    ENCODING,
    FRAME_CLOSE,
    FRAME_MESSAGE,
    STATE_CLOSED,
    STATE_CLOSING,
    close_frame,
)
from ..session import Session, SessionManager


class Transport(abc.ABC):
    create_session = True

    @classmethod
    def get_session(cls, manager: SessionManager, session_id: str) -> Session:
        return manager.get(session_id, create=cls.create_session)

    def __init__(self, manager: SessionManager, session: Session, request: web.Request):
        self.manager = manager
        self.session = session
        self.request = request

    @abc.abstractmethod
    async def process(self) -> web.StreamResponse:
        pass


class StreamingTransport(Transport, abc.ABC):
    timeout = None
    maxsize = 128 * 1024

    def __init__(self, manager: SessionManager, session: Session, request: web.Request):
        super().__init__(manager, session, request)
        self.size = 0
        self.response = None

    async def _send(self, text: str):
        blob = text.encode(ENCODING)
        await self.response.write(blob)
        self.size += len(blob)
        return self.size > self.maxsize

    async def handle_session(self):
        assert self.response is not None, "Response is not specified."

        # session was interrupted
        if self.session.interrupted:
            await self._send(close_frame(1002, "Connection interrupted"))
            return

        # session is closing or closed
        if self.session.state in (STATE_CLOSING, STATE_CLOSED):
            await self.session._remote_closed()
            await self._send(close_frame(3000, "Go away!"))
            return

        # acquire session
        try:
            await self.manager.acquire(self.session, self.request)
        except SessionIsAcquired:
            await self._send(close_frame(2010, "Another connection still open"))
            return

        try:
            while True:
                if self.timeout:
                    try:
                        frame, text = await asyncio.wait_for(
                            self.session._get_frame(),
                            timeout=self.timeout,
                        )
                    except asyncio.futures.TimeoutError:
                        frame, text = FRAME_MESSAGE, "a[]"
                else:
                    frame, text = await self.session._get_frame()

                if frame == FRAME_CLOSE:
                    await self.session._remote_closed()
                    await self._send(text)
                    break

                stop = await self._send(text)
                if stop:
                    break
        except (asyncio.CancelledError, ConnectionError):
            await self.session._remote_close(exc=aiohttp.ClientConnectionError)
            await self.session._remote_closed()
            raise
        except SessionIsClosed:
            pass
        finally:
            await self.manager.release(self.session)
