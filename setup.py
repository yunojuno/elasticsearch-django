from os import path, chdir, pardir
from setuptools import setup, find_packages

from elasticsearch_django import __version__

README = open(path.join(path.dirname(__file__), 'README.rst')).read()

# allow setup.py to be run from any path
chdir(path.normpath(path.join(path.abspath(__file__), pardir)))

setup(
    name="elasticsearch-django",
    version=__version__,
    packages=find_packages(),
    install_requires=[
        'Django>=1.11',
        'elasticsearch>=6,<7',
        'elasticsearch-dsl>=6,<7',
        'psycopg2-binary>=2.6',
        'simplejson>=3.8'
    ],
    include_package_data=True,
    license='MIT',
    description='Elasticsearch Django app',
    long_description=README,
    url='https://github.com/yunojuno/elasticsearch-django',
    author='YunoJuno',
    author_email='code@yunojuno.com',
    maintainer='YunoJuno',
    maintainer_email='code@yunojuno.com',
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Framework :: Django',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.0',
        'Framework :: Django :: 2.1',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
)
