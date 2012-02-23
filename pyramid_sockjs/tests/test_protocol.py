import json
from base import TestCase


class TestProtocol(TestCase):

    def test_encode(self):
        from pyramid_sockjs import protocol

        self.assertEqual(protocol.encode({}), json.dumps({}))
        self.assertEqual(protocol.encode(['test']), json.dumps(['test']))
        self.assertEqual(protocol.encode('"test"'), json.dumps('"test"'))

    def test_decode(self):
        from pyramid_sockjs import protocol

        self.assertEqual(protocol.decode(json.dumps({})), {})
        self.assertEqual(protocol.decode(json.dumps(['test'])), ['test'])
        self.assertEqual(protocol.decode(json.dumps('"test"')), '"test"')

    def test_close_frame(self):
        from pyramid_sockjs import protocol

        msg = protocol.close_frame(1000, 'Internal error')
        self.assertEqual(msg, 'c[1000,"Internal error"]')

    def test_close_frame_endline(self):
        from pyramid_sockjs import protocol

        msg = protocol.close_frame(1000, 'Internal error', '\n')
        self.assertEqual(msg, 'c[1000,"Internal error"]\n')

    def test_message_frame(self):
        from pyramid_sockjs import protocol

        msg = protocol.message_frame(['msg1', 'msg2'])
        self.assertEqual(msg, 'a%s'%protocol.encode(['msg1', 'msg2']))

    def test_message_frame_endline(self):
        from pyramid_sockjs import protocol

        msg = protocol.message_frame(['msg1', 'msg2'], '\n')
        self.assertEqual(msg, 'a%s\n'%protocol.encode(['msg1', 'msg2']))
