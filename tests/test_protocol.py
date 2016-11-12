import json

from sockjs import protocol


def test_encode():
    assert protocol.dumps({}) == json.dumps({})
    assert protocol.dumps(['test']) == json.dumps(['test'])
    assert protocol.dumps('"test"') == json.dumps('"test"')


def test_decode():
    assert protocol.loads(json.dumps({})) == {}
    assert protocol.loads(json.dumps(['test'])) == ['test']
    assert protocol.loads(json.dumps('"test"')) == '"test"'


def test_close_frame():
    msg = protocol.close_frame(1000, 'Internal error')
    assert msg == 'c[1000,"Internal error"]'


def test_message_frame():
    msg = protocol.message_frame('msg1')
    assert msg == 'a%s' % protocol.dumps(['msg1'])


def test_messages_frame():
    msg = protocol.messages_frame(['msg1', 'msg2'])
    assert msg == 'a%s' % protocol.dumps(['msg1', 'msg2'])
