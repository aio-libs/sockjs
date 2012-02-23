import gevent
from datetime import datetime, timedelta

from base import BaseTestCase


class SessionTestCase(BaseTestCase):

    def setUp(self):
        super(SessionTestCase, self).setUp()

        self.now = datetime.now()
        test_self = self

        class DateTime(object):

            def now(self):
                return test_self.now

        from pyramid_sockjs import session
        session.datetime = DateTime()

    def tearDown(self):
        from pyramid_sockjs import session
        session.datetime = datetime

        super(SessionTestCase, self).tearDown()

    def test_ctor(self):
        from pyramid_sockjs import Session, STATE_NEW
        session = Session('id')

        self.assertEqual(session.id, 'id')
        self.assertEqual(session.expired, False)
        self.assertEqual(session.expires, self.now + timedelta(seconds=10))

        self.assertEqual(session.hits, 0)
        self.assertEqual(session.heartbeats, 0)
        self.assertEqual(session.state, STATE_NEW)

        session = Session('id', timedelta(seconds=15))

        self.assertEqual(session.id, 'id')
        self.assertEqual(session.expired, False)
        self.assertEqual(session.expires, self.now + timedelta(seconds=15))

    def test_str(self):
        from pyramid_sockjs import Session, STATE_OPEN, STATE_CLOSING
        session = Session('test')
        session.hits = 10
        session.heartbeats = 50
        session.state = STATE_OPEN

        self.assertEqual(str(session),
                         "id='test' connected hits=10 heartbeats=50")

        session.state = STATE_CLOSING
        self.assertEqual(str(session),
                         "id='test' disconnected hits=10 heartbeats=50")

        session.send('msg')
        self.assertEqual(
            str(session),
            "id='test' disconnected queue[1] hits=10 heartbeats=50")

    def test_tick(self):
        from pyramid_sockjs import Session
        session = Session('id')

        self.now = self.now + timedelta(hours=1)
        session.tick()
        self.assertEqual(session.expires, self.now + session.timeout)

    def test_tick_different_timeout(self):
        from pyramid_sockjs import Session
        session = Session('id', timedelta(seconds=20))

        self.now = self.now + timedelta(hours=1)
        session.tick()
        self.assertEqual(session.expires, self.now + timedelta(seconds=20))

    def test_tick_custom(self):
        from pyramid_sockjs import Session
        session = Session('id', timedelta(seconds=20))

        self.now = self.now + timedelta(hours=1)
        session.tick(timedelta(seconds=30))
        self.assertEqual(session.expires, self.now + timedelta(seconds=30))

    def test_heartbeat(self):
        from pyramid_sockjs import Session
        session = Session('id')

        self.assertEqual(session.heartbeats, 0)

        session.heartbeat()
        self.assertEqual(session.heartbeats, 1)

        session.heartbeat()
        self.assertEqual(session.heartbeats, 2)

    def test_expire(self):
        from pyramid_sockjs import Session
        session = Session('id')

        session.expired = False

        session.expire()
        self.assertTrue(session.expired)

    def test_send(self):
        from pyramid_sockjs import Session, protocol
        session = Session('id')

        session.send(['message'])
        self.assertEqual(session.queue.get(), ['message'])

    def test_send_string(self):
        from pyramid_sockjs import Session, protocol
        session = Session('id')

        session.send('message')
        self.assertEqual(session.queue.get(), 'message')

    def test_send_tick(self):
        from pyramid_sockjs import Session, protocol
        session = Session('id')

        self.now = self.now + timedelta(hours=1)

        session.send(['message'])
        self.assertEqual(session.expires, self.now + session.timeout)

    def test_get_transport_message(self):
        from pyramid_sockjs import Session
        session = Session('id')

        session.send('message')
        self.assertEqual(session.get_transport_message(), 'message')

        from gevent.queue import Empty

        self.assertRaises(
            Empty, session.get_transport_message, timeout=0.1)

    def test_get_transport_message_tick(self):
        from pyramid_sockjs import Session
        session = Session('id')

        session.send('message')

        self.now = self.now + timedelta(hours=1)

        session.get_transport_message()

        self.assertEqual(session.expires, self.now + session.timeout)

    def test_open(self):
        from pyramid_sockjs import Session, STATE_OPEN
        session = Session('id')
        session.open()
        self.assertEqual(session.state, STATE_OPEN)

    def test_open_on_open(self):
        from pyramid_sockjs import Session

        opened = []

        class TestSession(Session):
            def on_open(self):
                opened.append(True)

        session = TestSession('id')
        session.open()

        self.assertTrue(opened[0])

    def test_open_on_open_exception(self):
        from pyramid_sockjs import Session, STATE_OPEN
        class TestSession(Session):
            def on_open(self):
                raise Exception()

        session = TestSession('id')
        session.open()
        self.assertEqual(session.state, STATE_OPEN)

    def test_message(self):
        from pyramid_sockjs import Session
        session = Session('id')
        session.open()

        self.now = self.now + timedelta(hours=1)

        session.message('message')

        self.assertEqual(session.expires, self.now + session.timeout)

    def test_message_on_message(self):
        from pyramid_sockjs import Session

        messages = []

        class TestSession(Session):
            def on_message(self, msg):
                messages.append(msg)

        session = TestSession('id')
        session.open()
        session.message('message')

        self.assertEqual(messages[0], 'message')

    def test_message_on_message_exception(self):
        from pyramid_sockjs import Session
        class TestSession(Session):
            def on_message(self, msg):
                raise Exception()

        session = TestSession('id')
        session.open()

        err = None
        try:
            session.message('message')
        except Exception as exc: # pragma: no cover
            err = exc

        self.assertIsNone(err)

    def test_close(self):
        from pyramid_sockjs import Session, STATE_CLOSING
        session = Session('id')
        session.open()
        session.close()
        self.assertFalse(session.expired)
        self.assertEqual(session.state, STATE_CLOSING)

    def test_close_event(self):
        from pyramid_sockjs import Session

        closing = []
        class TestSession(Session):
            def on_close(self):
                closing.append(True)

        session = TestSession('id')
        session.open()
        session.close()
        self.assertTrue(closing[0])

    def test_close_on_message_exception(self):
        from pyramid_sockjs import Session
        class TestSession(Session):
            def on_close(self):
                raise Exception()

        session = TestSession('id')
        session.open()

        err = None
        try:
            session.close()
        except Exception as exc: # pragma: no cover
            err = exc

        self.assertIsNone(err)

    def test_closed(self):
        from pyramid_sockjs import Session, STATE_CLOSED
        session = Session('id')
        session.open()
        session.closed()
        self.assertTrue(session.expired)
        self.assertEqual(session.state, STATE_CLOSED)

    def test_closed_event(self):
        from pyramid_sockjs import Session

        closed = []
        class TestSession(Session):
            def on_closed(self):
                closed.append(True)

        session = TestSession('id')
        session.open()
        session.closed()
        self.assertTrue(closed[0])

    def test_closed_on_message_exception(self):
        from pyramid_sockjs import Session, STATE_CLOSED
        class TestSession(Session):
            def on_closed(self):
                raise Exception()

        session = TestSession('id')
        session.open()

        err = None
        try:
            session.closed()
        except Exception as exc: # pragma: no cover
            err = exc

        self.assertIsNone(err)
        self.assertEqual(session.state, STATE_CLOSED)


