import tulip
import logging
import collections
from heapq import heappush, heappop
from datetime import datetime, timedelta
from pyramid.compat import string_types
from pyramid_sockjs.protocol import encode, decode, message_frame, close_frame
from pyramid_sockjs.protocol import OPEN, CLOSE, MESSAGE, HEARTBEAT, FRAMES
from pyramid_sockjs.exceptions import SessionIsAcquired

log = logging.getLogger('pyramid_sockjs')

STATE_NEW = 0
STATE_OPEN = 1
STATE_CLOSING = 2
STATE_CLOSED = 3

FRAME_OPEN = OPEN
FRAME_CLOSE = CLOSE
FRAME_MESSAGE = MESSAGE
FRAME_HEARTBEAT = HEARTBEAT


class Session(object):
    """ SockJS session object

    ``state``: Session state

    ``manager``: Session manager that hold this session

    ``request``: Request object

    ``registry``: Pyramid component registry

    ``acquierd``: Acquired state, indicates that transport is using session

    ``timeout``: Session timeout

    """

    manager = None
    request = None
    registry = None
    acquired = False
    timeout = timedelta(seconds=10)
    state = STATE_NEW
    interrupted = False

    _heartbeat = False

    def __init__(self, id, timeout=timedelta(seconds=10), request=None):
        self.id = id
        self.expired = False
        self.timeout = timeout
        self.request = request
        self.registry = getattr(request, 'registry', None)
        self.expires = datetime.now() + timeout

        self.hits = 0
        self.heartbeats = 0

        self._waiter = None  # A future.
        self._queue = collections.deque()

    def __str__(self):
        result = ['id=%r' % (self.id,)]

        if self.state == STATE_OPEN:
            result.append('connected')
        else:
            result.append('disconnected')

        if len(self._queue):
            result.append('queue[%s]' % len(self._queue))
        if self.hits:
            result.append('hits=%s' % self.hits)
        if self.heartbeats:
            result.append('heartbeats=%s' % self.heartbeats)

        return ' '.join(result)

    def tick(self, timeout=None):
        self.expired = False

        if timeout is None:
            self.expires = datetime.now() + self.timeout
        else:
            self.expires = datetime.now() + timeout

    def acquire(self, request=None, heartbeat=True):
        if self.state == STATE_NEW:
            self.open()

        self.acquired = True
        self._heartbeat = heartbeat
        self.manager.acquire(self, request)

    def release(self):
        self.acquired = False
        self._heartbeat = False
        if self.manager is not None:
            self.manager.release(self)

    def heartbeat(self, expires):
        self.expired = False
        self.expires = expires
        self.heartbeats += 1
        if self._heartbeat:
            self.send_frame(FRAME_HEARTBEAT, FRAME_HEARTBEAT)

    def expire(self):
        """ Manually expire a session. """
        self.expired = True

    def open(self):
        log.info('open session: %s', self.id)
        self.state = STATE_OPEN
        self.send_frame(FRAME_OPEN, FRAME_OPEN, True)
        try:
            self.on_open()
        except:
            log.exception("Exceptin in .on_open method.")

    def close(self):
        """ close session """
        log.info('close session: %s', self.id)
        self.state = STATE_CLOSING
        try:
            self.on_close()
        except:
            log.exception("Exceptin in .on_close method.")

        self.send_frame(FRAME_CLOSE, close_frame(3000, b'Go away!'))

    def closed(self):
        log.info('session closed: %s', self.id)
        self.state = STATE_CLOSED
        self._queue.clear()
        self.release()
        self.expire()
        try:
            self.on_closed()
        except:
            log.exception("Exceptin in .on_closed method.")

    def interrupt(self):
        log.info('session has been interrupted: %s', self.id)
        self.interrupted = True
        try:
            self.on_interrupt()
        except:
            log.exception("Exceptin in .on_interrupt method.")

    @tulip.coroutine
    def wait(self, block=True):
        if block:
            while not self._queue:
                self._waiter = tulip.Future()
                yield from self._waiter

        # cleanup HB
        hb = None
        while self._queue and (self._queue[0][0] == HEARTBEAT):
            hb = self._queue.popleft()

        # join message frames
        messages = []
        while self._queue and (self._queue[0][0] == FRAME_MESSAGE):
            messages.append(self._queue.popleft()[1])

        if messages:
            if len(messages) > 1:
                return FRAME_MESSAGE, b''.join(
                    (b'a[', b','.join([m[2:-1] for m in messages]), b']'))
            else:
                return FRAME_MESSAGE, messages[0]

        if self._queue:
            return self._queue.popleft()

        return FRAME_HEARTBEAT, FRAME_HEARTBEAT

    def send(self, msg):
        """ send message to client """
        if self.manager.debug:
            log.info('outgoing message: %s, %s', self.id, str(msg)[:200])

        self.tick()
        self.send_frame(FRAME_MESSAGE, message_frame(msg))

    def send_frame(self, tp, frame, prepend=False):
        if prepend:
            self._queue.appendleft((tp, frame))
        else:
            self._queue.append((tp, frame))

        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            waiter.set_result(False)

    def message(self, msg):
        log.info('incoming message: %s, %s', self.id, msg[:200])
        self.tick()
        try:
            self.on_message(msg)
        except:
            log.exception("Exceptin in .on_message method.")

    def on_open(self):
        """ override in subsclass """

    def on_message(self, msg):
        """ executes when new message is received from client """

    def on_close(self):
        """ executes after session marked as closing """

    def on_closed(self):
        """ executes after session marked as closed """

    def on_remove(self):
        """ executes before removing from session manager """

    def on_interrupt(self):
        """ executes in case of network disconnection """


