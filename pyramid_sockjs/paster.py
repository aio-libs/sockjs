import gevent
import gevent.monkey
from gevent.pywsgi import WSGIServer


# For paste.deploy server instantiation (egg:pyramid_sockjs#server)
def gevent_server_runner(wsgi_app, global_conf, **kw):
    gevent.monkey.patch_all()

    def runner():
        host = kw.get('host', '0.0.0.0')
        port = int(kw.get('port', 8080))
        server = WSGIServer((host, port), wsgi_app)
        print('Starting Gevent server on http://%s:%s' % (host, port))
        server.serve_forever()

    jobs = [gevent.spawn(runner)]
    gevent.joinall(jobs)
