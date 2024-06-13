import dataclasses
import enum
import hashlib
from datetime import datetime
from typing import Union


ENCODING = "utf-8"


@enum.unique
class SessionState(enum.Enum):
    NEW = 0
    OPEN = 1
    CLOSING = 2
    CLOSED = 3


_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

# json
# -----------

# Fastest
try:
    import ujson as json

    kwargs = {}  # pragma: no cover
except ImportError:  # pragma: no cover

    def dthandler(obj):
        if isinstance(obj, datetime):
            now = obj.timetuple()
            return "%s, %02d %s %04d %02d:%02d:%02d -0000" % (
                _days[now[6]],
                now[2],
                _months[now[1] - 1],
                now[0],
                now[3],
                now[4],
                now[5],
            )

    kwargs = {"default": dthandler, "separators": (",", ":")}

    # Faster
    try:
        import simplejson as json
    except ImportError:
        # Slowest
        import json


# Frames
# ------


@enum.unique
class Frame(enum.Enum):
    OPEN = "o"
    CLOSE = "c"
    MESSAGE = "a"
    MESSAGE_BLOB = "a1"
    HEARTBEAT = "h"


# ------------------

IFRAME_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <script src="%s"></script>
  <script>
    document.domain = document.domain;
    SockJS.bootstrap_iframe();
  </script>
</head>
<body>
  <h2>Don't panic!</h2>
  <p>This is a SockJS hidden iframe. It's used for cross domain magic.</p>
</body>
</html>
""".strip()

IFRAME_MD5 = hashlib.md5(IFRAME_HTML.encode()).hexdigest()

loads = json.loads
ENCODING = "utf-8"


def dumps(data):
    return json.dumps(data, **kwargs)


def close_frame(code, reason):
    return Frame.CLOSE.value + json.dumps([code, reason], **kwargs)


def message_frame(message):
    return Frame.MESSAGE.value + json.dumps([message], **kwargs)


def messages_frame(messages):
    return Frame.MESSAGE.value + json.dumps(messages, **kwargs)


# Handler messages
# ---------------------


@enum.unique
class MsgType(enum.Enum):
    OPEN = 1
    MESSAGE = 2
    CLOSE = 3
    CLOSED = 4


@dataclasses.dataclass(frozen=True)
class SockjsMessage:
    type: MsgType
    data: Union[str, Exception, None]

    @property
    def tp(self) -> MsgType:
        return self.type


OPEN_MESSAGE = SockjsMessage(MsgType.OPEN, None)
CLOSE_MESSAGE = SockjsMessage(MsgType.CLOSE, None)
CLOSED_MESSAGE = SockjsMessage(MsgType.CLOSED, None)
