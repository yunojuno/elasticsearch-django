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

import django.core.serializers.json
import django.contrib.postgres.fields

from psycopg2.extras import Json


class JsonAdapter(Json):

    """Customized psycopg2.extras.Json to allow for a custom encoder."""

    def __init__(self, adapted, dumps=None, encoder=None):
        self.encoder = encoder
        super(JsonAdapter, self).__init__(adapted, dumps=dumps)

    def dumps(self, obj):
        options = {'cls': self.encoder} if self.encoder else {}
        return base_json.dumps(obj, **options)


class JSONField(django.contrib.postgres.fields.JSONField):

    """Subclass of JSONField updated to use DjangoJSONEncoder."""

    # See https://github.com/django/django/blob/master/django/contrib/postgres/fields/jsonb.py

    def __init__(self, verbose_name=None, name=None, **kwargs):
        self.encoder = django.core.serializers.json.DjangoJSONEncoder
        super(JSONField, self).__init__(verbose_name, name, **kwargs)

    def get_prep_value(self, value):
        if value is not None:
            return JsonAdapter(value, encoder=self.encoder)
        return value
