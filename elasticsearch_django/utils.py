# -*- coding: utf-8 -*-
from contextlib import contextmanager

from .settings import get_settings


@contextmanager
def disable_search_updates():
    """
    Context manager used to temporarily disable auto_sync.

    This is useful when performing bulk updates on objects - when
    you may not want to flood the indexing process.

    >>> with disable_search_updates():
    ...     for obj in model.objects.all():
    ...     obj.save()

    """
    _settings = get_settings()
    _sync = _settings['auto_sync']
    _settings['auto_sync'] = False
    yield
    _settings['auto_sync'] = _sync
