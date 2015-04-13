import json
from base import TestCase


class TestProtocol(TestCase):

    def test_encode(self):
        from sockjs import protocol

        self.assertEqual(
            protocol.encode({}), json.dumps({}).encode('utf-8'))
        self.assertEqual(
            protocol.encode(['test']), json.dumps(['test']).encode('utf-8'))
        self.assertEqual(
            protocol.encode('"test"'), json.dumps('"test"').encode('utf-8'))

    def test_decode(self):
        from sockjs import protocol

        self.assertEqual(protocol.decode(json.dumps({})), {})
        self.assertEqual(protocol.decode(json.dumps(['test'])), ['test'])
        self.assertEqual(protocol.decode(json.dumps('"test"')), '"test"')

    def test_close_frame(self):
        from pyramid_sockjs import protocol

        msg = protocol.close_frame(1000, 'Internal error')
        self.assertEqual(msg, b'c[1000,"Internal error"]')

    def test_message_frame(self):
        from sockjs import protocol

        msg = protocol.message_frame(['msg1', 'msg2'])
        self.assertEqual(
            msg.decode('utf-8'),
            'a[%s]' % protocol.encode(['msg1', 'msg2']).decode('utf-8'))
