# -*- coding: utf-8 -*-
from os import path, chdir, pardir
from setuptools import setup, find_packages

README = open(path.join(path.dirname(__file__), 'README.rst')).read()
# requirements.txt must be included in MANIFEST.in and include_package_data must be True
# in order for this to work; ensures that tox can use the setup to enforce requirements
REQUIREMENTS = '\n'.join(open(path.join(path.dirname(__file__), 'requirements.txt')).readlines())  # noqa

# allow setup.py to be run from any path
chdir(path.normpath(path.join(path.abspath(__file__), pardir)))

setup(
    name="elasticsearch-django",
    version="0.5.0",
    packages=find_packages(),
    install_requires=REQUIREMENTS,
    include_package_data=True,
    description='Elasticsearch Django app',
    long_description=README,
    url='https://github.com/yunojuno/elasticsearch-django',
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
