import base64
from hashlib import md5, sha1

import gevent
from gevent.pywsgi import Input
from geventwebsocket.websocket import WebSocketHybi

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

from pyramid_sockjs import transports

handler_types = {
    'websocket'    : ('bi', transports.WebSocketTransport),

    'xhr'          : ('recv', transports.XHRPollingTransport()),
    'xhr_send'     : ('send', transports.XHRSendPollingTransport()),
    'xhr_streaming': ('recv', transports.XHRStreamingTransport),

    'jsonp'        : ('recv', transports.JSONPolling()),
    'jsonp_send'   : ('send', transports.JSONPolling()),

    'htmlfile'     : ('recv', transports.HTMLFileTransport()),
    'iframe'       : ('recv', transports.IFrameTransport()),
}


@view_config(route_name='sockjs')
def sockjs(request):
    matchdict = request.matchdict
    tid = matchdict['transport']

    # Lookup the direction of the transport and its
    # associated handler
    if tid not in handler_types:
        return HTTPNotFound()

    direction, transport = handler_types[tid]

    # session
    sessions = request.get_sockjs_sessions()

    session = sessions.get(matchdict['session'], direction in ('bi','recv'))
    if session is None:
        return HTTPNotFound()

    request.environ['sockjs'] = session

    # initiate websocket connetion
    if tid == 'websocket':
        result = init_websocket_connection(request)
        if result is not None:
            return result

    return transport(session, request)


@view_config(route_name='sockjs-info')
def sockjs_info(request):
    request.response.body = str(map(str, []))
    return request.response


@view_config(route_name='sockjs-iframe')
def sockjs_iframe(request):
    pass


def init_websocket_connection(request):
    environ = request.environ

    upgrade = environ.get('HTTP_UPGRADE', '').lower()
    if upgrade == 'websocket':
        connection = environ.get('HTTP_CONNECTION', '').lower()

        if 'upgrade' in connection:
            version = environ.get("HTTP_SEC_WEBSOCKET_VERSION")
            if version:
                environ['wsgi.websocket_version'] = 'hybi-%s' % version
                if version not in SUPPORTED_VERSIONS:
                    return HTTPBadRequest(
                        headers=(('Sec-WebSocket-Version', '13, 8, 7'),))

                result = handle_hybi(request, environ)

                if result is not None:
                    return result
                return None

    return HTTPBadRequest()


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUPPORTED_VERSIONS = ('13', '8', '7')

def handle_hybi(request, environ):
    protocol = environ.get('SERVER_PROTOCOL','')

    # check client handshake for validity
    if not request.method == "GET":
        # 5.2.1 (1)
        return HTTPBadRequest()
    elif not protocol.startswith("HTTP/"):
        # 5.2.1 (1)
        return HTTPBadRequest()
    elif not (environ.get('GATEWAY_INTERFACE','').endswith('/1.1') or \
              protocol.endswith('/1.1')):
        # 5.2.1 (1)
        return HTTPBadRequest()
    
    key = environ.get("HTTP_SEC_WEBSOCKET_KEY")
    if not key:
        # 5.2.1 (3)
        return HTTPBadRequest('HTTP_SEC_WEBSOCKET_KEY is missing from request')
    elif len(base64.b64decode(key)) != 16:
        # 5.2.1 (3)
        return HTTPBadRequest('Invalid key: %r', key)

    # !!!!!!! HACK !!!!!!!
    wsgi_input = environ['wsgi.input']
    if not isinstance(wsgi_input, Input):
        return HTTPBadRequest("Can't get handler.rfile from %s", wsgi_input)
    else:
        rfile = wsgi_input.rfile
    # !!!!!!! HACK !!!!!!!

    environ['wsgi.websocket'] = WebSocketHybi(rfile, environ)

    headers = [
        ("Upgrade", "websocket"),
        ("Connection", "Upgrade"),
        ("Content-Length", "0"),
        ("Sec-WebSocket-Accept", base64.b64encode(sha1(key + GUID).digest()))]
    request.response.headers = headers
    request.response.status = '101 Switching Protocols'
