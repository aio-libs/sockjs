import asyncio
from asyncio import ensure_future
from datetime import datetime, timedelta
from unittest import mock

import pytest
from aiohttp import web

from sockjs import (
    Session,
    SessionIsAcquired,
    SessionIsClosed,
    protocol,
    SessionState,
    Frame,
)


class TestSession:
    async def test_ctor(self, mocker):
        dt = mocker.patch("sockjs.session.datetime")
        now = dt.now.return_value = datetime.now()

        session = Session("id")
        assert session.id == "id"
        assert not session.expired
        assert session.expires == now + timedelta(seconds=5)

        assert session._hits == 0
        assert session._heartbeats == 0
        assert session.state == SessionState.NEW

        session = Session("id", disconnect_delay=15)

        assert session.id == "id"
        assert not session.expired
        assert session.expires == now + timedelta(seconds=15)

    async def test_str(self, make_session):
        session = make_session("test")
        session.state = SessionState.OPEN

        assert str(session) == "id='test' connected"

        session._hits = 10
        session._heartbeats = 50
        session.state = SessionState.CLOSING
        assert str(session) == "id='test' disconnected hits=10 heartbeats=50"

        session.feed(Frame.MESSAGE, "msg")
        assert str(session) == "id='test' disconnected queue[1] hits=10 heartbeats=50"

        session.state = SessionState.CLOSED
        assert str(session) == "id='test' closed queue[1] hits=10 heartbeats=50"

        session.state = SessionState.OPEN
        session.acquired = True
        expected = "id='test' connected acquired queue[1] hits=10 heartbeats=50"
        assert str(session) == expected

    async def test_tick(self, mocker, make_session):
        dt = mocker.patch("sockjs.session.datetime")
        now = dt.now.return_value = datetime.now()
        session = make_session("test")

        now = dt.now.return_value = now + timedelta(hours=1)
        session.tick()
        assert session.next_heartbeat == now + timedelta(
            seconds=session.heartbeat_delay
        )

    async def test_tick_different_timeoutk(self, mocker, make_session):
        dt = mocker.patch("sockjs.session.datetime")
        now = dt.now.return_value = datetime.now()
        session = make_session("test", disconnect_delay=20)

        now = dt.now.return_value = now + timedelta(hours=1)
        session.tick()
        assert session.next_heartbeat == now + timedelta(
            seconds=session.heartbeat_delay
        )

    async def test_tick_custom(self, mocker, make_session):
        dt = mocker.patch("sockjs.session.datetime")
        now = dt.now.return_value = datetime.now()
        session = make_session("test", disconnect_delay=20)

        now = dt.now.return_value = now + timedelta(hours=1)
        session.tick(30)
        assert session.next_heartbeat == now + timedelta(seconds=30)

    async def test_heartbeat(self, make_session):
        session = make_session("test")
        session._send_heartbeats = True
        assert session._heartbeats == 0
        session.heartbeat()
        assert session._heartbeats == 1
        session.heartbeat()
        assert session._heartbeats == 2

    async def test_heartbeat_transport(self, make_session):
        session = make_session("test")
        session._send_heartbeats = True
        session.heartbeat()
        assert list(session._queue) == [(Frame.HEARTBEAT, Frame.HEARTBEAT.value)]

    async def test_expire(self, make_session, mocker):
        dt = mocker.patch("sockjs.session.datetime")
        now = dt.now.return_value = datetime.now()

        session = make_session("test", disconnect_delay=5)
        session.expire()
        assert session.expires == now + timedelta(seconds=5)
        assert not session.expired
        dt.now.return_value = now + timedelta(seconds=5)
        assert session.expired

    async def test_send(self, make_session):
        session = make_session("test")
        session.send("message")
        assert list(session._queue) == []

        session.state = SessionState.OPEN
        session.send("message")

        assert list(session._queue) == [(Frame.MESSAGE, ["message"])]

    async def test_send_non_str(self, make_session):
        session = make_session("test")
        with pytest.raises(AssertionError):
            session.send(b"str")

    async def test_send_frame(self, make_session):
        session = make_session("test")
        session.send_frame('a["message"]')
        assert list(session._queue) == []

        session.state = SessionState.OPEN
        session.send_frame('a["message"]')

        assert list(session._queue) == [(Frame.MESSAGE_BLOB, 'a["message"]')]

    async def test_feed(self, make_session):
        session = make_session("test")
        session.feed(Frame.OPEN, Frame.OPEN.value)
        session.feed(Frame.MESSAGE, "msg")
        session.feed(Frame.CLOSE, (3001, "reason"))

        assert list(session._queue) == [
            (Frame.OPEN, Frame.OPEN.value),
            (Frame.MESSAGE, ["msg"]),
            (Frame.CLOSE, (3001, "reason")),
        ]

    async def test_feed_msg_packing(self, make_session):
        session = make_session("test")
        session.feed(Frame.MESSAGE, "msg1")
        session.feed(Frame.MESSAGE, "msg2")
        session.feed(Frame.CLOSE, (3001, "reason"))
        session.feed(Frame.MESSAGE, "msg3")

        assert list(session._queue) == [
            (Frame.MESSAGE, ["msg1", "msg2"]),
            (Frame.CLOSE, (3001, "reason")),
            (Frame.MESSAGE, ["msg3"]),
        ]

    async def test_feed_with_waiter(self, make_session):
        session = make_session("test")
        session._waiter = waiter = asyncio.Future()
        session.feed(Frame.MESSAGE, "msg")

        assert list(session._queue) == [(Frame.MESSAGE, ["msg"])]
        assert session._waiter is None
        assert waiter.done()

    async def test_wait(self, make_session):
        s = make_session("test")
        s.state = SessionState.OPEN

        async def send():
            await asyncio.sleep(0.001)
            s.feed(Frame.MESSAGE, "msg1")

        ensure_future(send())
        frame, payload = await s.get_frame()
        assert frame == Frame.MESSAGE
        assert payload == 'a["msg1"]'

    async def test_wait_closed(self, make_session):
        s = make_session("test")
        s.state = SessionState.CLOSED
        with pytest.raises(SessionIsClosed):
            await s.get_frame()

    async def test_wait_message(self, make_session):
        s = make_session("test")
        s.state = SessionState.OPEN
        s.feed(Frame.MESSAGE, "msg1")
        frame, payload = await s.get_frame()
        assert frame == Frame.MESSAGE
        assert payload == 'a["msg1"]'

    async def test_wait_close(self, make_session):
        s = make_session("test")
        s.state = SessionState.OPEN
        s.feed(Frame.CLOSE, (3000, "Go away!"))
        frame, payload = await s.get_frame()
        assert frame == Frame.CLOSE
        assert payload == 'c[3000,"Go away!"]'

    async def test_wait_message_unpack(self, make_session):
        s = make_session("test")
        s.state = SessionState.OPEN
        s.feed(Frame.MESSAGE, "msg1")
        frame, payload = await s.get_frame(pack=False)
        assert frame == Frame.MESSAGE
        assert payload == ["msg1"]

    async def test_wait_close_unpack(self, make_session):
        s = make_session("test")
        s.state = SessionState.OPEN
        s.feed(Frame.CLOSE, (3000, "Go away!"))
        frame, payload = await s.get_frame(pack=False)
        assert frame == Frame.CLOSE
        assert payload == (3000, "Go away!")

    async def test_close(self, make_session):
        session = make_session("test")
        session.state = SessionState.OPEN
        session.close()
        assert session.state == SessionState.CLOSING
        assert list(session._queue) == [(Frame.CLOSE, (3000, "Go away!"))]

    async def test_close_idempotent(self, make_session):
        session = make_session("test")
        session.state = SessionState.CLOSED
        session.close()
        assert session.state == SessionState.CLOSED
        assert list(session._queue) == []

    async def test_acquire_new_session(
        self,
        make_manager,
        make_session,
        make_request,
        make_handler,
    ):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager)
        assert session.state == SessionState.NEW
        assert session._hb_task is None
        assert not session._send_heartbeats

        await manager.acquire(session, request=make_request("GET", "/test/"))
        assert session.state == SessionState.OPEN
        assert session._send_heartbeats
        assert session._hb_task is not None
        assert list(session._queue) == [(Frame.OPEN, Frame.OPEN.value)]
        assert messages == [(protocol.OPEN_MESSAGE, session)]

        hb_task = session._hb_task
        session.release()
        assert not session._send_heartbeats
        assert session._hb_task is None
        assert hb_task._must_cancel

    async def test_acquire_exception_in_handler(
        self, make_manager, make_session, make_request
    ):
        async def handler(msg, s):
            raise ValueError

        sm = make_manager(handler)
        session = make_session(manager=sm)
        assert session.state == SessionState.NEW

        await sm.acquire(session, request=make_request("GET", "/test/"))
        assert session.state == SessionState.CLOSING
        assert session._send_heartbeats
        assert session.interrupted
        assert list(session._queue) == [
            (Frame.OPEN, Frame.OPEN.value),
            (Frame.CLOSE, (3000, "Internal error")),
        ]

    async def test_remote_close(self, make_session, make_manager, make_handler):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager)

        await manager.remote_close(session)
        assert not session.interrupted
        assert session.state == SessionState.CLOSING
        assert messages == [
            (protocol.SockjsMessage(protocol.MsgType.CLOSE, None), session)
        ]

    async def test_remote_close_idempotent(
        self,
        make_session,
        make_manager,
        make_handler,
    ):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session()
        session.state = SessionState.CLOSED

        await manager.remote_close(session)
        assert session.state == SessionState.CLOSED
        assert messages == []

    async def test_remote_close_with_exc(
        self,
        make_session,
        make_manager,
        make_handler,
    ):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager)

        exc = ValueError()
        await manager.remote_close(session, exc=exc)
        assert session.interrupted
        assert session.state == SessionState.CLOSING
        assert messages == [
            (protocol.SockjsMessage(protocol.MsgType.CLOSE, exc), session)
        ]

    async def test_remote_close_exc_in_handler(
        self,
        make_session,
        make_manager,
        make_handler,
    ):
        handler = make_handler([], exc=True)
        manager = make_manager(handler)
        session = make_session()

        await manager.remote_close(session)
        assert not session.interrupted
        assert session.state == SessionState.CLOSING

    async def test_remote_closed(self, make_session, make_manager, make_handler):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager)

        await manager.remote_closed(session)
        assert session.expires > datetime.now()
        assert not session.expired
        assert session.state == SessionState.NEW
        assert messages == []

        session.expires = datetime.now()
        assert session.expired
        await manager.remote_closed(session)
        assert session.state == SessionState.CLOSED
        assert messages == [(protocol.CLOSED_MESSAGE, session)]

        # Without delay
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(disconnect_delay=0)
        await manager.remote_closed(session)
        assert session.expired
        await manager.remote_closed(session)
        assert session.state == SessionState.CLOSED
        assert messages == [(protocol.CLOSED_MESSAGE, session)]

    async def test_remote_closed_idempotent(
        self,
        make_session,
        make_manager,
        make_handler,
    ):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session()
        session.state = SessionState.CLOSED

        await manager.remote_closed(session)
        assert session.state == SessionState.CLOSED
        assert messages == []

    async def test_remote_closed_with_waiter(
        self,
        make_session,
        make_manager,
        make_handler,
    ):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager, disconnect_delay=0)
        session._waiter = waiter = asyncio.Future()

        now = datetime.now()
        await manager.remote_closed(session)
        assert waiter.done()
        assert session.expires <= now
        assert session.expired
        assert session._waiter is None
        assert session.state == SessionState.CLOSED
        assert messages == [(protocol.CLOSED_MESSAGE, session)]

    async def test_remote_closed_exc_in_handler(
        self,
        make_session,
        make_manager,
        make_handler,
    ):
        handler = make_handler([], exc=True)
        manager = make_manager(handler)
        session = make_session(disconnect_delay=0)

        now = datetime.now()
        await manager.remote_closed(session)
        assert session.expires <= now
        assert session.expired
        assert session.state == SessionState.CLOSED

    async def test_remote_message(self, make_session, make_manager, make_handler):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager)

        await manager.remote_message(session, "msg")
        assert messages == [
            (protocol.SockjsMessage(protocol.MsgType.MESSAGE, "msg"), session)
        ]

    async def test_remote_message_exc(self, make_session, make_manager, make_handler):
        messages = []
        handler = make_handler(messages, exc=True)
        manager = make_manager(handler)
        session = make_session()

        await manager.remote_message(session, "msg")
        assert messages == []

    async def test_remote_messages(self, make_session, make_manager, make_handler):
        messages = []
        handler = make_handler(result=messages)
        manager = make_manager(handler)
        session = make_session(manager=manager)

        await manager.remote_messages(session, ("msg1", "msg2"))
        assert messages == [
            (protocol.SockjsMessage(protocol.MsgType.MESSAGE, "msg1"), session),
            (protocol.SockjsMessage(protocol.MsgType.MESSAGE, "msg2"), session),
        ]

    async def test_remote_messages_exc(self, make_session, make_manager, make_handler):
        messages = []
        handler = make_handler(messages, exc=True)
        manager = make_manager(handler)
        session = make_session()

        await manager.remote_messages(session, ("msg1", "msg2"))
        assert messages == []


