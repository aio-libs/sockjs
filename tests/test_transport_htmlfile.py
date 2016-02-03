from unittest import mock

from sockjs.transports import htmlfile

from test_base import BaseSockjsTestCase


class HtmlFileTransportTests(BaseSockjsTestCase):

    TRANSPORT_CLASS = htmlfile.HTMLFileTransport

    def test_streaming_send(self):
        trans = self.make_transport()

        resp = trans.response = mock.Mock()
        stop = trans.send('text data')
        resp.write.assert_called_with(
            b'<script>\np("text data");\n</script>\r\n')
        self.assertFalse(stop)
        self.assertEqual(
            trans.size,
            len(b'<script>\np("text data");\n</script>\r\n'))

        trans.maxsize = 1
        stop = trans.send('text data')
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
        self.assertEqual(resp.status, 500)
