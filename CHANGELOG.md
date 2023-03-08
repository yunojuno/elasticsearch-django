# Changelog

All notable changes to this project will be documented in this file.

## v8.2 [unreleased]

- Adds support for more complex client configuration [#68 - @ColeDCrawford]

## v8.0

This is a non-functional release - updating the Python, Django and
Elasticsearch version support. It will break if you are using an
unsupported version of any of the above, but should work without
modification if not.

- Adds support for Python 3.11
- Adds support for Django 4.0, 4.1
- Adds support for Elasticsearch 8.x
- Adds support for custom model primary keys

- Removes support for Django 3.0, 3.1