_marker = object()


class SessionManager(dict):
    """ A basic session manager """

    _hb_cb = None
    started = False

    def __init__(self, name, registry, session=Session,
                 heartbeat=7.0, timeout=timedelta(seconds=10)):
        self.name = name
        self.route_name = 'sockjs-url-%s'%name
        self.registry = registry
        self.factory = session
        self.acquired = {}
        self.sessions = []
        self.heartbeat = heartbeat
        self.timeout = timeout
        self.debug = registry.settings['debug_sockjs']

    def route_url(self, request):
        return request.route_url(self.route_name)

    def start(self):
        if not self.started:
            self.started = True
            el = tulip.get_event_loop()
            self._hb_cb = el.call_repeatedly(self.heartbeat, self._heartbeat)

    def stop(self):
        if self._hb_cb: self._hb_cb.cancel()

    def _heartbeat(self):
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

    def on_session_gc(self, session):
        return session.on_remove()

    def _add(self, session):
        if session.expired:
            raise ValueError("Can't add expired session")

        session.manager = self
        session.registry = self.registry

        self[session.id] = session
        self.sessions.append(session)
        return session

    def get(self, id, create=False, request=None, default=_marker):
        session = super(SessionManager, self).get(id, None)
        if session is None:
            if create:
                session = self._add(
                    self.factory(id, self.timeout, request=request))
            else:
                if default is not _marker:
                    return default
                raise KeyError(id)

        return session

    def acquire(self, session, request=None):
        sid = session.id

        if sid in self.acquired:
            raise SessionIsAcquired("Another connection still open")
        if sid not in self:
            raise KeyError("Unknown session")

        session.tick()
        session.hits += 1
        session.manager = self
        if request is not None:
            session.request = request

        self.acquired[sid] = True
        return session

    def is_acquired(self, session):
        return session.id in self.acquired

    def release(self, session):
        if session.id in self.acquired:
            del self.acquired[session.id]

    def active_sessions(self):
        for session in self.values():
            if not session.expired:
                yield session

    def clear(self):
        """ Manually expire all sessions in the pool. """
        for session in list(self.values()):
            if session.state != STATE_CLOSED:
                session.closed()

        self.clear()
        self.sessions.clear()

    def broadcast(self, message):
        frame = message_frame(message)

        for session in self.values():
            if not session.expired:
                session.send_frame(MESSAGE, frame)

    def __del__(self):
        self.clear()
        self.stop()
