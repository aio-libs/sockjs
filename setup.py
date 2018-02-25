import codecs
import os
import re
from setuptools import setup, find_packages

with codecs.open(os.path.join(os.path.abspath(os.path.dirname(
        __file__)), 'sockjs', '__init__.py'), 'r', 'latin1') as fp:
    try:
        version = re.findall(r"^__version__ = '([^']+)'\r?$",
                             fp.read(), re.M)[0]
    except IndexError:
        raise RuntimeError('Unable to determine version.')

install_requires = ['aiohttp >= 3.0.0']


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


setup(name='sockjs',
      version=version,
      description=('SockJS server implementation for aiohttp.'),
      long_description='\n\n'.join((read('README.rst'), read('CHANGES.txt'))),
      classifiers=[
          "License :: OSI Approved :: Apache Software License",
          "Intended Audience :: Developers",
          "Programming Language :: Python",
          "Programming Language :: Python :: 3",
          "Programming Language :: Python :: 3.5",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: Implementation :: CPython",
          "Topic :: Internet :: WWW/HTTP",
          "Framework :: AsyncIO",
      ],
      author='Nikolay Kim',
      author_email='fafhrd91@gmail.com',
      url='https://github.com/aio-libs/sockjs/',
      license='Apache 2',
      packages=find_packages(),
      install_requires=install_requires,
      include_package_data=True,
      zip_safe=False)
