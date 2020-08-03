from django.db import models

from elasticsearch_django.models import SearchDocumentManagerMixin, SearchDocumentMixin


class ExampleModelManager(SearchDocumentManagerMixin, models.Manager):
    def get_search_queryset(self, index="_all"):
        return self.all()


class ExampleModel(SearchDocumentMixin, models.Model):
    """Model class for use in tests."""

    simple_field_1 = models.IntegerField()
    simple_field_2 = models.CharField(max_length=100)
    complex_field = models.FileField()

    objects = ExampleModelManager()

    def as_search_document(self, index="_all"):
        return {
            "simple_field_1": self.simple_field_1,
            "simple_field_2": self.simple_field_2,
            "complex_field": str(self.complex_field),
        }