class TestSessionManager:
    async def test_request_available(self, make_manager, make_request):
        sm = make_manager()
        s = sm.get("test", True)
        assert s.request is None
        await sm.acquire(s, make_request("GET", "/test/"))
        assert s.request is not None
        assert isinstance(s.request, web.Request)

    async def test_fresh(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        sm._add(s)
        assert "test" in sm.sessions

    async def test_add(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()

        sm._add(s)
        assert "test" in sm.sessions
        assert sm.sessions["test"] is s

    async def test_add_expired(self, make_manager, make_session):
        sm = make_manager()
        session = make_session(disconnect_delay=0)
        session.expire()
        assert session.expires <= datetime.now()

        with pytest.raises(ValueError):
            sm._add(session)

    async def test_get(self, make_manager, make_session):
        sm = make_manager()
        s = make_session()
        with pytest.raises(KeyError):
            sm.get("test")

        sm._add(s)
        assert sm.get("test") is s

    async def test_get_unknown_with_default(self, make_manager):
        sm = make_manager()
        default = object()

        item = sm.get("id", default=default)
        assert item is default

    async def test_get_with_create(self, make_manager):
        sm = make_manager()

        s = sm.get("test", True)
        assert s.id in sm.sessions
        assert isinstance(s, Session)

    async def test_acquire(self, make_manager, make_session, make_request):
        sm = make_manager()
        s1 = make_session()
        sm._add(s1)
        s1.acquire = mock.Mock()
        s1.acquire.return_value = asyncio.Future()
        s1.acquire.return_value.set_result(True)

        s2 = await sm.acquire(s1, request=make_request("GET", "/test/"))

        assert s1 is s2
        assert s1.id in sm.acquired
        assert sm.acquired[s1.id]
        assert sm.is_acquired(s1)
        assert s1.acquire.called

    async def test_acquire_unknown(self, make_manager, make_session, make_request):
        sm = make_manager()
        s = make_session()
        with pytest.raises(KeyError):
            await sm.acquire(s, request=make_request("GET", "/test/"))

    async def test_acquire_locked(self, make_manager, make_session, make_request):
        sm = make_manager()
        s = make_session()
        sm._add(s)
        await sm.acquire(s, request=make_request("GET", "/test/"))

        with pytest.raises(SessionIsAcquired):
            await sm.acquire(s, request=make_request("GET", "/test/"))

    async def test_release(self, make_manager, make_request):
        sm = make_manager()
        s = sm.get("test", True)
        s.release = mock.Mock()

        await sm.acquire(s, request=make_request("GET", "/test/"))
        await sm.release(s)

        assert "test" not in sm.acquired
        assert not sm.is_acquired(s)
        assert s.release.called

    async def test_active_sessions(self, make_manager):
        sm = make_manager()

        s1 = sm.get("test1", True)
        s2 = sm.get("test2", True)
        s2.disconnect_delay = 0
        s2.expire()

        active = list(sm.active_sessions())
        assert len(active) == 1
        assert s1 in active

    async def test_broadcast(self, make_manager):
        sm = make_manager()

        s1 = sm.get("test1", True)
        s1.state = SessionState.OPEN
        s2 = sm.get("test2", True)
        s2.state = SessionState.OPEN
        sm.broadcast("msg")

        assert list(s1._queue) == [(Frame.MESSAGE_BLOB, 'a["msg"]')]
        assert list(s2._queue) == [(Frame.MESSAGE_BLOB, 'a["msg"]')]

    async def test_clear(self, make_manager):
        sm = make_manager()

        s1 = sm.get("s1", True)
        s1.state = SessionState.OPEN
        s2 = sm.get("s2", True)
        s2.state = SessionState.OPEN

        await sm.clear()

        assert not bool(sm.sessions)
        assert s1.expired
        assert s2.expired
        assert s1.state == SessionState.CLOSED
        assert s2.state == SessionState.CLOSED

    async def test_gc_task(self, make_manager):
        sm = make_manager()
        assert not sm.started
        assert sm._gc_task is None

        sm.start()
        assert sm.started
        assert sm._gc_task is not None

        gc_task = sm._gc_task

        await sm.stop()
        assert not sm.started
        assert sm._gc_task is None
        assert gc_task._must_cancel

    async def test_gc_expire(self, make_manager, make_session, make_request):
        sm = make_manager()
        s = make_session(manager=sm)
        await sm.acquire(s, request=make_request("GET", "/test/"))
        await sm.release(s)

        now = datetime.now()
        s.expires = now - timedelta(seconds=30)
        assert s.expired

        await sm._gc_expired_sessions()
        assert s.id not in sm.sessions
        assert s.expired
        assert s.state == SessionState.CLOSED

    async def test_gc_expire_acquired(self, make_manager, make_session, make_request):
        sm = make_manager()
        s = make_session(manager=sm)
        await sm.acquire(s, request=make_request("GET", "/test/"))
        s.expires = datetime.now() - timedelta(seconds=30)
        await sm._gc_expired_sessions()

        assert s.id not in sm.sessions
        assert s.id not in sm.acquired
        assert s.expired
        assert s.state == SessionState.CLOSED

    async def test_gc_one_expire(self, make_manager, make_session, make_request):
        sm = make_manager()
        s1 = make_session("id1", manager=sm)
        s2 = make_session("id2", manager=sm)
        await sm.acquire(s1, request=make_request("GET", "/test/"))
        await sm.acquire(s2, request=make_request("GET", "/test/"))
        await sm.release(s1)
        await sm.release(s2)

        s1.expires = datetime.now() - timedelta(seconds=30)

        await sm._gc_expired_sessions()
        assert s1.id not in sm.sessions
        assert s2.id in sm.sessions

    async def test_emits_warning_on_del(self, make_manager, make_session):
        sm = make_manager()
        make_session("id1", manager=sm)
        make_session("id2", manager=sm)

        with pytest.warns(RuntimeWarning) as warning:
            getattr(sm, "__del__")()
            msg = "Please call `await SessionManager.stop()` before del"
            assert warning[0].message.args[0] == msg

    async def test_does_not_emits_warning_on_del_if_no_sessions(
        self, make_manager, make_session
    ):
        sm = make_manager()
        make_session("id1", manager=sm)
        make_session("id2", manager=sm)

        await sm.clear()
        getattr(sm, "__del__")()
