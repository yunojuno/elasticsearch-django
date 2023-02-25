from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from django.db.models import signals

from .apps import _on_model_save


@contextmanager
def disable_search_updates() -> Generator:
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
    # get a list of the receivers for the search updates
    search_update_receivers = [
        r for r in signals.post_save.receivers if r[1]() == _on_model_save
    ]
    # strip them from the current post_save receivers
    signals.post_save.receivers = [
        r for r in signals.post_save.receivers if r not in search_update_receivers
    ]
    signals.post_save.sender_receivers_cache.clear()
    yield
    # add them back on again
    signals.post_save.receivers += search_update_receivers
    signals.post_save.sender_receivers_cache.clear()
