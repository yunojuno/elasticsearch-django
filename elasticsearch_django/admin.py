import logging

import simplejson as json  # simplejson supports Decimal serialization
from django.contrib import admin
from django.template.defaultfilters import truncatechars, truncatewords
from django.utils.safestring import mark_safe

from .models import SearchQuery

logger = logging.getLogger(__name__)


def pretty_print(data: dict) -> str:
    """
    Return an indented HTML pretty-print version of JSON.

    Take the event_payload JSON, indent it, order the keys and then
    present it as a <code> block. That's about as good as we can get
    until someone builds a custom syntax function.

    """
    pretty = json.dumps(data, sort_keys=True, indent=4, separators=(",", ": "))
    html = pretty.replace(" ", "&nbsp;").replace("\n", "<br>")
    return mark_safe("<code>%s</code>" % html)  # noqa S703, S308


class SearchQueryAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "search_terms_display",
        "total_hits_display",
        "returned_",
        "min_",
        "max_",
        "reference",
        "executed_at",
    )
    list_filter = ("index", "query_type")
    search_fields = ("search_terms", "user__first_name", "user__last_name", "reference")
    # excluding because we are using a pretty version instead
    exclude = ("hits", "aggregations", "query", "page", "total_hits_")
    readonly_fields = (
        "user",
        "index",
        "search_terms",
        "query_type",
        "total_hits",
        "total_hits_relation",
        "returned_",
        "min_",
        "max_",
        "duration",
        "query_",
        "hits_",
        "aggregations_",
        "executed_at",
    )

    def search_terms_display(self, instance: SearchQuery) -> str:
        """Return truncated version of search_terms."""
        raw = instance.search_terms
        # take first five words, and further truncate to 50 chars if necessary
        return truncatechars(truncatewords(raw, 5), 50)

    def query_(self, instance: SearchQuery) -> str:
        """Return pretty version of query JSON."""
        return pretty_print(instance.query)

    def max_(self, instance: SearchQuery) -> str:
        """Return pretty version of max_score."""
        return "-" if instance.page_size == 0 else str(instance.max_score)

    max_.short_description = "Max score"  # type: ignore

    def min_(self, instance: SearchQuery) -> str:
        """Return pretty version of min_score."""
        return "-" if instance.page_size == 0 else str(instance.min_score)

    min_.short_description = "Min score"  # type: ignore

    def total_hits_display(self, instance: SearchQuery) -> str:
        """Return total hit count, annotated if lower bound."""
        if instance.total_hits_relation == SearchQuery.TotalHitsRelation.ESTIMATE:
            return f"{instance.total_hits}*"
        return f"{instance.total_hits}"

    def returned_(self, instance: SearchQuery) -> str:
        """Return number of hits returned in the page."""
        if instance.page_size == 0:
            return "-"
        return "%i - %i" % (instance.page_from, instance.page_to)

    returned_.short_description = "Page returned"  # type: ignore

    def hits_(self, instance: SearchQuery) -> str:
        """Return pretty version of hits JSON."""
        return pretty_print(instance.hits)

    def aggregations_(self, instance: SearchQuery) -> str:
        """Return pretty version of aggregations JSON."""
        return pretty_print(instance.aggregations)


admin.site.register(SearchQuery, SearchQueryAdmin)
