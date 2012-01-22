import logging
import gevent
from gevent.queue import Queue
from heapq import heappush, heappop
from datetime import datetime, timedelta
from pyramid.compat import string_types

log = logging.getLogger('pyramid_sockjs')


class Session(object):

    acquired = False
    timeout = timedelta(seconds=10)

    def __init__(self, id, timeout=timedelta(seconds=10)):
        self.id = id
        self.expired = False
        self.timeout = timeout
        self.expires = datetime.now() + timeout

        self.queue = Queue()

        self.hits = 0
        self.heartbeats = 0
        self.connected = False

    def __str__(self):
        result = ['session_id=%r' % self.id]

        if self.connected:
            result.append('connected')
        else:
            result.append('disconnected')

        if self.queue.qsize():
            result.append('queue[%s]' % self.queue.qsize())
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

    def heartbeat(self):
        self.heartbeats += 1

    def expire(self):
        """ Manually expire a session. """
        self.expired = True
        self.connected = False

    def send(self, msg):
        log.info('outgoing message: %s, %s', self.id, msg)
        if isinstance(msg, string_types):
            msg = [msg]
        self.tick()
        self.queue.put_nowait(msg)

    def send_raw(self, msg):
        self.tick()
        self.queue.put_nowait(msg)

    def _messages(self, timeout=None):
        self.tick()
        return self.queue.get(timeout=timeout)

    def open(self):
        log.info('open session: %s', self.id)
        self.tick()
        self.connected = True
        try:
            self.on_open()
        except:
            log.exception("Exceptin in .on_open method.")

    def message(self, msg):
        log.info('incoming message: %s, %s', self.id, msg)
        self.tick()
        try:
            self.on_message(msg)
        except:
            log.exception("Exceptin in .on_message method.")

    def close(self):
        log.info('close session: %s', self.id)
        self.expire()
        try:
            self.on_close()
        except:
            log.exception("Exceptin in .on_message method.")

    def on_open(self):
        """ override in subsclass """

    def on_message(self, msg):
        """ override in subsclass """

    def on_close(self):
        """ override in subsclass """


class SessionManager(object):
    """ A basic session manager """

    _gc_thread = None

    def __init__(self, name, registry, session=Session,
                 gc_cycle=5.0, timeout = timedelta(seconds=10)):
        self.name = 'sockjs-%s'%name
        self.registry = registry
        self.factory = session
        self.sessions = {}
        self.acquired = {}
        self.pool = []
        self.timeout = timeout
        self._gc_cycle = gc_cycle

    def route_url(self, request):
        return request.route_url(self.name)

    def start(self):
        if self._gc_thread is None:
            def _gc_sessions():
                while True:
                    gevent.sleep(self._gc_cycle)
                    self._gc()

            self._gc_thread = gevent.Greenlet(_gc_sessions)

        if not self._gc_thread.started:
            self._gc_thread.start()

    def _gc(self):
        current_time = datetime.now()

        while self.pool:
            expires, session = self.pool[0]

            # Every session is fresh
            if expires > current_time:
                break

            expires, session = heappop(self.pool)
            if session.id not in self.sessions:
                continue

            # Session is to be GC'd immedietely
            if session.expires < current_time:
                del self.sessions[session.id]
                if session.connected:
                    session.close()
                continue
            else:
                heappush(self.pool, (session.expires, session))

    def add(self, session):
        if session.expired:
            raise ValueError("Can't add expired session")

        session.manager = self
        session.registry = self.registry

        self.sessions[session.id] = session
        heappush(self.pool, (session.expires, session))

    def get(self, id):
        return self.sessions.get(id, None)

    def acquire(self, id, create=False):
        session = self.sessions.get(id, None)
        if session is None and create:
            session = self.factory(id, self.timeout)
            self.add(session)

        session.tick()
        session.hits += 1
        self.acquired[session.id] = True
        return session

    def release(self, session):
        if session.id in self.acquired:
            del self.acquired[session.id]

    def active_sessions(self):
        for session in self.sessions.values():
            if not session.expired:
                yield session

    def clear(self):
        """ Manually expire all sessions in the pool. """
        while self.pool:
            expr, session = heappop(self.pool)
            session.expire()
            del self.sessions[session.id]

    def broadcast(self, msg):
        for session in self.sessions.values():
            if not session.expired:
                session.send(msg)

    def __del__(self):
        self.clear()


class GetSessionManager(object):
    """ Pyramid's request.get_sockjs_manager implementation """

    def __init__(self, registry):
        self.registry = registry

    def __call__(self, name=''):
        try:
            return self.registry.__sockjs_managers__[name]
        except AttributeError:
            raise KeyError(name)
