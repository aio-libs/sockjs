# pyramid_sockjs

from pyramid_sockjs.session import Session
from pyramid_sockjs.session import SessionManager

from pyramid_sockjs.session import STATE_NEW
from pyramid_sockjs.session import STATE_OPEN
from pyramid_sockjs.session import STATE_CLOSING
from pyramid_sockjs.session import STATE_CLOSED

from pyramid_sockjs.protocol import json
from pyramid_sockjs.route import get_session_manager


def includeme(cfg):
    from pyramid.settings import asbool
    from pyramid_sockjs.route import add_sockjs_route
    from pyramid_sockjs.route import GetSessionManager

    def get_manager(request, name=''):
        return GetSessionManager(request.registry)

    cfg.add_directive('add_sockjs_route', add_sockjs_route)
    cfg.set_request_property(get_manager, 'get_sockjs_manager', True)

    settings = cfg.get_settings()
    settings['debug_sockjs'] = asbool(settings.get('debug_sockjs', 'f'))
