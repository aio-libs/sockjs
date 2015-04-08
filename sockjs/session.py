import asyncio
import logging
from datetime import datetime, timedelta

from sockjs import protocol
from sockjs.protocol import STATE_NEW
from sockjs.protocol import STATE_OPEN
from sockjs.protocol import STATE_CLOSING
from sockjs.protocol import STATE_CLOSED
from sockjs.exceptions import SessionIsAcquired

from sockjs.protocol import MSG_CLOSE, MSG_MESSAGE, message_frame

from sockjs.protocol import SockjsMessage
from sockjs.protocol import OpenMessage, CloseMessage, ClosedMessage


log = logging.getLogger('sockjs')


class Session(object):
    """ SockJS session object

    ``state``: Session state

    ``manager``: Session manager that hold this session

    ``request``: Request object

    ``registry``: Pyramid component registry

    ``acquired``: Acquired state, indicates that transport is using session

    ``timeout``: Session timeout

    """

    app = None
    manager = None
    acquired = False
    timeout = timedelta(seconds=10)
    state = STATE_NEW
    interrupted = False
    exception = None
    transport = None

    _heartbeat = False

    def __init__(self, id, handler,
                 timeout=timedelta(seconds=10), debug=False):
        self.id = id
        self.handler = handler
        self.expired = False
        self.timeout = timeout
        self.expires = datetime.now() + timeout

        self._hits = 0
        self._heartbeats = 0
        self._debug = debug

        self._messages = []
        self._frames = []

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

        if len(self._messages):
            result.append('messages[%s]' % len(self._messages))
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

    @asyncio.coroutine
    def _acquire(self, manager, transport, heartbeat=True):
        self.acquired = True
        self.manager = manager
        self.transport = transport
        self._heartbeat = heartbeat

        self._tick()
        self._hits += 1

        if self.state == STATE_NEW:
            log.info('open session: %s', self.id)
            self.state = STATE_OPEN
            yield from self.transport.send_open()
            try:
                yield from self.handler(OpenMessage, self)
            except:
                log.exception("Exceptin in .on_open method.")
        else:
            if self._messages:
                yield from self.transport.send_messages(self._messages)
                self._messages.clear()

            while self._frames:
                yield from self.transport.send_message_frame(
                    self._frames.pop(0))

    def _release(self):
        self.acquired = False
        self.manager = None
        self.transport = None
        self._heartbeat = False

    def _heartbeat(self, expires):
        self.expired = False
        self.expires = expires
        self.heartbeats += 1
        if self._heartbeat:
            self.transport.send_heartbeat()

    @asyncio.coroutine
    def _remote_close(self, exc=None):
        """close session"""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        log.info('close session: %s', self.id)
        self.state = STATE_CLOSING
        if exc is not None:
            self.exception = exc
            self.interrupted = True
        try:
            yield from self.handler(SockjsMessage(MSG_CLOSE, exc), self)
        except:
            log.exception("Exceptin in close handler.")

    def _remote_closed(self):
        if self.state == STATE_CLOSED:
            return

        log.info('session closed: %s', self.id)
        self._messages.clear()
        self.state = STATE_CLOSED
        self.expire()
        try:
            yield from self.handler(ClosedMessage, self)
        except:
            log.exception("Exceptin in closed handler.")

    @asyncio.coroutine
    def _remote_message(self, msg):
        log.info('incoming message: %s, %s', self.id, msg[:200])
        self._tick()
        try:
            yield from self.handler(SockjsMessage(MSG_MESSAGE, msg), self)
        except:
            log.exception("Exceptin in handler method.")

    @asyncio.coroutine
    def _remote_messages(self, messages):
        self._tick()

        for msg in messages:
            log.info('incoming message: %s, %s', self.id, msg[:200])
            try:
                yield from self.handler(SockjsMessage(MSG_MESSAGE, msg), self)
            except:
                log.exception("Exceptin in handler method.")

    def expire(self):
        """ Manually expire a session. """
        self.expired = True

    def send(self, msg):
        """ send message to client """
        if self._debug:
            log.info('outgoing message: %s, %s', self.id, str(msg)[:200])

        if self.state != STATE_OPEN:
            return

        self._tick()
        if self.transport is None:
            self._messages.append(msg)
        else:
            yield from self.transport.send_message(msg)

    def send_frame(self, frm):
        """ send message to client """
        if self._debug:
            log.info('outgoing message: %s, %s', self.id, frm[:200])

        if self.state != STATE_OPEN:
            return

        self._tick()
        if self.transport is None:
            self._frames.append(frm)
        else:
            yield from self.transport.send_message_frame(frm)

    @asyncio.coroutine
    def close(self, code=3000, reason='Go away!'):
        """close session"""
        if self.state in (STATE_CLOSING, STATE_CLOSED):
            return

        log.info('close session: %s', self.id)
        self.state = STATE_CLOSING

        if self.transport is not None:
            yield from self.transport.send_close(code, reason)


