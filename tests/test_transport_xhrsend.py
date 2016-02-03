from sockjs.transports import xhrsend

from test_base import BaseSockjsTestCase


class XHRSendTransportTests(BaseSockjsTestCase):

    TRANSPORT_CLASS = xhrsend.XHRSendTransport

    def test_not_supported_meth(self):
        transp = self.make_transport(method='PUT')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 403)

    def test_no_payload(self):
        transp = self.make_transport()
        transp.request.read = self.make_fut(b'')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 500)

    def test_bad_json(self):
        transp = self.make_transport()
        transp.request.read = self.make_fut(b'{]')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 500)

    def test_post_message(self):
        transp = self.make_transport()
        transp.session._remote_messages = self.make_fut(1)
        transp.request.read = self.make_fut(b'["msg1","msg2"]')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 204)
        transp.session._remote_messages.assert_called_with(['msg1', 'msg2'])

    def test_OPTIONS(self):
        transp = self.make_transport(method='OPTIONS')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 204)
