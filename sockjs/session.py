import asyncio
import collections
import logging
from datetime import datetime, timedelta

try:
    from asyncio import ensure_future
except ImportError:  # pragma: no cover
    ensure_future = asyncio.async

from .protocol import STATE_NEW, STATE_OPEN, STATE_CLOSING, STATE_CLOSED
from .protocol import FRAME_OPEN, FRAME_CLOSE
from .protocol import FRAME_MESSAGE, FRAME_MESSAGE_BLOB, FRAME_HEARTBEAT
from .exceptions import SessionIsAcquired, SessionIsClosed

from .protocol import MSG_CLOSE, MSG_MESSAGE
from .protocol import close_frame, message_frame, messages_frame
from .protocol import SockjsMessage, OpenMessage, ClosedMessage


log = logging.getLogger('sockjs')


class Session(object):
    """ SockJS session object

    ``state``: Session state

    ``manager``: Session manager that hold this session

    ``acquired``: Acquired state, indicates that transport is using session

    ``timeout``: Session timeout

    """

    manager = None
    acquired = False
    state = STATE_NEW
    interrupted = False
    exception = None

    def __init__(self, id, handler, *,
                 timeout=timedelta(seconds=10), loop=None, debug=False):
        self.id = id
        self.handler = handler
        self.expired = False
        self.timeout = timeout
        self.expires = datetime.now() + timeout
        self.loop = loop

        self._hits = 0
        self._heartbeats = 0
        self._heartbeat_transport = False
        self._debug = debug
        self._waiter = None
        self._queue = collections.deque()

    def __str__(self):
        result = ['id=%r' % (self.id,)]

        if self.state == STATE_OPEN:
            result.append('connected')
        elif self.state == STATE_CLOSED:
            result.append('closed')
        else:
            result.append('disconnected')

        if self.acquired:
            result.append('acquired')

        if len(self._queue):
            result.append('queue[%s]' % len(self._queue))
        if self._hits:
            result.append('hits=%s' % self._hits)
        if self._heartbeats:
            result.append('heartbeats=%s' % self._heartbeats)

        return ' '.join(result)

    def _tick(self, timeout=None):
        self.expired = False

        if timeout is None:
            self.expires = datetime.now() + self.timeout
        else:
            self.expires = datetime.now() + timeout

    async def _acquire(self, manager, heartbeat=True):
        self.acquired = True
        self.manager = manager
        self._heartbeat_transport = heartbeat

        self._tick()
        self._hits += 1

        if self.state == STATE_NEW:
            log.debug('open session: %s', self.id)
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
                self._feed(FRAME_CLOSE, (3000, 'Internal error'))
                log.exception('Exception in open session handling.')

    def _release(self):
        self.acquired = False
        self.manager = None
        self._heartbeat_transport = False

    def _heartbeat(self):
        self.expired = False
        self._tick()
        self._heartbeats += 1
        if self._heartbeat:
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

    async def _wait(self, pack=True):
        if not self._queue and self.state != STATE_CLOSED:
            assert not self._waiter
            self._waiter = asyncio.Future(loop=self.loop)
            await self._waiter

        if self._queue:
            frame, payload = self._queue.popleft()
            if pack:
                if frame == FRAME_CLOSE:
                    return FRAME_CLOSE, close_frame(*payload)
                elif frame == FRAME_MESSAGE:
                    return FRAME_MESSAGE, messages_frame(payload)

            return frame, payload
        else:
            raise SessionIsClosed()

    async def _remote_close(self, exc=None):
        """close session from remote."""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        log.info('close session: %s', self.id)
        self.state = STATE_CLOSING
        if exc is not None:
            self.exception = exc
            self.interrupted = True
        try:
            await self.handler(SockjsMessage(MSG_CLOSE, exc), self)
        except Exception:
            log.exception('Exception in close handler.')

    async def _remote_closed(self):
        if self.state == STATE_CLOSED:
            return

        log.info('session closed: %s', self.id)
        self.state = STATE_CLOSED
        self.expire()
        try:
            await self.handler(ClosedMessage, self)
        except Exception:
            log.exception('Exception in closed handler.')

        # notify waiter
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)

    async def _remote_message(self, msg):
        log.debug('incoming message: %s, %s', self.id, msg[:200])
        self._tick()

        try:
            await self.handler(SockjsMessage(MSG_MESSAGE, msg), self)
        except Exception:
            log.exception('Exception in message handler.')

    async def _remote_messages(self, messages):
        self._tick()

        for msg in messages:
            log.debug('incoming message: %s, %s', self.id, msg[:200])
            try:
                await self.handler(SockjsMessage(MSG_MESSAGE, msg), self)
            except Exception:
                log.exception('Exception in message handler.')

    def expire(self):
        """Manually expire a session."""
        self.expired = True

    def send(self, msg):
        """send message to client."""
        assert isinstance(msg, str), 'String is required'

        if self._debug:
            log.info('outgoing message: %s, %s', self.id, str(msg)[:200])

        if self.state != STATE_OPEN:
            return

        self._tick()
        self._feed(FRAME_MESSAGE, msg)

    def send_frame(self, frm):
        """send message frame to client."""
        if self._debug:
            log.info('outgoing message: %s, %s', self.id, frm[:200])

        if self.state != STATE_OPEN:
            return

        self._tick()
        self._feed(FRAME_MESSAGE_BLOB, frm)

    def close(self, code=3000, reason='Go away!'):
        """close session"""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        if self._debug:
            log.debug('close session: %s', self.id)

        self.state = STATE_CLOSING
        self._feed(FRAME_CLOSE, (code, reason))


