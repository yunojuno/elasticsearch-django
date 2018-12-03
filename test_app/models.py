import logging

from django.conf import settings
from elasticsearch_django.models import (
    SearchDocumentMixin,
    SearchDocumentManagerMixin,
)
from django.db import models

logger = logging.getLogger(__name__)


class BookQuerySet(models.QuerySet):

    """Example model used for testing with Elasticsearch."""


class BookManager(SearchDocumentManagerMixin, models.Manager):

    """Example model manager that implements SearchDocumentMixin."""

    def get_search_queryset(self, index='_all'):
        """Exclude profiles from search index where discipline is empty."""
        return self.get_queryset().all().order_by('id')


class Book(SearchDocumentMixin, models.Model):

    """Example model used for testing Elasticsearch."""

    author = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name='books',
        on_delete=models.CASCADE
    )
    title = models.CharField(
        max_length=100,
        blank=False,
        null=False,
    )
    sample = models.TextField(
        blank=True,
        null=True,
    )
    date_published = models.DateField(
        blank=True,
        null=True
    )
    genre = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )
    price = models.DecimalField(
        'Recommended Retail Price',
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )

    def as_search_document(self, index='_all', update_fields=None):
        if update_fields:
            print(f"Partial document update: {update_fields}")
        else:
            print("Full document update")
        return dict(
            author=self.author.get_full_name(),
            title=self.title,
            summary=self.sample,
            price=self.price,
            date_published=self.date_published,
            genre=self.genre
        )

    # set custom model manager
    objects = BookManager.from_queryset(BookQuerySet)()

    def __str__(self):
        return self.title

    def __repr__(self):
        return (
            "<Book id=%s, title='%s', author='%s'>" % (
                self.id,
                self.title,
                self.author.get_full_name()
            )
        )

    def reprice(self, new_price):
        """Update the price only.

        This is used to demonstrate a partial update, as it calls
        the model.save() method with `update_fields` passed in.

        """
        self.price = new_price
        super().save(update_fields=['price'])
