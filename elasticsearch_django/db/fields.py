# ######################################################################
# The code below is copied from the Django master - it allows
# for custom encoders, which is what we need to handle the
# serialization of dates and decimals correctly.
#
# Commit: https://github.com/django/django/commit/13c3e5d5a05e9c358d212d154addd703cac3bc66
#
# TODO: deprecate once we upgrade to 1.11(?)
# ######################################################################
from __future__ import absolute_import

import json as base_json

import django
import django.core.serializers.json
import django.contrib.postgres.fields

from psycopg2.extras import Json


class _JsonAdapter(Json):

    """Customized psycopg2.extras.Json to allow for a custom encoder."""

    def __init__(self, adapted, dumps=None, encoder=None):
        self.encoder = encoder
        super(_JsonAdapter, self).__init__(adapted, dumps=dumps)

    def dumps(self, obj):
        options = {"cls": self.encoder} if self.encoder else {}
        return base_json.dumps(obj, **options)


class _JSONField(django.contrib.postgres.fields.JSONField):

    """Subclass of JSONField updated to use DjangoJSONEncoder."""

    # See https://github.com/django/django/blob/master/django/contrib/postgres/fields/jsonb.py

    def __init__(self, verbose_name=None, encoder=None, name=None, **kwargs):
        self.encoder = encoder or django.core.serializers.json.DjangoJSONEncoder
        super(_JSONField, self).__init__(verbose_name, name, **kwargs)

    def get_prep_value(self, value):
        if value is not None:
            return _JsonAdapter(value, encoder=self.encoder)
        return value


# Django 1.11 and above can use the contrib JSONField as it supports
# the encoder kwarg, which means we can use DjangoJSONEncode; 1.10
# and 1.9 must use our hacked together version (which is a direct
# copy+paste from the 1.11 codebase).
if django.VERSION[0] == 1 and django.VERSION[1] == 11:
    from django.contrib.postgres.fields import JSONField
else:
    # HACK: but it works
    JSONField = _JSONField
