from unittest import mock

from aiohttp import websocket
from aiohttp.web_ws import WebSocketResponse

from sockjs.transports import EventsourceTransport, WebSocketTransport

from test_base import BaseSockjsTestCase


class EventsourceTransportTests(BaseSockjsTestCase):

    TRANSPORT_CLASS = EventsourceTransport

    def test_streaming_send(self):
        trans = self.make_transport()

        resp = trans.response = mock.Mock()
        stop = trans.send('text data')
        resp.write.assert_called_with(b'data: text data\r\n\r\n')
        self.assertFalse(stop)
        self.assertEqual(
            trans.size, len(b'data: text data\r\n\r\n'))

        trans.maxsize = 1
        stop = trans.send('text data')
        self.assertTrue(stop)

    def test_process(self):
        transp = self.make_transport()
        transp.handle_session = self.make_fut(1)
        resp = self.loop.run_until_complete(transp.process())
        self.assertTrue(transp.handle_session.called)
        self.assertEqual(resp.status, 200)
