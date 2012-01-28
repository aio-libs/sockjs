# pyramid_sockjs transports


class StopStreaming(StopIteration):
    """ Connection has been disconnected. """


from .jsonp import JSONPolling
from .websocket import WebSocketTransport
from .htmlfile import HTMLFileTransport
from .eventsource import EventsourceTransport
from .xhrpolling import XHRPollingTransport
from .xhrpolling import XHRSendPollingTransport
from .xhrstreaming import XHRStreamingTransport

from .utils import session_cookie


handlers = {
    'websocket'    : (True, WebSocketTransport),

    'xhr'          : (True, XHRPollingTransport()),
    'xhr_send'     : (False, XHRSendPollingTransport()),
    'xhr_streaming': (True, XHRStreamingTransport),

    'jsonp'        : (True, JSONPolling),
    'jsonp_send'   : (False, JSONPolling),

    'htmlfile'     : (True, HTMLFileTransport),
    'eventsource'  : (True, EventsourceTransport),
}
