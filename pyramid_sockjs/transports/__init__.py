# pyramid_sockjs transports


class StreamingStop(Exception):
    """ Connection has been disconnected. """


from .jsonp import JSONPolling
from .websocket import WebSocketTransport
from .htmlfile import HTMLFileTransport
from .transports import XHRPollingTransport, \
    XHRSendPollingTransport, XHRStreamingTransport

handlers = {
    'websocket'    : (True, WebSocketTransport),

    'xhr'          : (True, XHRPollingTransport()),
    'xhr_send'     : (False, XHRSendPollingTransport()),
    'xhr_streaming': (True, XHRStreamingTransport),

    'jsonp'        : (True, JSONPolling),
    'jsonp_send'   : (False, JSONPolling),

    'htmlfile'     : (True, HTMLFileTransport),
}
