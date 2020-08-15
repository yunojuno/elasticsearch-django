# Support for old and new (3.1+) JSONField
try:
    from django.db.models import JSONField  # noqa: F401
except ImportError:
    from django.contrib.postgres.fields import JSONField  # noqa: F401
