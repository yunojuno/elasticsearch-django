# -*- coding: utf-8 -*-
"""elasticsearch_django model admin."""
import simplejson as json  # simplejson supports Decimal serialization
import logging

from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import SearchQuery

logger = logging.getLogger(__name__)


def pprint(data):
    """
    Returns an indented HTML pretty-print version of JSON.

    Take the event_payload JSON, indent it, order the keys and then
    present it as a <code> block. That's about as good as we can get
    until someone builds a custom syntax function.

    """
    pretty = json.dumps(
        data,
        sort_keys=True,
        indent=4,
        separators=(',', ': ')
    )
    html = pretty.replace(" ", "&nbsp;").replace("\n", "<br>")
    return mark_safe("<code>%s</code>" % html)


class SearchQueryAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'index',
        'total_hits',
        'returned_',
        'min_',
        'max_',
        'reference',
        'executed_at',
    )
    list_filter = (
        'index',
    )
    # excluding because we are using a pretty version instead
    exclude = ('hits', 'query', 'page')
    readonly_fields = (
        'user',
        'index',
        'total_hits',
        'returned_',
        'min_',
        'max_',
        'duration',
        'query_',
        'hits_',
        'executed_at',
    )

    def query_(self, instance):
        """Pretty version of query JSON."""
        return pprint(instance.query)

    def max_(self, instance):
        """Pretty version of max_score."""
        return '-' if instance.page_size == 0 else instance.max_score
    max_.short_description = "Max score"

    def min_(self, instance):
        """Pretty version of min_score."""
        return '-' if instance.page_size == 0 else instance.min_score
    min_.short_description = "Min score"

    def returned_(self, instance):
        """Number of hits returned in the page."""
        if instance.page_size == 0:
            return '-'
        else:
            return "%i - %i" % (instance.page_from, instance.page_to)

    returned_.short_description = "Page returned"

    def hits_(self, instance):
        """Pretty version of hits JSON."""
        return pprint(instance.hits)

admin.site.register(SearchQuery, SearchQueryAdmin)