_marker = object()


class SessionManager(dict):
    """A basic session manager."""

    _hb_timer = None  # heartbeat event loop timer

    def __init__(self, name, app, handler,
                 heartbeat=7.0, timeout=timedelta(seconds=10), debug=False):
        self.name = name
        self.route_name = 'sockjs-url-%s' % name
        self.app = app
        self.handler = handler
        self.factory = Session
        self.acquired = {}
        self.sessions = []
        self.heartbeat = heartbeat
        self.timeout = timeout
        self.debug = debug

    def route_url(self, request):
        return request.route_url(self.route_name)

    @property
    def started(self):
        return self._hb_timer is not None

    def start(self):
        # if not self._hb_timer:
        #     loop = tulip.get_event_loop()
        #     self._hb_timer = loop.call_later(
        #         self.heartbeat, self._heartbeat, loop)
        pass

    def stop(self):
        if self._hb_timer:
            self._hb_timer.cancel()
            self._hb_timer = None

    def _heartbeat(self, loop):
        sessions = self.sessions

        if sessions:
            now = datetime.now()
            expires = now + self.timeout

            idx = 0
            while idx < len(sessions):
                session = sessions[idx]

                if session.expires < now:
                    # Session is to be GC'd immedietely
                    if not self.on_session_gc(session):
                        del self[session.id]
                        del self.sessions[idx]
                    if session.id in self.acquired:
                        del self.acquired[session.id]
                    if session.state == STATE_OPEN:
                        session.close()
                    if session.state == STATE_CLOSING:
                        session.closed()
                    continue

                elif session.acquired:
                    session.heartbeat(expires)

                idx += 1

        self._hb_timer = loop.call_later(
            self.heartbeat, self._heartbeat, loop)

    def on_session_gc(self, session):
        return session.on_remove()

    def _add(self, session):
        if session.expired:
            raise ValueError("Can't add expired session")

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
                    self.factory(id, self.handler, self.timeout))
            else:
                if default is not _marker:
                    return default
                raise KeyError(id)

        return session

    @asyncio.coroutine
    def acquire(self, session, transport):
        sid = session.id

        if sid in self.acquired:
            raise SessionIsAcquired("Another connection still open")
        if sid not in self:
            raise KeyError("Unknown session")

        self.acquired[sid] = True

        yield from session._acquire(self, transport)
        return session

    def is_acquired(self, session):
        return session.id in self.acquired

    @asyncio.coroutine
    def release(self, session):
        if session.id in self.acquired:
            session._release()
            del self.acquired[session.id]

    def active_sessions(self):
        for session in self.values():
            if not session.expired:
                yield session

    def clear(self):
        """ Manually expire all sessions in the pool. """
        for session in list(self.values()):
            if session.state != STATE_CLOSED:
                session._remote_closed()

        self.sessions.clear()
        super(SessionManager, self).clear()

    def broadcast(self, message):
        blob = message_frame(message)

        for session in self.values():
            if not session.expired:
                yield from session.send_frame(blob)

    def __del__(self):
        self.clear()
        self.stop()
