import tulip
import tulip.http
try:
    import signal
except ImportError:
    signal = None


# For paste.deploy server instantiation (egg:pyramid_sockjs#server)
def tulip_server_runner(wsgi_app, global_conf, **kw):
    host = kw.get('host', '0.0.0.0')
    port = int(kw.get('port', 8080))
    try:
        keep_alive = float(kw.get('keep-alive', None))
    except:
        keep_alive = None

    loop = tulip.get_event_loop()
    loop.start_serving(
        lambda: tulip.http.WSGIServerHttpProtocol(
            wsgi_app, readpayload=True, keep_alive=keep_alive), host, port)
    print('Starting Tulip server on http://%s:%s' % (host, port))

    if signal:
        loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
