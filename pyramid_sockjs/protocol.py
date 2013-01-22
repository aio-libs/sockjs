import time
import hashlib
from email import utils
from datetime import datetime
from pyramid.compat import string_types

_days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# json
# -----------

# Fastest
try:
    import ujson as json
    kwargs = {} # pragma: no cover
except ImportError: # pragma: no cover
    def dthandler(obj):
        if isinstance(obj, datetime):
            now = obj.timetuple()
            return '%s, %02d %s %04d %02d:%02d:%02d -0000' % (
                _days[now[6]], now[2],
                _months[now[1] - 1], now[0], now[3], now[4], now[5])

    kwargs = {'default': dthandler, 'separators': (',', ':')}

    # Faster
    try:
        import simplejson as json
    except ImportError:
        # Slowest
        import json


# Frames
# ------

OPEN      = b"o"
CLOSE     = b"c"
MESSAGE   = b"a"
HEARTBEAT = b"h"


# ------------------

IFRAME_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <script>
    document.domain = document.domain;
    _sockjs_onload = function(){SockJS.bootstrap_iframe();};
  </script>
  <script src="%s"></script>
</head>
<body>
  <h2>Don't panic!</h2>
  <p>This is a SockJS hidden iframe. It's used for cross domain magic.</p>
</body>
</html>
""".strip()

IFRAME_MD5 = hashlib.md5(IFRAME_HTML.encode()).hexdigest()

decode = json.loads

def encode(data):
    return json.dumps(data, **kwargs).encode()

def close_frame(code, reason):
    return CLOSE + b'[' + str(code).encode() + b',' + encode(reason) + b']'

def message_frame(message):
    return MESSAGE + encode([message])

def heartbeat_frame():
    return 'h'

FRAMES = {
    CLOSE: close_frame,
    MESSAGE: message_frame,
    HEARTBEAT: heartbeat_frame,
}
