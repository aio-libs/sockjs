import time
import hashlib
from email import utils
from datetime import datetime
from pyramid.compat import string_types

# json
# -----------

# Fastest
try:
    import ujson as json
    kwargs = {} # pragma: no cover
except ImportError: # pragma: no cover
    def dthandler(obj):
        if isinstance(obj, datetime):
            return utils.formatdate(time.mktime(obj.utctimetuple()))

    kwargs = {'default': dthandler, 'separators': (',', ':')}

    # Faster
    try:
        import simplejson as json
    except ImportError:
        # Slowest
        import json


# Frames
# ------

OPEN      = "o\n"
CLOSE     = "c"
MESSAGE   = "a"
HEARTBEAT = "h\n"


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

IFRAME_MD5 = hashlib.md5(IFRAME_HTML).hexdigest()

decode = json.loads

def encode(data):
    return json.dumps(data, **kwargs)

def close_frame(code, reason, eol=''):
    return '%s[%d,%s]%s' % (CLOSE, code, encode(reason), eol)

def message_frame(data, eol=''):
    return '%s%s%s'%(MESSAGE, encode(data), eol)
