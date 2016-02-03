from unittest import mock

from sockjs.transports import jsonp

from test_base import BaseSockjsTestCase


class JSONPollingTransportTests(BaseSockjsTestCase):

    TRANSPORT_CLASS = jsonp.JSONPolling

    def test_streaming_send(self):
        trans = self.make_transport()
        trans.callback = 'cb'

        resp = trans.response = mock.Mock()
        stop = trans.send('text data')
        resp.write.assert_called_with(b'/**/cb("text data");\r\n')
        self.assertTrue(stop)

    def test_process(self):
        transp = self.make_transport(query_params={'c': 'calback'})
        transp.handle_session = self.make_fut(1)
        resp = self.loop.run_until_complete(transp.process())
        self.assertTrue(transp.handle_session.called)
        self.assertEqual(resp.status, 200)

    def test_process_no_callback(self):
        transp = self.make_transport()

        resp = self.loop.run_until_complete(transp.process())
        self.assertTrue(transp.session._remote_closed.called)
        self.assertEqual(resp.status, 500)

    def test_process_bad_callback(self):
        transp = self.make_transport(query_params={'c': 'calback!!!!'})

        resp = self.loop.run_until_complete(transp.process())
        self.assertTrue(transp.session._remote_closed.called)
        self.assertEqual(resp.status, 400)

    def test_process_not_supported(self):
        transp = self.make_transport(method='PUT')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 400)

    def test_process_bad_encoding(self):
        transp = self.make_transport(method='POST')
        transp.request.read = self.make_fut(b'test')
        transp.request.content_type
        transp.request._content_type = 'application/x-www-form-urlencoded'
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 500)

    def test_process_no_payload(self):
        transp = self.make_transport(method='POST')
        transp.request.read = self.make_fut(b'd=')
        transp.request.content_type
        transp.request._content_type = 'application/x-www-form-urlencoded'
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 500)

    def test_process_bad_json(self):
        transp = self.make_transport(method='POST')
        transp.request.read = self.make_fut(b'{]')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 500)

    def test_process_message(self):
        transp = self.make_transport(method='POST')
        transp.session._remote_messages = self.make_fut(1)
        transp.request.read = self.make_fut(b'["msg1","msg2"]')
        resp = self.loop.run_until_complete(transp.process())
        self.assertEqual(resp.status, 200)
        transp.session._remote_messages.assert_called_with(['msg1', 'msg2'])
