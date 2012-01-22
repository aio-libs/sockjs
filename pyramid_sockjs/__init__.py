# pyramid_sockjs

def includeme(cfg):
    from pyramid_sockjs.route import add_sockjs_route
    from pyramid_sockjs.session import GetSessionManager

    def get_manager(request, name=''):
        return GetSessionManager(request.registry)

    cfg.add_directive('add_sockjs_route', add_sockjs_route)
    cfg.set_request_property(get_manager, 'get_sockjs_manager', True)
