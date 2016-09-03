import os
from setuptools import setup

README = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="elasticsearch-django",
    version="0.1",
    packages=[
        'elasticsearch_django',
        'elasticsearch_django.migrations',
        'elasticsearch_django.management.commands'
    ],
    install_requires=['django>=1.8', 'elasticsearch-dsl>=2.0'],
    include_package_data=True,
    description='Django-aware Elasticsearch library.',
    long_description=README,
    url='https://github.com/yunojuno/django-elasticsearch',
    author='Hugo Rodger-Brown',
    author_email='code@yunojuno.com',
    maintainer='Hugo Rodger-Brown',
    maintainer_email='hugo@yunojuno.com',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
