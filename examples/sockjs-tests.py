# -*- coding: utf-8 -*-
import math
import gevent
from pyramid_sockjs.session import Session


class EchoSession(Session):

    def on_message(self, message):
        self.send(message)


class CloseSession(Session):
    def on_open(self):
        self.close()

    def on_message(self, msg):
        pass


class TickerSession(Session):
    def on_open(self, info):
        self.timeout = ioloop.PeriodicCallback(self._ticker, 1000)
        self.timeout.start()

    def on_close(self):
        self.timeout.stop()

    def _ticker(self):
        self.send('tick!')


class BroadcastSession(Session):

    def on_message(self, msg):
        self.manager.broadcast(msg)


class AmplifySession(Session):

    def on_message(self, msg):
        n = int(msg)
        if n < 0 or n > 19:
            n = 1

        self.send('x' * int(math.pow(2, n)))


if __name__ == '__main__':
    """ Simple sockjs tests server """
    from pyramid.config import Configurator
    from pyramid_sockjs.paster import gevent_server_runner

    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route('echo', '/echo', session=EchoSession)
    config.add_sockjs_route('close', '/close', session=CloseSession)
    config.add_sockjs_route('ticker', '/ticker', session=TickerSession)
    config.add_sockjs_route('amplify', '/Amplify', session=AmplifySession)
    config.add_sockjs_route('broadcast', '/broadcast', session=BroadcastSession)
    
    app = config.make_wsgi_app()
    gevent_server_runner(app, {}, **{'host': '127.0.0.1', 'port': '8081'})
