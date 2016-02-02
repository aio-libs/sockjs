import json
import unittest

from sockjs import protocol


class TestProtocol(unittest.TestCase):

    def test_encode(self):
        self.assertEqual(protocol.dumps({}), json.dumps({}))
        self.assertEqual(
            protocol.dumps(['test']), json.dumps(['test']))
        self.assertEqual(
            protocol.dumps('"test"'), json.dumps('"test"'))

    def test_decode(self):
        self.assertEqual(protocol.loads(json.dumps({})), {})
        self.assertEqual(protocol.loads(json.dumps(['test'])), ['test'])
        self.assertEqual(protocol.loads(json.dumps('"test"')), '"test"')

    def test_close_frame(self):
        msg = protocol.close_frame(1000, 'Internal error')
        self.assertEqual(msg, 'c[1000,"Internal error"]')

    def test_message_frame(self):
        msg = protocol.message_frame('msg1')
        self.assertEqual(
            msg, 'a%s' % protocol.dumps(['msg1']))

    def test_messages_frame(self):
        msg = protocol.messages_frame(['msg1', 'msg2'])
        self.assertEqual(
            msg, 'a%s' % protocol.dumps(['msg1', 'msg2']))
