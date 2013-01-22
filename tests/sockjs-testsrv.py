from pyramid_sockjs.session import Session
from pyramid_sockjs.session import SessionManager
from pyramid_sockjs.server import tulip_server_runner


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
    """ Sockjs tests server """
    from pyramid.config import Configurator
    from pyramid_sockjs.transports.eventsource import EventsourceTransport
    from pyramid_sockjs.transports.htmlfile import HTMLFileTransport
    from pyramid_sockjs.transports.xhrstreaming import XHRStreamingTransport

    HTMLFileTransport.maxsize = 4096
    EventsourceTransport.maxsize = 4096
    XHRStreamingTransport.maxsize = 4096

    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route('echo', '/echo', EchoSession)
    config.add_sockjs_route('close', '/close', CloseSession)
    config.add_sockjs_route('broadcast', '/broadcast', BroadcastSession)
    config.add_sockjs_route(
        'wsoff', '/disabled_websocket_echo', EchoSession,
        disable_transports=('websocket',))
    config.add_sockjs_route(
        'cookie', '/cookie_needed_echo', EchoSession, cookie_needed=True)

    app = config.make_wsgi_app()

    tulip_server_runner(app, {}, **{'host': '127.0.0.1', 'port': '8081'})
