from contextlib import contextmanager

from django.db.models import signals

from .settings import get_settings
from .apps import _on_model_save


def _strip_on_model_save():
    """Returns list of signal receivers without _on_model_save."""
    return [r for r in signals.post_save.receivers if r[1]() != _on_model_save]


@contextmanager
def disable_search_updates():
    """
    Context manager used to temporarily disable auto_sync.

    This is useful when performing bulk updates on objects - when
    you may not want to flood the indexing process.

    >>> with disable_search_updates():
    ...     for obj in model.objects.all():
    ...     obj.save()

    The function works by temporarily removing the apps._on_model_save
    signal handler from the model.post_save signal receivers, and then
    restoring them after.

    """
    _receivers = signals.post_save.receivers.copy()
    signals.post_save.receivers = _strip_on_model_save()
    yield
    signals.post_save.receivers = _receivers
