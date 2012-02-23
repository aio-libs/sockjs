import sys
import gevent
from pyramid_sockjs.session import Session


class EchoSession(Session):

    def on_message(self, message):
        self.send(message)


class CloseSession(Session):

    def on_open(self):
        self.close()


class BroadcastSession(Session):

    def on_message(self, msg):
        self.manager.broadcast(msg)


if __name__ == '__main__':
    """ Simple sockjs tests server """
    from pyramid.config import Configurator
    from pyramid_sockjs.paster import gevent_server_runner
    from pyramid_sockjs.transports import websocket, jsonp
    from pyramid_sockjs.transports.xhrpolling import PollingTransport
    from pyramid_sockjs.transports.eventsource import EventsourceTransport
    from pyramid_sockjs.transports.xhrstreaming import XHRStreamingTransport
    from pyramid_sockjs.transports.htmlfile import HTMLFileTransport

    HTMLFileTransport.maxsize = 4096
    EventsourceTransport.maxsize = 4096
    XHRStreamingTransport.maxsize = 4096
    XHRStreamingTransport.timing = 0.01
    websocket.TIMING = 0.1
    jsonp.timing = 0.1
    PollingTransport.timing = 0.2

    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route('echo', '/echo', session=EchoSession)
    config.add_sockjs_route('wsoff', '/disabled_websocket_echo', session=EchoSession,
                            disable_transports=('websocket',))

    config.add_sockjs_route('close', '/close', session=CloseSession)
    config.add_sockjs_route('broadcast', '/broadcast', session=BroadcastSession)

    app = config.make_wsgi_app()

    if len(sys.argv) > 1 and (sys.argv[1] == '-g'):
        from gunicorn.app.pasterapp import paste_server
        paste_server(app, port=8081, worker_class='gevent', workers=1)
    else:
        gevent_server_runner(app, {}, **{'host': '127.0.0.1', 'port': '8081'})
