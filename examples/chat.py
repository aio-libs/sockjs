# -*- coding: utf-8 -*-
from pyramid_sockjs.session import Session


class ChatSession(Session):

    def on_open(self):
        self.manager.broadcast("Someone joined.")

    def on_message(self, message):
        self.manager.broadcast(message)

    def on_close(self):
        self.manager.broadcast("Someone left.")


if __name__ == '__main__':
    """ Simple sockjs chat """
    from pyramid.config import Configurator
    from pyramid_sockjs.paster import gevent_server_runner

    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route(session=ChatSession)

    config.add_route('root', '/')
    config.add_view(route_name='root', renderer='__main__:chat.pt')

    app = config.make_wsgi_app()
    #gevent_server_runner(app, {})
    from gunicorn.app.pasterapp import paste_server
    paste_server(app, host='0.0.0.0:8080',
                 working_class='gevent', workers=1, keepalive=10, debug=True)
