import abc
import asyncio

from aiohttp import web
from aiohttp.web_exceptions import HTTPClientError, HTTPError

from ..exceptions import SessionIsAcquired, SessionIsClosed
from ..protocol import (
    ENCODING,
    close_frame,
    SessionState,
    Frame,
)
from ..session import Session, SessionManager


class HTTPClientClosedConnection(HTTPClientError):
    status_code = 499


class Transport(abc.ABC):
    name: str
    create_session = True

    @classmethod
    def get_session(cls, manager: SessionManager, session_id: str) -> Session:
        return manager.get(session_id, create=cls.create_session)

    def __init__(
        self,
        manager: SessionManager,
        session: Session,
        request: web.Request,
    ):
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
        try:
            blob = text.encode(ENCODING)
            await self.response.write(blob)
            self.size += len(blob)
            return self.size > self.maxsize
        except ConnectionResetError as e:
            raise HTTPClientClosedConnection() from e

    async def handle_session(self):
        assert self.response is not None, "Response is not specified."

        # session was interrupted
        if self.session.interrupted:
            await self._send(close_frame(1002, "Connection interrupted"))
            return

        # session is closing or closed
        if self.session.state in (SessionState.CLOSING, SessionState.CLOSED):
            await self.manager.remote_closed(self.session)
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
                            self.session.get_frame(),
                            timeout=self.timeout,
                        )
                    except asyncio.futures.TimeoutError:
                        frame, text = Frame.MESSAGE, "a[]"
                else:
                    frame, text = await self.session.get_frame()

                if frame == Frame.CLOSE:
                    await self.manager.remote_closed(self.session)
                    await self._send(text)
                    break

                stop = await self._send(text)
                if stop:
                    break
        except (asyncio.CancelledError, ConnectionError, HTTPError) as e:
            await self.manager.remote_close(self.session, exc=e)
            await self.manager.remote_closed(self.session)
            raise
        except SessionIsClosed:
            pass
        finally:
            await self.manager.release(self.session)
