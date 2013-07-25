from pyramid.config import Configurator
from pyramid_sockjs.paster import tulip_server_runner
from pyramid_sockjs.session import Session


class ChatSession(Session):

    def on_open(self):
        self.manager.broadcast("Someone joined.")

    def on_message(self, message):
        self.manager.broadcast(message)

    def on_closed(self):
        self.manager.broadcast("Someone left.")


if __name__ == '__main__':
    """Simple sockjs chat."""
    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route(prefix='/__sockjs__', session=ChatSession)

    config.add_route('root', '/')
    config.add_view(route_name='root', renderer='__main__:chat.pt')

    app = config.make_wsgi_app()

    tulip_server_runner(app, {}, **{'host': '127.0.0.1', 'port': '8080'})