class GcThreadTestCase(BaseTestCase):

    def setUp(self):
        super(GcThreadTestCase, self).setUp()

        self.gc_executed = False

        def gc(s):
            self.gc_executed = True # pragma: no cover

        from pyramid_sockjs.session import SessionManager

        self.gc_origin = SessionManager._gc
        SessionManager._gc = gc

    def tearDown(self):
        from pyramid_sockjs.session import SessionManager
        SessionManager._gc = self.gc_origin

        super(GcThreadTestCase, self).tearDown()

    def test_gc_thread(self):
        from pyramid_sockjs.session import SessionManager

        sm = SessionManager('sm', self.registry, gc_cycle=0.1)
        sm.start()
        sm.stop()
        #self.assertTrue(self.gc_executed)


class SessionManagerTestCase(BaseTestCase):

    def setUp(self):
        super(SessionManagerTestCase, self).setUp()

        self.now = datetime.now()
        test_self = self

        class DateTime(object):

            def now(self):
                return test_self.now

        from pyramid_sockjs import session
        session.datetime = DateTime()

    def tearDown(self):
        from pyramid_sockjs import session
        session.datetime = datetime

        super(SessionManagerTestCase, self).tearDown()

    def make_one(self):
        from pyramid_sockjs.session import Session, SessionManager
        return Session, SessionManager('sm', self.registry)

    def test_fresh(self):
        Session, sm = self.make_one()

        sm._add(Session('id'))
        sm._gc()

        self.assertIn('id', sm)

    def test_gc_removed(self):
        Session, sm = self.make_one()

        sm._add(Session('id'))
        del sm['id']

        self.assertEqual(len(sm.pool), 1)
        sm._gc()

        self.assertEqual(len(sm.pool), 0)

    def test_gc_expire(self):
        from pyramid_sockjs import STATE_CLOSED
        Session, sm = self.make_one()

        session = Session('id')
        session.open()

        sm._add(session)

        self.now = session.expires + timedelta(seconds=10)

        sm._gc()
        self.assertNotIn('id', sm)
        self.assertTrue(session.expired)
        self.assertEqual(session.state, STATE_CLOSED)

    def test_gc_expire_acquired(self):
        from pyramid_sockjs import STATE_CLOSED
        Session, sm = self.make_one()

        session = Session('id')
        session.open()

        sm._add(session)
        sm.acquired['id'] = session

        self.now = session.expires + timedelta(seconds=10)

        sm._gc()
        self.assertNotIn('id', sm)
        self.assertNotIn('id', sm.acquired)
        self.assertTrue(session.expired)
        self.assertEqual(session.state, STATE_CLOSED)

    def test_gc_one_expire(self):
        Session, sm = self.make_one()

        session1 = Session('id1')
        session1.open()

        session2 = Session('id2')
        session2.open()

        sm._add(session1)
        sm._add(session2)

        self.now = session1.expires + timedelta(seconds=10)

        session2.tick()

        sm._gc()
        self.assertNotIn('id1', sm)
        self.assertIn('id2', sm)

    def test_add(self):
        Session, sm = self.make_one()
        session = Session('id')

        sm._add(session)
        self.assertIn('id', sm)
        self.assertIs(sm['id'], session)
        self.assertIs(sm.pool[0][1], session)
        self.assertIs(session.manager, sm)
        self.assertIs(session.registry, sm.registry)

    def test_add_expired(self):
        Session, sm = self.make_one()

        session = Session('id')
        session.expire()

        self.assertRaises(ValueError, sm._add, session)

    def test_get(self):
        Session, sm = self.make_one()
        session = Session('id')

        sm._add(session)
        self.assertIs(sm.get('id'), session)

    def test_get_unknown(self):
        Session, sm = self.make_one()
        self.assertRaises(KeyError, sm.get, 'id')

    def test_get_with_create(self):
        Session, sm = self.make_one()

        session = sm.get('id', True)
        self.assertIn(session.id, sm)
        self.assertIsInstance(session, Session)

    def test_acquire(self):
        Session, sm = self.make_one()

        session = Session('id')
        sm._add(session)

        self.now = self.now + timedelta(hours=1)

        request = object()

        s = sm.acquire(session, request=request)

        self.assertIs(s, session)
        self.assertIs(s.request, request)
        self.assertIn('id', sm.acquired)
        self.assertTrue(sm.acquired['id'])
        self.assertTrue(sm.is_acquired(s))
        self.assertEqual(session.expires, self.now + timedelta(seconds=10))

    def test_acquire_unknown(self):
        Session, sm = self.make_one()
        session = Session('id')

        self.assertRaises(KeyError, sm.acquire, session)

    def test_acquire_locked(self):
        Session, sm = self.make_one()
        session = Session('id')
        sm._add(session)

        s = sm.acquire(session)

        self.assertRaises(KeyError, sm.acquire, session)

    def test_release(self):
        Session, sm = self.make_one()

        session = sm.get('id', True)

        request = object()

        s = sm.acquire(session, request)
        sm.release(s)

        self.assertNotIn('id', sm.acquired)
        self.assertIsNone(s.request)

    def test_active_sessions(self):
        Session, sm = self.make_one()

        s1 = Session('s1')
        s2 = Session('s2')

        sm._add(s1)
        sm._add(s2)

        s2.expire()

        active = list(sm.active_sessions())
        self.assertEqual(len(active), 1)
        self.assertIn(s1, active)

    def test_broadcast(self):
        Session, sm = self.make_one()

        s1 = Session('s1')
        s2 = Session('s2')
        sm._add(s1)
        sm._add(s2)

        sm.broadcast('msg')
        self.assertEqual(s1.get_transport_message(), 'msg')
        self.assertEqual(s2.get_transport_message(), 'msg')

    def test_clear(self):
        from pyramid_sockjs.session import STATE_CLOSED

        Session, sm = self.make_one()

        s1 = Session('s1')
        s1.open()
        s2 = Session('s2')
        s2.open()

        sm._add(s1)
        sm._add(s2)

        sm.clear()

        self.assertFalse(bool(sm))
        self.assertTrue(s1.expired)
        self.assertTrue(s2.expired)
        self.assertEqual(s1.state, STATE_CLOSED)
        self.assertEqual(s2.state, STATE_CLOSED)
