from zope.interface import implementer
from pyramid.interfaces import IResponse


@implementer(IResponse)

class Transport:

    wait = None

    def __init__(self, session, request):
        self.session = session
        self.request = request

        request.environ['tulip.add_close_callback'](self.close)

    def close(self):
        self.session.interrupt()
        if self.wait is not None and not self.wait.done():
            self.wait.cancel()
