import asyncio

from sockjs.transports import WebSocketTransport

from test_base import BaseSockjsTestCase


class WebSocketTransportTests(BaseSockjsTestCase):
    TRANSPORT_CLASS = WebSocketTransport

    def make_mock_coro(self, return_value=None, raise_exception=None):

        @asyncio.coroutine
        def maked_coro(*args, **kwargs):
            maked_coro.called = True
            maked_coro.args = args
            maked_coro.kwargs = kwargs
            if raise_exception:
                raise raise_exception
            return return_value

        maked_coro.called = False

        return maked_coro

    def test_process_release_acquire_and_remote_closed(self):
        transp = self.make_transport()
        transp.session.interrupted = False
        transp.manager.acquire = self.make_mock_coro()
        transp.manager.release = self.make_mock_coro()
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 101)
        self.assertEqual(resp.headers.get('upgrade', '').lower(), 'websocket')
        self.assertEqual(resp.headers.get('connection', '').lower(), 'upgrade')

        transp.session._remote_closed.assert_called_once_with()
        self.assertTrue(transp.manager.acquire.called)
        self.assertTrue(transp.manager.release.called)
