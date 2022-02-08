import asyncio
import collections
import logging
import warnings
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from aiohttp import web

from .exceptions import SessionIsAcquired, SessionIsClosed
from .protocol import (
    ClosedMessage,
    FRAME_CLOSE,
    FRAME_HEARTBEAT,
    FRAME_MESSAGE,
    FRAME_MESSAGE_BLOB,
    FRAME_OPEN,
    MSG_CLOSE,
    MSG_MESSAGE,
    OpenMessage,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_NEW,
    STATE_OPEN,
    SockjsMessage,
    close_frame,
    message_frame,
    messages_frame,
)


log = logging.getLogger("sockjs")


class Session:
    """SockJS session object.

    ``state``: Session state

    ``manager``: Session manager that hold this session

    ``acquired``: Acquired state, indicates that transport is using session
    """

    manager: Optional["SessionManager"] = None
    acquired = False
    state = STATE_NEW
    interrupted = False
    exception = None
    app: Optional[web.Application] = None

    def __init__(
        self,
        session_id,
        handler,
        *,
        heartbeat_delay=25,
        disconnect_delay=5,
        debug=False
    ):
        self.id = session_id
        self.handler = handler
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
        self._queue = collections.deque()

    def __str__(self):
        result = ["id=%r" % (self.id,)]

        if self.state == STATE_OPEN:
            result.append("connected")
        elif self.state == STATE_CLOSED:
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

    def _tick(self, timeout=None):
        if timeout is None:
            self.next_heartbeat = datetime.now() + timedelta(
                seconds=self.heartbeat_delay
            )
        else:
            self.next_heartbeat = datetime.now() + timedelta(seconds=timeout)

    async def _acquire(
        self, manager: "SessionManager", request: web.Request, heartbeat=True
    ):
        self.acquired = True
        self.manager = manager
        self.app = manager.app
        self.request = request
        self.expires = None
        self._send_heartbeats = heartbeat

        self._tick()
        self._hits += 1

        if self.state == STATE_NEW:
            log.debug("open session: %s", self.id)
            self.state = STATE_OPEN
            self._feed(FRAME_OPEN, FRAME_OPEN)
            try:
                await self.handler(OpenMessage, self)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state = STATE_CLOSING
                self.exception = exc
                self.interrupted = True
                self._feed(FRAME_CLOSE, (3000, "Internal error"))
                log.exception("Exception in open session handling.")

    def _release(self):
        self.acquired = False
        self.manager = None
        self.request = None
        self._send_heartbeats = False

    def _heartbeat(self):
        self._heartbeats += 1
        if self._send_heartbeats:
            self._feed(FRAME_HEARTBEAT, FRAME_HEARTBEAT)

    def _feed(self, frame, data):
        # pack messages
        if frame == FRAME_MESSAGE:
            if self._queue and self._queue[-1][0] == FRAME_MESSAGE:
                self._queue[-1][1].append(data)
            else:
                self._queue.append((frame, [data]))
        else:
            self._queue.append((frame, data))

        # notify waiter
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)
        self._tick()

    async def _get_frame(self, pack=True) -> Tuple[str, str]:
        if not self._queue and self.state != STATE_CLOSED:
            assert not self._waiter
            self._waiter = asyncio.Future()
            await self._waiter

        if self._queue:
            frame, payload = self._queue.popleft()
            self._tick()
            if pack:
                if frame == FRAME_CLOSE:
                    return FRAME_CLOSE, close_frame(*payload)
                elif frame == FRAME_MESSAGE:
                    return FRAME_MESSAGE, messages_frame(payload)

            return frame, payload
        else:
            raise SessionIsClosed()

    async def _remote_close(self, exc=None):
        """Close session from remote."""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        log.info("close session: %s", self.id)
        self._tick()
        self.state = STATE_CLOSING
        if exc is not None:
            self.exception = exc
            self.interrupted = True
        try:
            await self.handler(SockjsMessage(MSG_CLOSE, exc), self)
        except Exception:
            log.exception("Exception in close handler.")

    async def _remote_closed(self):
        if self.state == STATE_CLOSED:
            return

        if self.disconnect_delay and not self.expired:
            self.expire()
            return

        log.info("session closed: %s", self.id)
        self.state = STATE_CLOSED
        self.expire()
        try:
            await self.handler(ClosedMessage, self)
        except Exception:
            log.exception("Exception in closed handler.")

        # notify waiter
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)

    async def _remote_message(self, msg):
        log.debug("incoming message: %s, %s", self.id, msg[:200])
        self._tick()

        try:
            await self.handler(SockjsMessage(MSG_MESSAGE, msg), self)
        except Exception:
            log.exception("Exception in message handler.")

    async def _remote_messages(self, messages):
        self._tick()

        for msg in messages:
            log.debug("incoming message: %s, %s", self.id, msg[:200])
            try:
                await self.handler(SockjsMessage(MSG_MESSAGE, msg), self)
            except Exception:
                log.exception("Exception in message handler.")

    def send(self, msg: str) -> bool:
        """send message to client."""
        assert isinstance(msg, str), "String is required"

        if self._debug:
            log.info("outgoing message: %s, %s", self.id, str(msg)[:200])

        if self.state != STATE_OPEN:
            return False

        self._feed(FRAME_MESSAGE, msg)
        return True

    def send_frame(self, frm):
        """send message frame to client."""
        if self._debug:
            log.info("outgoing message: %s, %s", self.id, frm[:200])

        if self.state != STATE_OPEN:
            return

        self._feed(FRAME_MESSAGE_BLOB, frm)

    def close(self, code=3000, reason="Go away!"):
        """close session"""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        if self._debug:
            log.debug("close session: %s", self.id)

        self.state = STATE_CLOSING
        self._feed(FRAME_CLOSE, (code, reason))


