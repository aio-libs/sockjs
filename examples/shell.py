""" interactive shell """
import sys
import code
import gevent
from gevent.queue import Queue
from pprint import pprint
from StringIO import StringIO
from pyramid_sockjs import Session, json


class InteractiveShell(Session):

    def __init__(self, id, *args, **kw):
        super(InteractiveShell, self).__init__(id, *args, **kw)

        self.shell = None
        self.cmd_id = 0
        self.shell_worker = None
        self.commands = Queue()

    def start(self):
        if self.shell_worker is None:
            def worker():
                while 1:
                    command = self.commands.get(True)
                    if command is None:
                        break

                    self.cmd_id = command['id']
                    out = StringIO()
                    orig = sys.stdout
                    sys.stdout = out
                    more = self.shell.runsource(command['source'])
                    sys.stdout = orig

                    self.send({'id': self.cmd_id,
                               'complete': True,
                               'more': more,
                               'out': out.getvalue()})

            self.shell_worker = gevent.Greenlet(worker)

        if not self.shell_worker:
            self.shell_worker.start()

    def write(self, data):
        print data,

    def on_open(self):
        self.shell = code.InteractiveInterpreter(
            {'session': self,
             'registry': self.registry,
             'manager': self.manager})

        self.shell.write = self.write
        self.start()

        self.send({'id': 0,
                   'complete': False,
                   'more': False,
                   'out': "Python %s on %s\n" % (sys.version, sys.platform)})

    def on_message(self, msg):
        self.commands.put_nowait(json.loads(msg))

    def on_closed(self):
        if self.shell_worker:
            self.shell_worker.kill()


if __name__ == '__main__':
    """ interactive shell """
    from pyramid.config import Configurator
    from pyramid_sockjs.paster import gevent_server_runner

    config = Configurator()
    config.include('pyramid_sockjs')

    config.add_sockjs_route('shell', '/++shell++', session=InteractiveShell)

    app = config.make_wsgi_app()
    gevent_server_runner(app, {}, host='127.0.0.1')
