""" websocket transport """
import gevent
from gevent.queue import Empty
from socket import SHUT_RDWR
from pyramid.response import Response
from pyramid_sockjs.protocol import OPEN, HEARTBEAT
from pyramid_sockjs.protocol import decode, close_frame, message_frame


TIMING = 5.0

def WebSocketTransport(session, request):
    socket = request.environ['gunicorn.socket']
    websocket = request.environ['wsgi.websocket']

    def send():
        websocket.send('o')
        session.open()

        while True:
            try:
                message = session.get_transport_message(TIMING)
            except Empty:
                message = 'h'
                session.heartbeat()
            else:
                message = message_frame(message)

            if message is None or not session.connected:
                try:
                    websocket.send(close_frame(3000, 'Go away!'))
                    websocket.close()
                    socket.shutdown(SHUT_RDWR)
                except:
                    pass
                session.close()
                break

            if not session.connected:
                break

            try:
                websocket.send(message)
            except:
                session.close()
                break

    def receive():
        while True:
            try:
                message = websocket.receive()
            except:
                session.close()
                break
            if message is None:
                session.close()
                break
            
            if not message:
                continue

            try:
                decoded_message = decode(message)
            except:
                session.close()
                websocket.close()
                socket.shutdown(SHUT_RDWR)
                break
                
            if decoded_message:
                session.message(decoded_message)

        session.manager.release(session)

    jobs = [gevent.spawn(send), gevent.spawn(receive)]

    return WebSocketResponse(request.response, jobs)


class WebSocketResponse(Response):

    def __init__(self, response, jobs):
        self.__dict__.update(response.__dict__)
        self.jobs = jobs

    def __call__(self, environ, start_response):
        write = start_response(
            self.status, self._abs_headerlist(environ))
        write('')

        gevent.joinall(self.jobs)
        return []
