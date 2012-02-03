""" interactive shell cli """
import sys
import code
import json
import Queue
import signal

class ConnectionClosedException(Exception):
    pass


class WebSocket8Client(object):

    def __init__(self, url):
        queue = Queue.Queue()
        self.queue = queue

        from ws4py.client.threadedclient import WebSocketClient
        class IntWebSocketClient(WebSocketClient):
            def received_message(self, m):
                queue.put_nowait(json.loads(str(m)))
            def read_from_connection(self, amount):
                try:
                    r = super(
                        IntWebSocketClient, self).read_from_connection(amount)
                except:
                    queue.put(Ellipsis)
                    return 0
                if not r:
                    queue.put(Ellipsis)
                return r
        self.client = IntWebSocketClient(url)
        self.client.connect()

    def close(self):
        if self.client:
            self.client.running = False
            self.client.close_connection()
            self.client._th.join()
            self.client = None

    def send(self, data):
        self.client.send(data)

    def recv(self):
        try:
            r = self.queue.get(timeout=1.0)
            if r is Ellipsis:
                raise ConnectionClosedException()
            return r
        except Queue.Empty:
            return
        except:
            self.close()
            raise


class InteractiveConsole(code.InteractiveConsole):

    def __init__(self, host):
        code.InteractiveConsole.__init__(self)

        self.host = host
        self.count = 0
        print 'Connecting...'
        self.ws = WebSocket8Client(host)

        r = self.ws.recv()
        if r is not None:
            print r['out'],

    def runsource(self, source, filename='<input>'):
        try:
            if source:
                return self.runsource_ws(source, filename)
        except ConnectionClosedException:
            print "Interactive shell has been disconnected. reconnecting..."
            self.ws = WebSocket8Client(self.host)
            self.ws.recv() # read welcome msg
            return self.runsource_ws(source, filename)

    def runsource_ws(self, source, filename='<input>'):
        self.count += 1

        cmd = json.dumps({'id': self.count, 'source': source})

        self.ws.send(cmd)

        while 1:
            r = self.ws.recv()
            if r is not None:
                if not r['more'] and r['out']:
                    print r['out'],
                if r['complete']:
                    return r['more']
            else:
                pass


def shell():
    console = None
    _handler_int = signal.getsignal(signal.SIGINT)
    _handler_term = signal.getsignal(signal.SIGTERM)

    def process_shutdown(sig, frame):
        if console is not None:
            try:
                console.ws.close()
            except:
                pass

        if sig == signal.SIGINT and callable(_handler_int):
            _handler_int(sig, frame)

        if sig == signal.SIGTERM and callable(_handler_term):
            _handler_term(sig, frame)

        if sig == signal.SIGTERM:
            raise sys.exit()

    signal.signal(signal.SIGINT, process_shutdown)
    signal.signal(signal.SIGTERM, process_shutdown)

    try:
        import readline
    except ImportError:
        pass

    host = sys.argv[1]
    if not host.endswith('/websocket'):
        if host.endswith('/'):
            host = '%swebsocket'%host
        else:
            host = '%s/websocket'%host

    console = InteractiveConsole(host)
    console.interact('')
    console.ws.close()


if __name__ == '__main__':
    shell()
