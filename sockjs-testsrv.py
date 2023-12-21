import logging

from aiohttp import web

import sockjs
from sockjs.transports.eventsource import EventsourceTransport
from sockjs.transports.htmlfile import HTMLFileTransport
from sockjs.transports.xhrstreaming import XHRStreamingTransport


async def echo_session(manager, session, msg):
    if msg.type == sockjs.MsgType.MESSAGE:
        session.send(msg.data)


async def close_session_handler(manager, session, msg):
    if msg.type == sockjs.MsgType.OPEN:
        session.close()


async def broadcast_session(manager, session, msg):
    if msg.type == sockjs.MsgType.OPEN:
        manager.broadcast(msg.data)


if __name__ == '__main__':
    """ Sockjs tests server """
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(message)s')

    HTMLFileTransport.maxsize = 4096
    EventsourceTransport.maxsize = 4096
    XHRStreamingTransport.maxsize = 4096

    app = web.Application()

    sockjs.add_endpoint(
        app, echo_session, name='echo', prefix='/echo'
    )
    sockjs.add_endpoint(
        app, close_session_handler, name='close', prefix='/close'
    )
    sockjs.add_endpoint(
        app, broadcast_session, name='broadcast', prefix='/broadcast'
    )
    sockjs.add_endpoint(
        app, echo_session, name='wsoff', prefix='/disabled_websocket_echo',
        disable_transports=('websocket',))

    sockjs.add_endpoint(
        app, echo_session, name='cookie', prefix='/cookie_needed_echo',
        cookie_needed=True
    )

    web.run_app(app, port=8081)
