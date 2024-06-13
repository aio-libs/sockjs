import asyncio
import logging
import warnings
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Tuple, Callable, Awaitable, TypeVar, Union, Any

from aiohttp import web

from . import SessionState
from .exceptions import SessionIsAcquired, SessionIsClosed
from .protocol import (
    CLOSED_MESSAGE,
    MsgType,
    OPEN_MESSAGE,
    SockjsMessage,
    close_frame,
    message_frame,
    messages_frame,
    Frame,
)


log = logging.getLogger("sockjs")
HandlerType = Callable[["SessionManager", "Session", SockjsMessage], Awaitable]


class Session:
    """SockJS session object.

    ``state``: Session state

    ``manager``: Session manager that hold this session

    ``acquired``: Acquired state, indicates that transport is using session
    """

    acquired = False
    state = SessionState.NEW
    interrupted = False
    exception = None
    _hb_task = None

    def __init__(
        self, session_id: str, *, heartbeat_delay=25, disconnect_delay=5, debug=False,
    ):
        self.id = session_id
        self.heartbeat_delay = heartbeat_delay
        self.disconnect_delay = disconnect_delay
        self.next_heartbeat = datetime.now() + timedelta(seconds=heartbeat_delay)
        self.expires: Optional[datetime] = datetime.now() + timedelta(
            seconds=disconnect_delay
        )
        self.request: Optional[web.Request] = None

        self._hits = 0
        self._heartbeats = 0
        self._send_heartbeats = False
        self._debug = debug
        self._waiter = None
        self._queue: deque[tuple[Frame, Any]] = deque()

    def __str__(self):
        result = ["id=%r" % (self.id,)]

        if self.state == SessionState.OPEN:
            result.append("connected")
        elif self.state == SessionState.CLOSED:
            result.append("closed")
        else:
            result.append("disconnected")

        if self.acquired:
            result.append("acquired")

        if len(self._queue):
            result.append("queue[%s]" % len(self._queue))
        if self._hits:
            result.append("hits=%s" % self._hits)
        if self._heartbeats:
            result.append("heartbeats=%s" % self._heartbeats)

        return " ".join(result)

    def expire(self):
        """Manually expire a session."""
        expires = datetime.now()
        if self.disconnect_delay:
            expires += timedelta(seconds=self.disconnect_delay)
        if not self.expires or self.expires > expires:
            self.expires = expires

    @property
    def expired(self) -> bool:
        if self.expires:
            return self.expires <= datetime.now()
        return False

    def acquire(self, request: web.Request) -> bool:
        """Returns True if session has opened."""
        self.acquired = True
        self.request = request
        self.expires = None
        self._send_heartbeats = self.heartbeat_delay > 0

        self.tick()
        self._hits += 1

        if self.state == SessionState.NEW:
            if self._debug:
                log.debug("open session: %s", self.id)
            self.state = SessionState.OPEN
            self.feed(Frame.OPEN, Frame.OPEN.value)
            return True

        return False

    def release(self):
        self.acquired = False
        self.request = None
        self._send_heartbeats = False
        if self._hb_task is not None:
            try:
                self._hb_task.cancel()
            except RuntimeError:
                pass  # an event loop already stopped
        self._hb_task = None

    def create_heartbeat_task(self):
        if self._hb_task is None and self._send_heartbeats:
            self._hb_task = asyncio.create_task(self._heartbeat_task())

    def tick(self, timeout=None):
        if timeout is None:
            self.next_heartbeat = datetime.now() + timedelta(
                seconds=self.heartbeat_delay
            )
        else:
            self.next_heartbeat = datetime.now() + timedelta(seconds=timeout)

    def heartbeat(self):
        if self._send_heartbeats:
            self.feed(Frame.HEARTBEAT, Frame.HEARTBEAT.value)
            self._heartbeats += 1

    async def _heartbeat_task(self):
        while True:
            now = datetime.now()
            if self.next_heartbeat <= now:
                self.heartbeat()
                self.tick()
            delta = (self.next_heartbeat - now).total_seconds()
            if delta > 0:
                await asyncio.sleep(delta)

    def feed(self, frame: Frame, data):
        # pack messages
        if frame == Frame.MESSAGE:
            if self._queue and self._queue[-1][0] == Frame.MESSAGE:
                self._queue[-1][1].append(data)
            else:
                self._queue.append((frame, [data]))
        else:
            self._queue.append((frame, data))

        self.release_waiters()
        self.tick()

    async def get_frame(self, pack=True) -> Tuple[Frame, str]:
        if not self._queue and self.state != SessionState.CLOSED:
            assert not self._waiter
            self._waiter = asyncio.Future()
            await self._waiter

        if self._queue:
            frame, payload = self._queue.popleft()
            self.tick()
            if pack:
                match frame:
                    case Frame.CLOSE:
                        return frame, close_frame(*payload)
                    case Frame.MESSAGE:
                        return frame, messages_frame(payload)

            return frame, payload
        else:
            raise SessionIsClosed()

    def release_waiters(self):
        # notify waiter
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)

    def send(self, msg: str) -> bool:
        """send message to client."""
        assert isinstance(msg, str), "String is required"

        if self._debug:
            log.info("outgoing message: %s, %s", self.id, str(msg)[:200])

        if self.state != SessionState.OPEN:
            return False

        self.feed(Frame.MESSAGE, msg)
        return True

    def send_frame(self, frm):
        """send message frame to client."""
        if self._debug:
            log.info("outgoing message: %s, %s", self.id, frm[:200])

        if self.state != SessionState.OPEN:
            return

        self.feed(Frame.MESSAGE_BLOB, frm)

    def close(self, code=3000, reason="Go away!"):
        """close session"""
        if self.state in (SessionState.CLOSING, SessionState.CLOSED):
            return

        if self._debug:
            log.debug("close session: %s", self.id)

        self.state = SessionState.CLOSING
        self.feed(Frame.CLOSE, (code, reason))


