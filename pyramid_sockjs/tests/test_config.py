from pyramid.request import Request
from pyramid.events import NewRequest
from pyramid.exceptions import ConfigurationError

from base import BaseTestCase


class PyramidDirectiveTestCase(BaseTestCase):

    _include = False

    def test_directive_add_sockjs_route(self):
        self.config.include('pyramid_sockjs')

        self.assertTrue(hasattr(self.config, 'add_sockjs_route'))

    def test_directive_get_sockjs_manager(self):
        self.config.include('pyramid_sockjs')

        request = Request(self._environ)
        request.registry = self.registry
        self.registry.notify(NewRequest(request))

        self.assertTrue(hasattr(request, 'get_sockjs_manager'))


class AddSockJSRouteTestCase(BaseTestCase):

    def setUp(self):
        super(AddSockJSRouteTestCase, self).setUp()

        self._views = views = {}
        self._views_info = views_info = {}
        self._routes = routes = {}

        def add_route(name, pattern):
            routes[name] = pattern

        def add_view(route_name=None, view=None,
                     permission=None, decorator=None):
            views[route_name] = view
            views_info[route_name] = (permission, decorator)

        self.config.add_route = add_route
        self.config.add_view = add_view

    def test_basic(self):
        name = ''
        self.config.add_sockjs_route()

        self.assertIn('sockjs-%s'%name, self._routes)
        self.assertIn('sockjs-info-%s'%name, self._routes)
        self.assertIn('sockjs-iframe-%s'%name, self._routes)
        self.assertIn('sockjs-iframe-ver-%s'%name, self._routes)

        self.assertIn(self._routes['sockjs-%s'%name],
                      '/__sockjs__/{server}/{session}/{transport}')
        self.assertIn(self._routes['sockjs-info-%s'%name],
                      '/__sockjs__/info')
        self.assertIn(self._routes['sockjs-iframe-%s'%name],
                      '/__sockjs__/iframe.html')
        self.assertIn(self._routes['sockjs-iframe-ver-%s'%name],
                      '/__sockjs__/iframe{version}.html')

        self.assertIn('sockjs-%s'%name, self._views)
        self.assertIn('sockjs-info-%s'%name, self._views)
        self.assertIn('sockjs-iframe-%s'%name, self._views)
        self.assertIn('sockjs-iframe-ver-%s'%name, self._views)

    def test_permission_decorator(self):
        name = ''
        permission = 1
        decorator = 2

        self.config.add_sockjs_route(permission=permission,
                                     decorator=decorator)

        val = (permission, decorator)

        self.assertEqual(val, self._views_info['sockjs-%s'%name])
        self.assertEqual(val, self._views_info['sockjs-info-%s'%name])
        self.assertEqual(val, self._views_info['sockjs-iframe-%s'%name])
        self.assertEqual(val, self._views_info['sockjs-iframe-ver-%s'%name])

    def test_config_error(self):
        self.config.add_sockjs_route('route')
        self.assertRaises(
            ConfigurationError, self.config.add_sockjs_route, 'route')

    def test_custom_name(self):
        name = 'chat-service'
        self.config.add_sockjs_route(name)

        self.assertIn('sockjs-%s'%name, self._routes)
        self.assertIn('sockjs-info-%s'%name, self._routes)
        self.assertIn('sockjs-iframe-%s'%name, self._routes)
        self.assertIn('sockjs-iframe-ver-%s'%name, self._routes)

        self.assertIn('sockjs-%s'%name, self._views)
        self.assertIn('sockjs-info-%s'%name, self._views)
        self.assertIn('sockjs-iframe-%s'%name, self._views)
        self.assertIn('sockjs-iframe-ver-%s'%name, self._views)

    def test_custom_prefix(self):
        name = ''
        prefix = '/__chat__/'

        self.config.add_sockjs_route(name, prefix=prefix)

        self.assertIn(self._routes['sockjs-%s'%name],
                      '/__chat__/{server}/{session}/{transport}')
        self.assertIn(self._routes['sockjs-info-%s'%name],
                      '/__chat__/info')
        self.assertIn(self._routes['sockjs-iframe-%s'%name],
                      '/__chat__/iframe.html')
        self.assertIn(self._routes['sockjs-iframe-ver-%s'%name],
                      '/__chat__/iframe{version}.html')

    def test_session_manager_name(self):
        import pyramid_sockjs

        name = 'example'
        self.config.add_sockjs_route(name)

        self.assertTrue(hasattr(self.registry, '__sockjs_managers__'))
        self.assertIn(name, self.registry.__sockjs_managers__)
        self.assertIsInstance(
            self.registry.__sockjs_managers__[name],
            pyramid_sockjs.SessionManager)

    def test_get_session_manager_default(self):
        import pyramid_sockjs
        self.config.add_sockjs_route()

        request = Request(self._environ)
        request.registry = self.registry
        self.registry.notify(NewRequest(request))

        sm = request.get_sockjs_manager()
        self.assertIs(self.registry.__sockjs_managers__[''], sm)

    def test_get_session_manager_unknown(self):
        request = Request(self._environ)
        request.registry = self.registry
        self.registry.notify(NewRequest(request))

        self.assertRaises(
            KeyError, request.get_sockjs_manager, 'test')

        self.config.add_sockjs_route()
        self.assertRaises(
            KeyError, request.get_sockjs_manager, 'test')

    def test_get_session_manager_name(self):
        import pyramid_sockjs

        name = 'example'
        self.config.add_sockjs_route(name)

        request = Request(self._environ)
        request.registry = self.registry
        self.registry.notify(NewRequest(request))

        sm = request.get_sockjs_manager(name)

        self.assertIs(self.registry.__sockjs_managers__[name], sm)

    def test_custom_session(self):
        import pyramid_sockjs

        class ChatSession(pyramid_sockjs.Session):
            """ """

        self.config.add_sockjs_route(session=ChatSession)
        self.assertIs(
            self.registry.__sockjs_managers__[''].factory, ChatSession)

    def test_custom_session_manager(self):
        import pyramid_sockjs

        class ChatSessionManager(pyramid_sockjs.SessionManager):
            """ """

        sm = ChatSessionManager('chat', self.registry)

        self.config.add_sockjs_route('chat', session_manager=sm)
        self.assertIs(self.registry.__sockjs_managers__['chat'], sm)

    def test_custom_session_manager_different_names(self):
        import pyramid_sockjs

        class ChatSessionManager(pyramid_sockjs.SessionManager):
            """ """

        sm = ChatSessionManager('chat', self.registry)

        self.assertRaises(
            ConfigurationError,
            self.config.add_sockjs_route, 'other-chat', session_manager=sm)


class SessionManagerRouteUrlTestCase(BaseTestCase):

    def test_session_manager_route_url(self):
        import pyramid_sockjs

        name = 'example'
        self.config.add_sockjs_route(name, prefix='/chat-service')
        self.config.commit()

        request = Request(self._environ)
        request.registry = self.registry
        self.registry.notify(NewRequest(request))

        sm = request.get_sockjs_manager(name)
        self.assertEqual(
            sm.route_url(request), 'http://example.com/chat-service/')
