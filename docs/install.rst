============
Installation
============

virtualenv
==========

1. Install virtualenv::

    $ wget https://raw.github.com/pypa/virtualenv/master/virtualenv.py
    $ python2.7 ./virtualenv.py --no-site-packages sockjs

2. Install gevent 1.0b1::

    $ ./sockjs/bin/pip install http://gevent.googlecode.com/files/gevent-1.0b1.tar.gz

3. Clone pyramid_sockjs from github and then install::

    $ git clone git://github.com/fafhrd91/pyramid_sockjs.git
    $ cd pyramid_sockjs
    $ ../sockjs/bin/python setup.py develop


Server config
=============

To use gevent based server use following configuration
for server section::

    [server:main]
    use = egg:pyramid_sockjs#server
    host = 127.0.0.1
    port = 8080

To use gunicorn server use following configuation for server section::

    [server:main]
    use = egg:gunicorn
    host = 127.0.0.1
    port = 8080
    workers = 1
    worker_class = gevent


Chat example
============

You can run `chat` example with following command. It doesnt require
any configuration, it runs on host ``127.0.0.1`` and port ``8080``::


    $ ./sockjs/bin/python ./pyramid_sockjs/examples/chat.py
