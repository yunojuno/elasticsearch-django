# search.tests package identifier
from django.db import models

from ..models import (
    SearchDocumentMixin,
    SearchDocumentManagerMixin
)


SEARCH_DOC = {"foo": "bar"}


class TestModelManager(SearchDocumentManagerMixin, models.Manager):
    pass


class TestModel(SearchDocumentMixin, models.Model):

    """Model class for use in tests."""

    class Meta:
        # should prevent db errors during tests
        managed = False

    objects = TestModelManager()

    def as_search_document(self, index):
        return SEARCH_DOC

    def as_search_document_update(self, index, update_fields):
        return SEARCH_DOC
