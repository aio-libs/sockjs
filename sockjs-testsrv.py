import asyncio
import logging
from aiohttp import web

import sockjs
from sockjs.transports.eventsource import EventsourceTransport
from sockjs.transports.htmlfile import HTMLFileTransport
from sockjs.transports.xhrstreaming import XHRStreamingTransport


async def echoSession(msg, session):
    if msg.type == sockjs.MSG_MESSAGE:
        session.send(msg.data)


async def closeSessionHander(msg, session):
    if msg.type == sockjs.MSG_OPEN:
        session.close()


async def broadcastSession(msg, session):
    if msg.type == sockjs.MSG_OPEN:
        session.manager.broadcast(msg.data)


if __name__ == '__main__':
    """ Sockjs tests server """
    loop = asyncio.get_event_loop()
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(message)s')

    HTMLFileTransport.maxsize = 4096
    EventsourceTransport.maxsize = 4096
    XHRStreamingTransport.maxsize = 4096

    app = web.Application(loop=loop)

    sockjs.add_endpoint(
        app, echoSession, name='echo', prefix='/echo')
    sockjs.add_endpoint(
        app, closeSessionHander, name='close', prefix='/close')
    sockjs.add_endpoint(
        app, broadcastSession, name='broadcast', prefix='/broadcast')
    sockjs.add_endpoint(
        app, echoSession, name='wsoff', prefix='/disabled_websocket_echo',
        disable_transports=('websocket',))
    sockjs.add_endpoint(
        app, echoSession, name='cookie', prefix='/cookie_needed_echo',
        cookie_needed=True)

    web.run_app(app)
