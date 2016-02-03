from sockjs.transports import xhrstreaming

from test_base import BaseSockjsTestCase


class XHRStreamingTransportTests(BaseSockjsTestCase):

    TRANSPORT_CLASS = xhrstreaming.XHRStreamingTransport

    def test_process(self):
        transp = self.make_transport()
        transp.handle_session = self.make_fut(1)
        resp = self.loop.run_until_complete(transp.process())
        self.assertTrue(transp.handle_session.called)
        self.assertEqual(resp.status, 200)

    def test_process_OPTIONS(self):
        transp = self.make_transport(method='OPTIONS')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 204)
