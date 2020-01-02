from django.db import models
from elasticsearch_django.models import SearchDocumentManagerMixin, SearchDocumentMixin

SEARCH_DOC = {"foo": "bar"}


class IndexedModelManager(SearchDocumentManagerMixin, models.Manager):
    pass


class IndexedModel(SearchDocumentMixin, models.Model):

    """Model class for use in tests."""

    simple_field_1 = models.IntegerField()
    simple_field_2 = models.CharField(max_length=100)
    complex_field = models.FileField()

    class Meta:
        # should prevent db errors during tests
        managed = False

    objects = IndexedModelManager()

    def as_search_document(self, index):
        return SEARCH_DOC
