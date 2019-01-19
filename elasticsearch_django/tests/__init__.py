# search.tests package identifier
from django.db import models

from ..models import SearchDocumentMixin, SearchDocumentManagerMixin


SEARCH_DOC = {"foo": "bar"}


class TestModelManager(SearchDocumentManagerMixin, models.Manager):
    pass


class TestModel(SearchDocumentMixin, models.Model):

    """Model class for use in tests."""

    simple_field_1 = models.IntegerField()
    simple_field_2 = models.CharField(max_length=100)
    complex_field = models.FileField()

    class Meta:
        # should prevent db errors during tests
        managed = False

    objects = TestModelManager()

    def as_search_document(self, index):
        return SEARCH_DOC