_marker = object()


class SessionManager:
    """A basic session manager."""

    _gc_task = None

    def __init__(
        self,
        name: str,
        app: web.Application,
        handler: HandlerType,
        heartbeat_delay=25,
        disconnect_delay=5,
        debug=False,
    ):
        self.name = name
        self.route_name = "sockjs-url-%s" % name
        self.app = app
        self.handler = handler
        self.factory = Session
        self.acquired = {}
        self.sessions: dict[str, Session] = {}
        self.heartbeat_delay = heartbeat_delay
        self.disconnect_delay = disconnect_delay
        self.debug = debug

    @property
    def started(self):
        return self._gc_task is not None

    def start(self):
        if not self._gc_task:
            self._gc_task = asyncio.create_task(self._gc_sessions_task())

    async def stop(self, _app=None):
        if self._gc_task is not None:
            try:
                self._gc_task.cancel()
            except RuntimeError:
                pass  # an event loop already stopped
        self._gc_task = None
        await self.clear()

    async def _check_expiration(self, session: Session):
        if session.expired:
            if self.debug:
                log.debug("session expired: %s", session.id)
            # Session is to be GC'd immediately
            if session.id in self.acquired:
                await self.release(session)
            if session.state == SessionState.OPEN:
                await self.remote_close(session)
            if session.state == SessionState.CLOSING:
                await self.remote_closed(session)
            return session.id

    async def _gc_sessions_task(self):
        delay = max(self.disconnect_delay, 5)
        while True:
            await asyncio.sleep(delay)
            await self._gc_expired_sessions()

    async def _gc_expired_sessions(self):
        sessions = self.sessions
        if sessions:
            tasks = [self._check_expiration(session) for session in sessions.values()]
            expired_session_ids = await asyncio.gather(*tasks)

            idx = 0
            for session_id in expired_session_ids:
                if session_id is None:
                    idx += 1
                    continue
                sessions.pop(session_id, None)

    def _add(self, session: Session):
        if session.expired:
            raise ValueError("Can not add expired session")

        self.sessions[session.id] = session
        return session

    _T = TypeVar("_T")

    def get(
        self,
        session_id,
        create=False,
        default: _T = _marker,
    ) -> Union[Session, _T]:
        session = self.sessions.get(session_id, None)
        if session is None:
            if create:
                session = self._add(
                    self.factory(
                        session_id,
                        heartbeat_delay=self.heartbeat_delay,
                        disconnect_delay=self.disconnect_delay,
                        debug=self.debug,
                    )
                )
            else:
                if default is not _marker:
                    return default
                raise KeyError(session_id)

        return session

    async def acquire(self, session: Session, request: web.Request):
        sid = session.id

        if sid in self.acquired:
            raise SessionIsAcquired("Another connection still open")
        if sid not in self.sessions:
            raise KeyError("Unknown session")

        if session.acquire(request):
            try:
                await self.handler(self, session, OPEN_MESSAGE)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                session.state = SessionState.CLOSING
                session.exception = exc
                session.interrupted = True
                session.feed(Frame.CLOSE, (3000, "Internal error"))
                log.exception("Exception in open session handling.")

        session.create_heartbeat_task()

        self.acquired[sid] = True
        return session

    def is_acquired(self, session):
        return session.id in self.acquired

    async def release(self, s: Session):
        if s.id in self.acquired:
            s.release()
            del self.acquired[s.id]

    def active_sessions(self):
        for session in list(self.sessions.values()):
            if not session.expired:
                yield session

    async def clear(self):
        """Manually expire all sessions in the pool."""
        for session in list(self.sessions.values()):
            if session.state != SessionState.CLOSED:
                session.disconnect_delay = 0
                await self.remote_closed(session)
        self.sessions.clear()

    def broadcast(self, message, exclude_session_ids: Optional[set] = None):
        blob = message_frame(message)
        exclude_session_ids = exclude_session_ids or set()

        for session in self.sessions.values():
            if not session.expired and session.id not in exclude_session_ids:
                session.send_frame(blob)

    def __del__(self):
        if len(self.sessions) or self._gc_task is not None:
            warnings.warn(
                "Please call `await SessionManager.stop()` before del",
                RuntimeWarning,
            )

    async def remote_message(self, session: Session, msg):
        """Call handler with message received from client."""
        if self.debug:
            log.debug("incoming message: %s, %s", session.id, msg[:200])
        session.tick()

        try:
            await self.handler(self, session, SockjsMessage(MsgType.MESSAGE, msg))
        except Exception:
            log.exception("Exception in message handler.")

    async def remote_messages(self, session: Session, messages):
        """Call handler for all messages received from client."""
        session.tick()

        for msg in messages:
            if self.debug:
                log.debug("incoming message: %s, %s", session.id, msg[:200])
            try:
                await self.handler(self, session, SockjsMessage(MsgType.MESSAGE, msg))
            except Exception:
                log.exception("Exception in message handler.")

    async def remote_close(self, session: Session, exc=None):
        """Start session closing."""
        if session.state in (SessionState.CLOSING, SessionState.CLOSED):
            return

        if self.debug:
            log.info("close session: %s", session.id)
        session.tick()
        session.state = SessionState.CLOSING
        if exc is not None:
            session.exception = exc
            session.interrupted = True
        try:
            await self.handler(self, session, SockjsMessage(MsgType.CLOSE, exc))
        except Exception:
            log.exception("Exception in close handler.")

    async def remote_closed(self, session: Session):
        """Close session."""
        if session.state == SessionState.CLOSED:
            return

        if session.disconnect_delay and not session.expired:
            session.expire()
            return

        if self.debug:
            log.info("session closed: %s", session.id)
        session.state = SessionState.CLOSED
        session.expire()
        try:
            await self.handler(self, session, CLOSED_MESSAGE)
        except Exception:
            log.exception("Exception in closed handler.")

        session.release_waiters()
