import os
from setuptools import setup, find_packages

version = '0.1'

install_requires = ['aiohttp >= 0.15.1']
tests_require = install_requires + ['nose']


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
          "Programming Language :: Python :: 3.3",
          "Programming Language :: Python :: 3.4",
          "Programming Language :: Python :: Implementation :: CPython",
          "Topic :: Internet :: WWW/HTTP"],
      author='Nikolay Kim',
      author_email='fafhrd91@gmail.com',
      url='https://github.com/aio-libs/sockjs/',
      license='Apache 2',
      packages=find_packages(),
      install_requires=install_requires,
      tests_require=tests_require,
      test_suite='nose.collector',
      include_package_data=True,
      zip_safe=False
)
