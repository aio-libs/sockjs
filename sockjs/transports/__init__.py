# sockjs transports
from .eventsource import EventsourceTransport
from .htmlfile import HTMLFileTransport
from .jsonp import JSONPolling, JSONPollingSend
from .websocket import WebSocketTransport
from .xhr import XHRTransport
from .xhrsend import XHRSendTransport
from .xhrstreaming import XHRStreamingTransport


transport_handlers = {
    "websocket": WebSocketTransport,
    "xhr": XHRTransport,
    "xhr_send": XHRSendTransport,
    "xhr_streaming": XHRStreamingTransport,
    "jsonp": JSONPolling,
    "jsonp_send": JSONPollingSend,
    "htmlfile": HTMLFileTransport,
    "eventsource": EventsourceTransport,
}
