import hashlib

# json
# -----------

# Fastest
try:
    import ujson as json
except ImportError:
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

def encode(message):
    """ Python to JSON """
    if isinstance(message, basestring):
        msg = message
    elif isinstance(message, (object, dict, list)):
        msg = json.dumps(message)
    else:
        raise ValueError("Unable to serialize: %s", str(message))
    return msg

def decode(data):
    """ JSON to Python """
    messages = []
    data.encode('utf-8', 'replace')

    # "a['123', 'abc']" -> [123, 'abc']
    try:
        messages = json.loads(data)
    except:
        raise ValueError("Unable to deserialize: %s", str(data))

    return messages

def close_frame(code, reason):
    return '%s[%d,"%s"]' % (CLOSE, code, reason)

def message_frame(data):
    return ''.join([MESSAGE, encode(data), '\n'])
