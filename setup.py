# -*- coding: utf-8 -*-
from os import path, chdir, pardir
from setuptools import setup, find_packages

README = open(path.join(path.dirname(__file__), 'README.rst')).read()

# allow setup.py to be run from any path
chdir(path.normpath(path.join(path.abspath(__file__), pardir)))

setup(
    name="elasticsearch-django",
    version="5.0.1",
    packages=find_packages(),
    install_requires=[
        'Django>=1.9',
        'elasticsearch>=5',
        'elasticsearch-dsl>=5',
        'psycopg2>=2.6',
        'simplejson>=3.8',
        'future'
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
        'Framework :: Django :: 1.9',
        'Framework :: Django :: 1.10',
        'Framework :: Django :: 1.11',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