_marker = object()


class SessionManager(dict):
    """A basic session manager."""

    _hb_handle = None  # heartbeat event loop timer
    _hb_task = None  # gc task

    def __init__(self, name, app, handler, loop,
                 heartbeat=25.0, timeout=timedelta(seconds=5), debug=False):
        self.name = name
        self.route_name = 'sockjs-url-%s' % name
        self.app = app
        self.handler = handler
        self.factory = Session
        self.acquired = {}
        self.sessions = []
        self.heartbeat = heartbeat
        self.timeout = timeout
        self.loop = loop
        self.debug = debug

    def route_url(self, request):
        return request.route_url(self.route_name)

    @property
    def started(self):
        return self._hb_handle is not None

    def start(self):
        if not self._hb_handle:
            self._hb_handle = self.loop.call_later(
                self.heartbeat, self._heartbeat)

    def stop(self):
        if self._hb_handle is not None:
            self._hb_handle.cancel()
            self._hb_handle = None
        if self._hb_task is not None:
            self._hb_task.cancel()
            self._hb_task = None

    def _heartbeat(self):
        if self._hb_task is None:
            self._hb_task = ensure_future(
                self._heartbeat_task(), loop=self.loop)

    async def _heartbeat_task(self):
        sessions = self.sessions

        if sessions:
            now = datetime.now()

            idx = 0
            while idx < len(sessions):
                session = sessions[idx]

                if session.acquired:
                    session._heartbeat()

                elif session.expires < now:
                    # Session is to be GC'd immedietely
                    if session.id in self.acquired:
                        await self.release(session)
                    if session.state == STATE_OPEN:
                        await session._remote_close()
                    if session.state == STATE_CLOSING:
                        await session._remote_closed()

                    del self[session.id]
                    del self.sessions[idx]
                    continue

                idx += 1

        self._hb_task = None
        self._hb_handle = self.loop.call_later(
            self.heartbeat, self._heartbeat)

    def _add(self, session):
        if session.expired:
            raise ValueError('Can not add expired session')

        session.manager = self
        session.registry = self.app

        self[session.id] = session
        self.sessions.append(session)
        return session

    def get(self, id, create=False, request=None, default=_marker):
        session = super(SessionManager, self).get(id, None)
        if session is None:
            if create:
                session = self._add(
                    self.factory(
                        id, self.handler,
                        timeout=self.timeout,
                        loop=self.loop, debug=self.debug))
            else:
                if default is not _marker:
                    return default
                raise KeyError(id)

        return session

    async def acquire(self, s):
        sid = s.id

        if sid in self.acquired:
            raise SessionIsAcquired('Another connection still open')
        if sid not in self:
            raise KeyError('Unknown session')

        await s._acquire(self)

        self.acquired[sid] = True
        return s

    def is_acquired(self, session):
        return session.id in self.acquired

    async def release(self, s):
        if s.id in self.acquired:
            s._release()
            del self.acquired[s.id]

    def active_sessions(self):
        for session in self.values():
            if not session.expired:
                yield session

    async def clear(self):
        """Manually expire all sessions in the pool."""
        for session in list(self.values()):
            if session.state != STATE_CLOSED:
                await session._remote_closed()

        self.sessions.clear()
        super(SessionManager, self).clear()

    def broadcast(self, message):
        blob = message_frame(message)

        for session in self.values():
            if not session.expired:
                session.send_frame(blob)

    def __del__(self):
        self.clear()
        self.stop()
