# pyramid_sockjs

from pyramid_sockjs import session


def includeme(cfg):
    cfg.add_route(
        'sockjs',
        '/__sockjs__/{server}/{session}/{transport}')

    cfg.add_route(
        'sockjs-info',
        '/__sockjs__/info')

    cfg.add_route(
        'sockjs-iframe',
        '/__sockjs__/iframe{version}.html')

    cfg.scan('pyramid_sockjs.route')

    def get_sessions(request):
        return session.GetSessions(request.registry)

    cfg.set_request_property(get_sessions, 'get_sockjs_sessions', True)