_marker = object()


class SessionManager(dict):
    """A basic session manager."""

    _hb_task = None  # gc task

    def __init__(
        self,
        name: str,
        app: web.Application,
        handler,
        heartbeat_delay=25,
        disconnect_delay=5,
        debug=False,
    ):
        super().__init__()
        self.name = name
        self.route_name = "sockjs-url-%s" % name
        self.app = app
        self.handler = handler
        self.factory = Session
        self.acquired = {}
        self.sessions: List[Session] = []
        self.heartbeat_delay = heartbeat_delay
        self.disconnect_delay = disconnect_delay
        self.debug = debug

    @property
    def started(self):
        return self._hb_task is not None

    def start(self):
        if not self._hb_task:
            self._hb_task = asyncio.create_task(self._heartbeat_task())

    async def stop(self, _app=None):
        if self._hb_task is not None:
            try:
                self._hb_task.cancel()
            except RuntimeError:
                pass  # an event loop already stopped
            self._hb_task = None
        await self.clear()

    async def _check_expiration(self, session: Session):
        if session.expired:
            log.debug("session expired: %s", session.id)
            # Session is to be GC'd immediately
            if session.id in self.acquired:
                await self.release(session)
            if session.state == STATE_OPEN:
                await session._remote_close()
            if session.state == STATE_CLOSING:
                await session._remote_closed()
            return session.id

    async def _gc_expired_sessions(self):
        sessions = self.sessions
        if sessions:
            tasks = [self._check_expiration(session) for session in sessions]
            expired_session_ids = await asyncio.gather(*tasks)

            idx = 0
            for session_id in expired_session_ids:
                if session_id is None:
                    idx += 1
                    continue
                del self[session_id]
                del sessions[idx]

    async def _heartbeat_task(self):
        delay = min(self.heartbeat_delay, self.disconnect_delay)
        if delay <= 0:
            delay = max(self.heartbeat_delay, self.disconnect_delay, 10)
        while True:
            await asyncio.sleep(delay)
            await self._gc_expired_sessions()
            self._heartbeat()

    def _heartbeat(self):
        # Send heartbeat
        now = datetime.now()
        for session in self.sessions:
            if session.next_heartbeat <= now:
                session._heartbeat()

    def _add(self, session: Session):
        if session.expired:
            raise ValueError("Can not add expired session")

        session.manager = self
        session.app = self.app

        self[session.id] = session
        self.sessions.append(session)
        return session

    def get(
        self,
        session_id,
        create=False,
        default=_marker,
    ) -> Session:
        session = super().get(session_id, None)
        if session is None:
            if create:
                session = self._add(
                    self.factory(
                        session_id,
                        self.handler,
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
        if sid not in self:
            raise KeyError("Unknown session")

        await session._acquire(self, request)

        self.acquired[sid] = True
        return session

    def is_acquired(self, session):
        return session.id in self.acquired

    async def release(self, s: Session):
        if s.id in self.acquired:
            s._release()
            del self.acquired[s.id]

    def active_sessions(self):
        for session in list(self.values()):
            if not session.expired:
                yield session

    async def clear(self):
        """Manually expire all sessions in the pool."""
        for session in list(self.values()):
            if session.state != STATE_CLOSED:
                session.disconnect_delay = 0
                await session._remote_closed()

        self.sessions.clear()
        super().clear()

    def broadcast(self, message):
        blob = message_frame(message)

        for session in list(self.values()):
            if not session.expired:
                session.send_frame(blob)

    def __del__(self):
        if len(self.sessions) or self._hb_task is not None:
            warnings.warn(
                "Please call `await SessionManager.stop()` before del",
                RuntimeWarning,
            )
