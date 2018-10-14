import asyncio
from unittest import mock
from datetime import datetime, timedelta

from aiohttp import web

import pytest

from asyncio import ensure_future

from sockjs import Session, SessionIsClosed, protocol, SessionIsAcquired


class TestSession:

    def test_ctor(self, mocker, make_handler, make_request, loop):
        dt = mocker.patch('sockjs.session.datetime')
        now = dt.now.return_value = datetime.now()

        handler = make_handler([])
        request = make_request("GET", "/TestPath")
        session = Session('id', handler, request, loop=loop)

        assert session.id == 'id'
        assert not session.expired
        assert session.expires == now + timedelta(seconds=10)

        assert session._hits == 0
        assert session._heartbeats == 0
        assert session.state == protocol.STATE_NEW

        session = Session('id', handler, request,
                          timeout=timedelta(seconds=15))

        assert session.id == 'id'
        assert not session.expired
        assert session.expires == now + timedelta(seconds=15)

    def test_str(self, make_session):
        session = make_session('test')
        session.state = protocol.STATE_OPEN

        assert str(session) == "id='test' connected"

        session._hits = 10
        session._heartbeats = 50
        session.state = protocol.STATE_CLOSING
        assert str(session) == "id='test' disconnected hits=10 heartbeats=50"

        session._feed(protocol.FRAME_MESSAGE, 'msg')
        assert str(session) == \
            "id='test' disconnected queue[1] hits=10 heartbeats=50"

        session.state = protocol.STATE_CLOSED
        assert str(session) == \
            "id='test' closed queue[1] hits=10 heartbeats=50"

        session.state = protocol.STATE_OPEN
        session.acquired = True
        assert str(session) == \
            "id='test' connected acquired queue[1] hits=10 heartbeats=50"

    def test_tick(self, mocker, make_session):
        dt = mocker.patch('sockjs.session.datetime')
        now = dt.now.return_value = datetime.now()
        session = make_session('test')

        now = dt.now.return_value = now + timedelta(hours=1)
        session._tick()
        assert session.expires == now + session.timeout

    def test_tick_different_timeoutk(self, mocker, make_session):
        dt = mocker.patch('sockjs.session.datetime')
        now = dt.now.return_value = datetime.now()
        session = make_session('test', timeout=timedelta(seconds=20))

        now = dt.now.return_value = now + timedelta(hours=1)
        session._tick()
        assert session.expires == now + timedelta(seconds=20)

    def test_tick_custom(self, mocker, make_session):
        dt = mocker.patch('sockjs.session.datetime')
        now = dt.now.return_value = datetime.now()
        session = make_session('test', timeout=timedelta(seconds=20))

        now = dt.now.return_value = now + timedelta(hours=1)
        session._tick(timedelta(seconds=30))
        assert session.expires == now + timedelta(seconds=30)

    def test_heartbeat(self, make_session):
        session = make_session('test')
        assert session._heartbeats == 0
        session._heartbeat()
        assert session._heartbeats == 1
        session._heartbeat()
        assert session._heartbeats == 2

    def test_heartbeat_transport(self, make_session):
        session = make_session('test')
        session._heartbeat_transport = True
        session._heartbeat()
        assert list(session._queue) == \
            [(protocol.FRAME_HEARTBEAT, protocol.FRAME_HEARTBEAT)]

    def test_expire(self, make_session):
        session = make_session('test')
        assert not session.expired

        session.expire()
        assert session.expired

    def test_send(self, make_session):
        session = make_session('test')
        session.send('message')
        assert list(session._queue) == []

        session.state = protocol.STATE_OPEN
        session.send('message')

        assert list(session._queue) == \
            [(protocol.FRAME_MESSAGE, ['message'])]

    def test_send_non_str(self, make_session):
        session = make_session('test')
        with pytest.raises(AssertionError):
            session.send(b'str')

    def test_send_frame(self, make_session):
        session = make_session('test')
        session.send_frame('a["message"]')
        assert list(session._queue) == []

        session.state = protocol.STATE_OPEN
        session.send_frame('a["message"]')

        assert list(session._queue) == \
            [(protocol.FRAME_MESSAGE_BLOB, 'a["message"]')]

    def test_feed(self, make_session):
        session = make_session('test')
        session._feed(protocol.FRAME_OPEN, protocol.FRAME_OPEN)
        session._feed(protocol.FRAME_MESSAGE, 'msg')
        session._feed(protocol.FRAME_CLOSE, (3001, 'reason'))

        assert list(session._queue) == \
            [(protocol.FRAME_OPEN, protocol.FRAME_OPEN),
             (protocol.FRAME_MESSAGE, ['msg']),
             (protocol.FRAME_CLOSE, (3001, 'reason'))]

    def test_feed_msg_packing(self, make_session):
        session = make_session('test')
        session._feed(protocol.FRAME_MESSAGE, 'msg1')
        session._feed(protocol.FRAME_MESSAGE, 'msg2')
        session._feed(protocol.FRAME_CLOSE, (3001, 'reason'))
        session._feed(protocol.FRAME_MESSAGE, 'msg3')

        assert list(session._queue) == \
            [(protocol.FRAME_MESSAGE, ['msg1', 'msg2']),
             (protocol.FRAME_CLOSE, (3001, 'reason')),
             (protocol.FRAME_MESSAGE, ['msg3'])]

    def test_feed_with_waiter(self, make_session, loop):
        session = make_session('test')
        session._waiter = waiter = asyncio.Future(loop=loop)
        session._feed(protocol.FRAME_MESSAGE, 'msg')

        assert list(session._queue) == \
            [(protocol.FRAME_MESSAGE, ['msg'])]
        assert session._waiter is None
        assert waiter.done()

    async def test_wait(self, make_session, loop):
        s = make_session('test')
        s.state = protocol.STATE_OPEN

        async def send():
            await asyncio.sleep(0.001, loop=loop)
            s._feed(protocol.FRAME_MESSAGE, 'msg1')

        ensure_future(send(), loop=loop)
        frame, payload = await s._wait()
        assert frame == protocol.FRAME_MESSAGE
        assert payload == 'a["msg1"]'

    async def test_wait_closed(self, make_session):
        s = make_session('test')
        s.state = protocol.STATE_CLOSED
        with pytest.raises(SessionIsClosed):
            await s._wait()

    async def test_wait_message(self, make_session):
        s = make_session('test')
        s.state = protocol.STATE_OPEN
        s._feed(protocol.FRAME_MESSAGE, 'msg1')
        frame, payload = await s._wait()
        assert frame == protocol.FRAME_MESSAGE
        assert payload == 'a["msg1"]'

    async def test_wait_close(self, make_session):
        s = make_session('test')
        s.state = protocol.STATE_OPEN
        s._feed(protocol.FRAME_CLOSE, (3000, 'Go away!'))
        frame, payload = await s._wait()
        assert frame == protocol.FRAME_CLOSE
        assert payload == 'c[3000,"Go away!"]'

    async def test_wait_message_unpack(self, make_session):
        s = make_session('test')
        s.state = protocol.STATE_OPEN
        s._feed(protocol.FRAME_MESSAGE, 'msg1')
        frame, payload = await s._wait(pack=False)
        assert frame == protocol.FRAME_MESSAGE
        assert payload == ['msg1']

    async def test_wait_close_unpack(self, make_session):
        s = make_session('test')
        s.state = protocol.STATE_OPEN
        s._feed(protocol.FRAME_CLOSE, (3000, 'Go away!'))
        frame, payload = await s._wait(pack=False)
        assert frame == protocol.FRAME_CLOSE
        assert payload == (3000, 'Go away!')

    def test_close(self, make_session):
        session = make_session('test')
        session.state = protocol.STATE_OPEN
        session.close()
        assert session.state == protocol.STATE_CLOSING
        assert list(session._queue) == \
            [(protocol.FRAME_CLOSE, (3000, 'Go away!'))]

    def test_close_idempotent(self, make_session):
        session = make_session('test')
        session.state = protocol.STATE_CLOSED
        session.close()
        assert session.state == protocol.STATE_CLOSED
        assert list(session._queue) == []

    async def test_acquire_new_session(self, make_session):
        manager = object()
        messages = []

        session = make_session(result=messages)
        assert session.state == protocol.STATE_NEW

        await session._acquire(manager)
        assert session.state == protocol.STATE_OPEN
        assert session.manager is manager
        assert session._heartbeat_transport
        assert list(session._queue) == \
            [(protocol.FRAME_OPEN, protocol.FRAME_OPEN)]
        assert messages == [(protocol.OpenMessage, session)]

    async def test_acquire_exception_in_handler(self, make_session):

        async def handler(msg, s):
            raise ValueError

        session = make_session(handler=handler)
        assert session.state == protocol.STATE_NEW

        await session._acquire(object())
        assert session.state == protocol.STATE_CLOSING
        assert session._heartbeat_transport
        assert session.interrupted
        assert list(session._queue) == \
            [(protocol.FRAME_OPEN, protocol.FRAME_OPEN),
             (protocol.FRAME_CLOSE, (3000, 'Internal error'))]

    async def test_remote_close(self, make_session):
        messages = []
        session = make_session(result=messages)

        await session._remote_close()
        assert not session.interrupted
        assert session.state == protocol.STATE_CLOSING
        assert messages == \
            [(protocol.SockjsMessage(
                protocol.MSG_CLOSE, None), session)]

    async def test_remote_close_idempotent(self, make_session):
        messages = []
        session = make_session(result=messages)
        session.state = protocol.STATE_CLOSED

        await session._remote_close()
        assert session.state == protocol.STATE_CLOSED
        assert messages == []

    async def test_remote_close_with_exc(self, make_session):
        messages = []
        session = make_session(result=messages)

        exc = ValueError()
        await session._remote_close(exc=exc)
        assert session.interrupted
        assert session.state == protocol.STATE_CLOSING
        assert messages == \
            [(protocol.SockjsMessage(protocol.MSG_CLOSE, exc),
              session)]

    async def test_remote_close_exc_in_handler(self,
                                               make_session, make_handler):
        handler = make_handler([], exc=True)
        session = make_session(handler=handler)

        await session._remote_close()
        assert not session.interrupted
        assert session.state == protocol.STATE_CLOSING

    async def test_remote_closed(self, make_session):
        messages = []
        session = make_session(result=messages)

        await session._remote_closed()
        assert session.expired
        assert session.state == protocol.STATE_CLOSED
        assert messages == [(protocol.ClosedMessage, session)]

    async def test_remote_closed_idempotent(self, make_session):
        messages = []
        session = make_session(result=messages)
        session.state = protocol.STATE_CLOSED

        await session._remote_closed()
        assert session.state == protocol.STATE_CLOSED
        assert messages == []

    async def test_remote_closed_with_waiter(self, make_session, loop):
        messages = []
        session = make_session(result=messages)
        session._waiter = waiter = asyncio.Future(loop=loop)

        await session._remote_closed()
        assert waiter.done()
        assert session.expired
        assert session._waiter is None
        assert session.state == protocol.STATE_CLOSED
        assert messages == [(protocol.ClosedMessage, session)]

    async def test_remote_closed_exc_in_handler(self,
                                                make_handler, make_session):
        handler = make_handler([], exc=True)
        session = make_session(handler=handler)

        await session._remote_closed()
        assert session.expired
        assert session.state == protocol.STATE_CLOSED

    async def test_remote_message(self, make_session):
        messages = []
        session = make_session(result=messages)

        await session._remote_message('msg')
        assert messages == \
            [(protocol.SockjsMessage(protocol.MSG_MESSAGE, 'msg'),
              session)]

    async def test_remote_message_exc(self, make_handler, make_session):
        messages = []
        handler = make_handler(messages, exc=True)
        session = make_session(handler=handler)

        await session._remote_message('msg')
        assert messages == []

    async def test_remote_messages(self, make_session):
        messages = []
        session = make_session(result=messages)

        await session._remote_messages(('msg1', 'msg2'))
        assert messages == \
            [(protocol.SockjsMessage(protocol.MSG_MESSAGE, 'msg1'),
              session),
             (protocol.SockjsMessage(protocol.MSG_MESSAGE, 'msg2'),
              session)]

    async def test_remote_messages_exc(self, make_handler, make_session):
        messages = []
        handler = make_handler(messages, exc=True)
        session = make_session(handler=handler)

        await session._remote_messages(('msg1', 'msg2'))
        assert messages == []


