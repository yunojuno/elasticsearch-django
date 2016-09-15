# This file was sourced from github.com/django-extensions/django-extensions

# but split off into this project to allow patching for Django 1.3+ to code
# around DeprecationWarnings
import datetime
from decimal import Decimal

import simplejson as json
# While Django 1.6+ recommends json over simplejson, we're still using it
# here because simplejson gets Decimal reincantation right (ie, it does it),
# whereas stdlib's json returns the value as a plain string.

from django.db import models
from django.conf import settings
from django.utils.encoding import force_text


"""
JSONField automatically serializes most Python terms to JSON data.
Creates a TEXT field with a default value of "{}".

 from django.db import models
 from yunojuno.apps.core.fields import JSONField

 class LOL(models.Model):
     extra = JSONField()
"""


class JSONEncoder(json.JSONEncoder):
    # Note that we store all dates and datetimes as UTC, in the isoformat
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()

        return json.JSONEncoder.default(self, obj)


def dumps(value):
    try:
        assert isinstance(value, dict)
    except AssertionError:
        try:
            assert isinstance(value, list)
        except AssertionError:
            raise

    return JSONEncoder().encode(value)


def loads(txt):
    value = json.loads(
        txt,
        parse_float=Decimal,
        encoding=settings.DEFAULT_CHARSET
    )
    try:
        assert isinstance(value, dict)
    except AssertionError:
        try:
            assert isinstance(value, list)
        except AssertionError:
            raise
    return value


class JSONDict(dict):
    """
    Hack so repr() called by dumpdata will output JSON instead of
    Python formatted data.  This way fixtures will work!
    """
    def __repr__(self):
        return dumps(self)


class JSONList(list):
    """
    Similar to JSONDict, but for Lists/Arrays
    """
    def __repr__(self):
        return dumps(self)


class JSONField(models.TextField):
    """JSONField is a generic textfield that neatly serializes/unserializes
    JSON objects seamlessly.  Main thingy must be a dict or a list (ie: JS map or array) """

    # Used so to_python() is called
    __metaclass__ = models.SubfieldBase

    def __init__(self, *args, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = '{}'
        models.TextField.__init__(self, *args, **kwargs)

    def to_python(self, value):
        """Convert our string value to JSON after we load it from the DB"""
        if not value:
            return {}
        elif isinstance(value, basestring):
            res = loads(value)
            try:
                assert isinstance(res, dict)
                return JSONDict(**res)
            except AssertionError:
                try:
                    assert isinstance(res, list)
                    return JSONList(res)
                except AssertionError:
                    raise
        else:
            return value

    def get_db_prep_save(self, value, connection):
        """Convert our JSON object to a string before we save"""

        if not isinstance(value, (list, dict)):
            # NOTE: this is a little ruthless, but works
            return super(JSONField, self).get_db_prep_save(
                "",
                connection
            )
        else:
            return super(JSONField, self).get_db_prep_save(
                dumps(value),
                connection
            )

    def deconstruct(self):
        """
        Returns enough information to recreate the field as a 4-tuple:
         * The name of the field on the model, if contribute_to_class has been run
         * The import path of the field, including the class: django.db.models.IntegerField
           This should be the most portable version, so less specific may be better.
         * A list of positional arguments
         * A dict of keyword arguments
        """

        name, path, args, kwargs = super(models.TextField, self).deconstruct()
        path = "elasticsearch_django.db.fields.JSONField"
        # see https://docs.djangoproject.com/en/dev/howto/
        #   custom-model-fields/#custom-field-deconstruct-method

        # only include the default if it's not in the kwargs
        if 'default' not in kwargs:
            kwargs['default'] = '{}'

        return (
            force_text(self.name, strings_only=True),
            path,
            args,
            kwargs,
        )
