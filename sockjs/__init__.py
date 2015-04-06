# pyramid_sockjs
__all__ = (
    'Session', 'SessionManager', 'get_manager', 'add_endpoint',
    'STATE_NEW', 'STATE_OPEN', 'STATE_CLOSING', 'STATE_CLOSED',
    'MSG_OPEN', 'MSG_MESSAGE', 'MSG_CLOSE', 'MSG_CLOSED',
    )

#from sockjs.session import Session
#from sockjs.session import SessionManager

from sockjs.protocol import STATE_NEW
from sockjs.protocol import STATE_OPEN
from sockjs.protocol import STATE_CLOSING
from sockjs.protocol import STATE_CLOSED

from sockjs.protocol import STATE_NEW
from sockjs.protocol import STATE_OPEN
from sockjs.protocol import STATE_CLOSING
from sockjs.protocol import STATE_CLOSED
from sockjs.protocol import MSG_OPEN
from sockjs.protocol import MSG_MESSAGE
from sockjs.protocol import MSG_CLOSE
from sockjs.protocol import MSG_CLOSED



from sockjs.route import get_manager, add_endpoint


def includeme(cfg):
    from pyramid.settings import asbool
    from sockjs.route import add_sockjs_route
    from sockjs.route import GetSessionManager

    def get_manager(request, name=''):
        return GetSessionManager(request.registry)

    cfg.add_directive('add_sockjs_route', add_sockjs_route)
    cfg.set_request_property(get_manager, 'get_sockjs_manager', True)

    settings = cfg.get_settings()
    settings['debug_sockjs'] = asbool(settings.get('debug_sockjs', 'f'))
