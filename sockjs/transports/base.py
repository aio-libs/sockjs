import asyncio

from sockjs.protocol import ENCODING, FRAME_OPEN
from sockjs.protocol import close_frame, messages_frame


class Transport:

    def __init__(self, manager, session, request):
        self.ws = None
        self.manager = manager
        self.session = session
        self.request = request
        self.loop = request.app.loop


class StreamingTransport(Transport):

    maxsize = 131072  # 128K bytes

    def __init__(self, manager, session, request):
        super().__init__(manager, session, request)

        self.size = 0
        self.waiter = asyncio.Future(loop=self.loop)
        self.response = None

    def send_open(self):
        return self.send_text(FRAME_OPEN)

    def send_message(self, message):
        return self.send_text(messages_frame([message]))

    def send_messages(self, messages):
        return self.send_text(messages_frame(messages))

    def send_message_frame(self, frame):
        return self.send_text(frame)

    @asyncio.coroutine
    def send_close(self, code, reason):
        yield from self.send_text(close_frame(code, reason))
        yield from self.session._remote_closed()

    @asyncio.coroutine
    def send_text(self, text):
        blob = (text + '\n').encode(ENCODING)
        yield from self.response.write(blob)

        self.size += len(blob)
        if self.size > self.maxsize:
            yield from self.manager.release(self.session)
            self.waiter.set_result(True)
