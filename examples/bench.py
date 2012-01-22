from pyramid_sockjs import Session


class EchoSession(Session):

    def on_message(self, msg):
        self.send(msg)

    @classmethod
    def dump_stats(self):
        print 'Clients: %d' % (len(self.clients))


if __name__ == '__main__':
    from pyramid.config import Configurator
    from pyramid_sockjs.paster import gevent_server_runner

    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route(prefix='/echo', session=EchoSession)

    app = config.make_wsgi_app()
    gevent_server_runner(app, {})
