from unittest import TestCase
from pyramid import testing
from pyramid.interfaces import IRequest


class SocketMock(object):

    def makefile(self):
        """ """

    def sendall(self, msg):
        """ """


class BaseTestCase(TestCase):

    _include = True
    _auto_include = True
    _settings = {}
    _environ = {
        'wsgi.url_scheme': 'http',
        'wsgi.version': (1, 0),
        'HTTP_HOST': 'example.com',
        'SCRIPT_NAME': '',
        'PATH_INFO': '/',
        'gunicorn.socket': SocketMock()}

    def setUp(self):
        self.init_pyramid()

    def make_request(self, environ=None, request_iface=IRequest, **kwargs):
        if environ is None:
            environ = self._environ
        request = testing.DummyRequest(environ=dict(environ), **kwargs)
        request.request_iface = IRequest
        return request

    def init_pyramid(self):
        self.request = request = self.make_request()
        self.config = testing.setUp(
            request=request,
            settings=self._settings,
            autocommit=self._auto_include)
        self.config.get_routes_mapper()
        self.registry = self.config.registry
        self.request.registry = self.registry

        if self._include:
            self.config.include('pyramid_sockjs')