class TestSessionManager:

    def test_request_available(self, make_manager, make_request):
        sm = make_manager()
        s = sm.get('test', True, make_request('GET', '/test/'))
        assert isinstance(s.request, web.Request)

    def test_fresh(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        sm._add(s)
        assert 'test' in sm

    def test_add(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()

        sm._add(s)
        assert 'test' in sm
        assert sm['test'] is s
        assert s.manager is sm

    def test_add_expired(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        s.expire()

        with pytest.raises(ValueError):
            sm._add(s)

    def test_get(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        with pytest.raises(KeyError):
            sm.get('test')

        sm._add(s)
        assert sm.get('test') is s

    def test_get_unknown_with_default(self, make_manager):
        sm = make_manager()
        default = object()

        item = sm.get('id', default=default)
        assert item is default

    def test_get_with_create(self, make_manager):
        sm = make_manager()

        s = sm.get('test', True)
        assert s.id in sm
        assert isinstance(s, Session)

    async def test_acquire(self, make_manager, make_session, loop):
        sm = make_manager()
        s1 = make_session()
        sm._add(s1)
        s1._acquire = mock.Mock()
        s1._acquire.return_value = asyncio.Future(loop=loop)
        s1._acquire.return_value.set_result(1)

        s2 = await sm.acquire(s1)

        assert s1 is s2
        assert s1.id in sm.acquired
        assert sm.acquired[s1.id]
        assert sm.is_acquired(s1)
        assert s1._acquire.called

    async def test_acquire_unknown(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        with pytest.raises(KeyError):
            await sm.acquire(s)

    async def test_acquire_locked(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        sm._add(s)
        await sm.acquire(s)

        with pytest.raises(SessionIsAcquired):
            await sm.acquire(s)

    async def test_release(self, make_manager):
        sm = make_manager()
        s = sm.get('test', True)
        s._release = mock.Mock()

        await sm.acquire(s)
        await sm.release(s)

        assert 'test' not in sm.acquired
        assert not sm.is_acquired(s)
        assert s._release.called

    def test_active_sessions(self, make_manager):
        sm = make_manager()

        s1 = sm.get('test1', True)
        s2 = sm.get('test2', True)
        s2.expire()

        active = list(sm.active_sessions())
        assert len(active) == 1
        assert s1 in active

    def test_broadcast(self, make_manager):
        sm = make_manager()

        s1 = sm.get('test1', True)
        s1.state = protocol.STATE_OPEN
        s2 = sm.get('test2', True)
        s2.state = protocol.STATE_OPEN
        sm.broadcast('msg')

        assert list(s1._queue) == [(protocol.FRAME_MESSAGE_BLOB, 'a["msg"]')]
        assert list(s2._queue) == [(protocol.FRAME_MESSAGE_BLOB, 'a["msg"]')]

    async def test_clear(self, make_manager):
        sm = make_manager()

        s1 = sm.get('s1', True)
        s1.state = protocol.STATE_OPEN
        s2 = sm.get('s2', True)
        s2.state = protocol.STATE_OPEN

        await sm.clear()

        assert not bool(sm)
        assert s1.expired
        assert s2.expired
        assert s1.state == protocol.STATE_CLOSED
        assert s2.state == protocol.STATE_CLOSED

    def test_heartbeat(self, make_manager):
        sm = make_manager()
        assert not sm.started
        assert sm._hb_task is None

        sm.start()
        assert sm.started
        assert sm._hb_handle is not None

        sm._heartbeat()
        assert sm._hb_task is not None

        hb_task = sm._hb_task

        sm.stop()
        assert not sm.started
        assert sm._hb_handle is None
        assert sm._hb_task is None
        assert hb_task._must_cancel

    async def test_heartbeat_task(self, make_manager):
        sm = make_manager()
        sm._hb_task = mock.Mock()

        await sm._heartbeat_task()
        assert sm.started
        assert sm._hb_task is None

    async def test_gc_expire(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()

        sm._add(s)
        await sm.acquire(s)
        await sm.release(s)

        s.expires = datetime.now() - timedelta(seconds=30)

        await sm._heartbeat_task()
        assert s.id not in sm
        assert s.expired
        assert s.state == protocol.STATE_CLOSED

    async def test_gc_expire_acquired(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        sm._add(s)
        await sm.acquire(s)
        s.expires = datetime.now() - timedelta(seconds=30)
        await sm._heartbeat_task()

        assert s.id not in sm
        assert s.id not in sm.acquired
        assert s.expired
        assert s.state == protocol.STATE_CLOSED

    async def test_gc_one_expire(self, make_manager, make_session):
        sm = make_manager()
        s1 = make_session('id1')
        s2 = make_session('id2')

        sm._add(s1)
        sm._add(s2)
        await sm.acquire(s1)
        await sm.acquire(s2)
        await sm.release(s1)
        await sm.release(s2)

        s1.expires = datetime.now() - timedelta(seconds=30)

        await sm._heartbeat_task()
        assert s1.id not in sm
        assert s2.id in sm

    async def test_emits_warning_on_del(self, make_manager, make_session):

        sm = make_manager()
        s1 = make_session('id1')
        s2 = make_session('id2')

        sm._add(s1)
        sm._add(s2)

        with pytest.warns(RuntimeWarning) as warning:
            getattr(sm, '__del__')()
            msg = 'Unclosed sessions! Please call ' \
                '`await SessionManager.clear()` before del'
            assert warning[0].message.args[0] == msg

    async def test_does_not_emits_warning_on_del_if_no_sessions(self,
                                                                make_manager,
                                                                make_session):

        sm = make_manager()
        s1 = make_session('id1')
        s2 = make_session('id2')

        sm._add(s1)
        sm._add(s2)

        await sm.clear()
        getattr(sm, '__del__')()
