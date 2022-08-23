from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Case, When
from django.db.models.query import QuerySet
from django.utils.timezone import now as tz_now
from django.utils.translation import gettext_lazy as _lazy
from elasticsearch_dsl import Search

from .settings import (
    get_client,
    get_model_index_properties,
    get_model_indexes,
    get_setting,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)

UPDATE_STRATEGY_FULL = "full"
UPDATE_STRATEGY_PARTIAL = "partial"
UPDATE_STRATEGY = get_setting("update_strategy", UPDATE_STRATEGY_FULL)


class SearchDocumentManagerMixin(models.Manager):
    """
    Model manager mixin that adds search document methods.

    There is one method in this class that must implemented -
    `get_search_queryset`. This must return a queryset that is the
    set of objects to be indexed. This queryset is then converted
    into a generator that emits the objects as JSON documents.

    """

    def get_search_queryset(self, index: str = "_all") -> QuerySet:
        """
        Return the dataset used to populate the search index.

        Kwargs:
            index: string, the name of the index we are interested in -
                this allows us to have different sets of objects in
                different indexes. Defaults to '_all', in which case
                all indexes index the same set of objects.

        This must return a queryset object.

        """
        raise NotImplementedError(
            "{} does not implement 'get_search_queryset'.".format(
                self.__class__.__name__
            )
        )

    def in_search_queryset(self, instance_id: int, index: str = "_all") -> bool:
        """
        Return True if an object is part of the search index queryset.

        Sometimes it's useful to know if an object _should_ be indexed. If
        an object is saved, how do you know if you should push that change
        to the search index? The simplest (albeit not most efficient) way
        is to check if it appears in the underlying search queryset.

        NB this method doesn't evaluate the entire dataset, it chains an
        additional queryset filter expression on the end. That's why it's
        important that the `get_search_queryset` method returns a queryset.

        Args:
            instance_id: the id of model object that we are looking for.

        Kwargs:
            index: string, the name of the index in which to check.
                Defaults to '_all'.

        """
        return self.get_search_queryset(index=index).filter(pk=instance_id).exists()

    def from_search_query(self, search_query: SearchQuery) -> QuerySet:
        """
        Return search results as model queryset in search ranking order.

        This method uses the Case .. When .. Then .. End SQL expression
        to annotate a queryset of model instances that map to the
        documents in the SearchQuery.hits collection. Doing this in SQL
        means that we can order the output using the search score which
        may not map onto any known object property.

        If the SearchQuery has highlighting in the query then we then
        iterate through the queryset and add these - this is more
        complex to do in SQL as the highlights are python dicts, and the
        combination of python and SQL is hard when going via the ORM.

        NB The performance of this function is directly related to the
        number of search results returned - if you are returning very
        large pages this may not run quickly. You have been warned.

        """
        if not search_query.hits:
            return self.get_queryset().none()
        case_when_rank = []
        case_when_score = []
        # build up a list of When clauses - one per object in search
        # results. The rank is just the position in the list (1-based).
        for rank, hit in enumerate(search_query.hits, start=1):
            # if custom sorting has been applied, score is null
            score = None if hit["score"] is None else float(hit["score"])
            case_when_rank.append(When(pk=hit["id"], then=rank))
            case_when_score.append(When(pk=hit["id"], then=score))

        # Fetch the matching objects from the database and annotate
        # with the rank and score from above, ordering by the rank.
        qs = (
            self.get_queryset()
            .filter(id__in=search_query.object_ids)
            .annotate(search_rank=Case(*case_when_rank))
            .annotate(search_score=Case(*case_when_score))
            .order_by("search_rank")
        )

        if search_query.has_highlights:
            # NB this iteration will evaluate the qs.
            for obj in qs:
                obj.search_highlights = search_query.get_doc_highlights(obj.id)

        return qs


class SearchDocumentMixin(object):
    """
    Mixin used by models that are indexed for ES.

    This mixin defines the interface exposed by models that
    are indexed ready for ES. The only method that needs
    implementing is `as_search_document`.

    """

    # Django model field types that can be serialized directly into
    # a known format. All other types will need custom serialization.
    # Used by as_search_document_update method
    SIMPLE_UPDATE_FIELD_TYPES = [
        "ArrayField",
        "AutoField",
        "BooleanField",
        "CharField",
        "DateField",
        "DateTimeField",
        "DecimalField",
        "EmailField",
        "FloatField",
        "IntegerField",
        "TextField",
        "URLField",
        "UUIDField",
    ]

    @property
    def search_indexes(self) -> list[str]:
        """Return the list of indexes for which this model is configured."""
        return get_model_indexes(self.__class__)

    @property
    def search_document_cache_key(self) -> str:
        """Key used for storing search docs in local cache."""
        return "elasticsearch_django:{}.{}.{}".format(
            self._meta.app_label, self._meta.model_name, self.pk  # type: ignore
        )

    @property
    def search_doc_type(self) -> str:
        """Return the doc_type used for the model."""
        raise DeprecationWarning("Mapping types have been removed from ES7.x")

    def as_search_document(self, *, index: str) -> dict:
        """
        Return the object as represented in a named index.

        This is named to avoid confusion - if it was `get_search_document`,
        which would be the logical name, it would not be clear whether it
        referred to getting the local representation of the search document,
        or actually fetching it from the index.

        Kwargs:
            index: string, the name of the index in which the object is to
                appear - this allows different representations in different
                indexes. Defaults to '_all', in which case all indexes use
                the same search document structure.

        Returns a dictionary.

        """
        raise NotImplementedError(
            "{} does not implement 'as_search_document'.".format(
                self.__class__.__name__
            )
        )

    def _is_field_serializable(self, field_name: str) -> bool:
        """Return True if the field can be serialized into a JSON doc."""
        return (
            self._meta.get_field(field_name).get_internal_type()  # type: ignore
            in self.SIMPLE_UPDATE_FIELD_TYPES
        )

    def clean_update_fields(self, index: str, update_fields: list[str]) -> list[str]:
        """
        Clean the list of update_fields based on the index being updated.

        If any field in the update_fields list is not in the set of properties
        defined by the index mapping for this model, then we ignore it. If
        a field _is_ in the mapping, but the underlying model field is a
        related object, and thereby not directly serializable, then this
        method will raise a ValueError.

        """
        search_fields = get_model_index_properties(self, index)
        clean_fields = [f for f in update_fields if f in search_fields]
        ignore = [f for f in update_fields if f not in search_fields]
        if ignore:
            logger.debug(
                "Ignoring fields from partial update: %s",
                [f for f in update_fields if f not in search_fields],
            )
        for f in clean_fields:
            if not self._is_field_serializable(f):
                raise ValueError(
                    "'%s' cannot be automatically serialized into a search "
                    "document property. Please override as_search_document_update.",
                    f,
                )
        return clean_fields

    def as_search_document_update(
        self, *, index: str, update_fields: list[str]
    ) -> dict:
        """
        Return a partial update document based on which fields have been updated.

        If an object is saved with the `update_fields` argument passed
        through, then it is assumed that this is a 'partial update'. In
        this scenario we need a {property: value} dictionary containing
        just the fields we want to update.

        This method handles two possible update strategies - 'full' or 'partial'.
        The default 'full' strategy simply returns the value of `as_search_document`
        - thereby replacing the entire document each time. The 'partial' strategy is
        more intelligent - it will determine whether the fields passed are in the
        search document mapping, and return a partial update document that contains
        only those that are. In addition, if any field that _is_ included cannot
        be automatically serialized (e.g. a RelatedField object), then this method
        will raise a ValueError. In this scenario, you should override this method
        in your subclass.

        >>> def as_search_document_update(self, index, update_fields):
        ...     if 'user' in update_fields:
        ...         update_fields.remove('user')
        ...         doc = super().as_search_document_update(index, update_fields)
        ...         doc['user'] = self.user.get_full_name()
        ...         return doc
        ...     return super().as_search_document_update(index, update_fields)

        You may also wish to subclass this method to perform field-specific logic
        - in this example if only the timestamp is being saved, then ignore the
        update if the timestamp is later than a certain time.

        >>> def as_search_document_update(self, index, update_fields):
        ...     if update_fields == ['timestamp']:
        ...         if self.timestamp > today():
        ...            return {}
        ...     return super().as_search_document_update(index, update_fields)

        """
        if UPDATE_STRATEGY == UPDATE_STRATEGY_FULL:
            return self.as_search_document(index=index)

        if UPDATE_STRATEGY == UPDATE_STRATEGY_PARTIAL:
            # in partial mode we update the intersection of update_fields and
            # properties found in the mapping file.
            return {
                k: getattr(self, k)
                for k in self.clean_update_fields(
                    index=index, update_fields=update_fields
                )
            }

        raise ValueError("Invalid update strategy.")

    def as_search_action(self, *, index: str, action: str) -> dict:
        """
        Return an object as represented in a bulk api operation.

        Bulk API operations have a very specific format. This function will
        call the standard `as_search_document` method on the object and then
        wrap that up in the correct format for the action specified.

        https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html

        Args:
            index: string, the name of the index in which the action is to
                be taken. Bulk operations are only every carried out on a single
                index at a time.
            action: string ['index' | 'update' | 'delete'] - this decides
                how the final document is formatted.

        Returns a dictionary.

        """
        if action not in ("index", "update", "delete"):
            raise ValueError("Action must be 'index', 'update' or 'delete'.")

        document = {
            "_index": index,
            "_op_type": action,
            "_id": self.pk,  # type: ignore
        }

        if action == "index":
            document["_source"] = self.as_search_document(index=index)
        elif action == "update":
            document["doc"] = self.as_search_document(index=index)
        return document

    def fetch_search_document(self, *, index: str) -> dict:
        """Fetch the object's document from a search index by id."""
        if not self.pk:  # type: ignore
            raise ValueError("Object must have a primary key before being indexed.")
        client = get_client()
        return client.get(index=index, id=self.pk)  # type: ignore

    def index_search_document(self, *, index: str) -> None:
        """
        Create or replace search document in named index.

        Checks the local cache to see if the document has changed,
        and if not aborts the update, else pushes to ES, and then
        resets the local cache. Cache timeout is set as "cache_expiry"
        in the settings, and defaults to 60s.

        """
        cache_key = self.search_document_cache_key
        new_doc = self.as_search_document(index=index)
        cached_doc = cache.get(cache_key)
        if new_doc == cached_doc:
            logger.debug("Search document for %r is unchanged, ignoring update.", self)
            return
        cache.set(cache_key, new_doc, timeout=get_setting("cache_expiry", 60))
        get_client().index(index=index, body=new_doc, id=self.pk)  # type: ignore

    def update_search_document(self, *, index: str, update_fields: list[str]) -> None:
        """
        Partial update of a document in named index.

        Partial updates are invoked via a call to save the document
        with 'update_fields'. These fields are passed to the
        as_search_document method so that it can build a partial
        document. NB we don't just call as_search_document and then
        strip the fields _not_ in update_fields as we are trying
        to avoid possibly expensive operations in building the
        source document. The canonical example for this method
        is updating a single timestamp on a model - we don't want
        to have to walk the model relations and build a document
        in this case - we just want to push the timestamp.

        When POSTing a partial update the `as_search_document` doc
        must be passed to the `client.update` wrapped in a "doc" node,
        # noqa: E501, see: https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html

        """
        doc = self.as_search_document_update(index=index, update_fields=update_fields)
        if not doc:
            logger.debug("Ignoring object update as document is empty.")
            return
        retry_on_conflict = cast(int, get_setting("retry_on_conflict", 0))
        get_client().update(
            index=index,
            id=self.pk,  # type: ignore
            body={"doc": doc},
            retry_on_conflict=retry_on_conflict,
        )

    def delete_search_document(self, *, index: str) -> None:
        """Delete document from named index."""
        cache.delete(self.search_document_cache_key)
        get_client().delete(index=index, id=self.pk)  # type: ignore


class SearchQuery(models.Model):
    """
    Model used to capture ES queries and responses.

    For low-traffic sites it's useful to be able to replay
    searches, and to track how a user filtered and searched.
    This model can be used to store a search query and meta
    information about the results (document type, id and score).

    >>> from elasticsearch_dsl import Search
    >>> search = Search(using=client)
    >>> sq = SearchQuery.execute(search).save()

    """

    class TotalHitsRelation(models.TextChoices):
        """The hits.total.relation response value."""

        ACCURATE = "eq", _lazy("Accurate hit count")
        ESTIMATE = "gte", _lazy("Lower bound of total hits")

    class QueryType(models.TextChoices):
        # whether this is a search query (returns results), or a count API
        # query (returns the number of results, but no detail),
        SEARCH = "SEARCH", _lazy("Search results")
        COUNT = "COUNT", _lazy("Count only")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="search_queries",
        blank=True,
        null=True,
        help_text=_lazy("The user who made the search query (nullable)."),
        on_delete=models.SET_NULL,
    )
    index = models.CharField(
        max_length=100,
        default="_all",
        help_text=_lazy("The name of the Elasticsearch index(es) being queried."),
    )
    # The query property contains the raw DSL query, which can be arbitrarily complex -
    # there is no one way of mapping input text to the query itself. However, it's
    # often helpful to have the terms that the user themselves typed easily accessible
    # without having to parse JSON.
    search_terms = models.CharField(
        max_length=400,
        default="",
        blank=True,
        help_text=_lazy(
            "Free text search terms used in the query, stored for easy reference."
        ),
    )
    query = models.JSONField(
        help_text=_lazy("The raw Elasticsearch DSL query."), encoder=DjangoJSONEncoder
    )
    query_type = models.CharField(
        help_text=_lazy("Does this query return results, or just the hit count?"),
        choices=QueryType.choices,
        default=QueryType.SEARCH,
        max_length=10,
    )
    hits = models.JSONField(
        help_text=_lazy(
            "The list of meta info for each of the query matches returned."
        ),
        encoder=DjangoJSONEncoder,
    )
    total_hits = models.IntegerField(
        default=0,
        help_text=_lazy(
            "Total number of matches found for the query (!= the hits returned)."
        ),
    )
    total_hits_relation = models.CharField(
        max_length=3,
        default="",
        blank=True,
        choices=TotalHitsRelation.choices,
        help_text=_lazy(
            "Indicates whether this is an exact match ('eq') or a lower bound ('gte')"
        ),
    )
    aggregations = models.JSONField(
        help_text=_lazy("The raw aggregations returned from the query."),
        encoder=DjangoJSONEncoder,
        default=dict,
    )
    reference = models.CharField(
        max_length=100,
        default="",
        blank=True,
        help_text=_lazy(
            "Custom reference used to identify and group related searches."
        ),
    )
    executed_at = models.DateTimeField(
        help_text=_lazy("When the search was executed - set via execute() method.")
    )
    duration = models.FloatField(
        help_text=_lazy("Time taken to execute the search itself, in seconds.")
    )

    class Meta:
        app_label = "elasticsearch_django"
        verbose_name = "Search query"
        verbose_name_plural = "Search queries"

    def __str__(self) -> str:
        return f"Query (id={self.pk}) run against index '{self.index}'"

    def __repr__(self) -> str:
        return (
            f"<SearchQuery id={self.pk} user={self.user} "
            f"index='{self.index}' total_hits={self.total_hits} >"
        )

    def save(self, *args: Any, **kwargs: Any) -> SearchQuery:
        """Save and return the object (for chaining)."""
        if self.search_terms is None:
            self.search_terms = ""
        super().save(**kwargs)
        return self

    def _extract_set(self, _property: str) -> list[str | int]:
        return [] if self.hits is None else (list({h[_property] for h in self.hits}))

    @property
    def doc_types(self) -> list[str]:
        """List of doc_types extracted from hits."""
        raise DeprecationWarning("Mapping types have been removed from ES7.x")

    @property
    def max_score(self) -> int:
        """Max relevance score in the returned page."""
        return int(max(self._extract_set("score") or [0]))

    @property
    def min_score(self) -> int:
        """Min relevance score in the returned page."""
        return int(min(self._extract_set("score") or [0]))

    @property
    def object_ids(self) -> list[int]:
        """List of model ids extracted from hits."""
        return [int(x) for x in self._extract_set("id")]

    @property
    def page_slice(self) -> tuple[int, int] | None:
        """Return the query from:size tuple (0-based)."""
        return (
            None
            if self.query is None
            else (self.query.get("from", 0), self.query.get("size", 10))
        )

    @property
    def page_from(self) -> int:
        """1-based index of the first hit in the returned page."""
        if self.page_size == 0:
            return 0
        if not self.page_slice:
            return 0
        return self.page_slice[0] + 1

    @property
    def page_to(self) -> int:
        """1-based index of the last hit in the returned page."""
        return 0 if self.page_size == 0 else self.page_from + self.page_size - 1

    @property
    def page_size(self) -> int:
        """Return number of hits returned in this specific page."""
        return 0 if self.hits is None else len(self.hits)

    @property
    def has_aggs(self) -> bool:
        """Return True if the query includes aggs."""
        return "aggs" in self.query

    @property
    def has_highlights(self) -> bool:
        """Return True if the query includes aggs."""
        if not self.query:
            raise ValueError("Missing query attribute.")
        return "highlight" in self.query

    def get_hit(self, doc_id: int | str) -> dict:
        """
        Return the hit with a give document id.

        Raises KeyError if the id does not exist.

        """
        if hit := [h for h in self.hits if h["id"] == str(doc_id)]:
            return hit[0]
        raise KeyError("Document id not found in search results.")

    def get_doc_rank(self, doc_id: int | str) -> int:
        """Return the position of a document in the results."""
        return [x for x in self._extract_set("id")].index(str(doc_id))

    def get_doc_score(self, doc_id: int | str) -> float:
        """Return specific document score."""
        return self.get_hit(doc_id)["score"]

    def get_doc_highlights(self, doc_id: int | str) -> dict | None:
        """Return specific document highlights."""
        return self.get_hit(doc_id).get("highlight")


def execute_search(
    search: Search,
    *,
    search_terms: str = "",
    user: AbstractBaseUser | None = None,
    reference: str | None = "",
    save: bool = True,
) -> SearchQuery:
    """
    Create a new SearchQuery instance and execute a search against ES.

    Args:
        search: elasticsearch.search.Search object, that internally contains
            the connection and query; this is the query that is executed. All
            we are doing is logging the input and parsing the output.
        search_terms: raw end user search terms input - what they typed into the search
            box.
        user: Django User object, the person making the query - used for logging
            purposes. Can be null.
        reference: string, can be anything you like, used for identification,
            grouping purposes.
        save: bool, if True then save the new object immediately, can be
            overridden to False to prevent logging absolutely everything.
            Defaults to True

    """
    start = time.time()
    response = search.execute()
    hits = [h.meta.to_dict() for h in response.hits]
    total_hits = response.hits.total.value
    total_hits_relation = response.hits.total.relation
    aggregations = response.aggregations.to_dict()
    duration = time.time() - start
    search_query = SearchQuery(
        user=user,
        search_terms=search_terms,
        index=", ".join(search._index or ["_all"])[:100],  # field length restriction
        query=search.to_dict(),
        query_type=SearchQuery.QueryType.SEARCH,
        hits=hits,
        aggregations=aggregations,
        total_hits=total_hits,
        total_hits_relation=total_hits_relation,
        reference=reference or "",
        executed_at=tz_now(),
        duration=duration,
    )
    search_query.response = response
    return search_query.save() if save else search_query


def execute_count(
    search: Search,
    *,
    search_terms: str = "",
    user: AbstractBaseUser | None = None,
    reference: str | None = "",
    save: bool = True,
) -> SearchQuery:
    """
    Run a "count" against ES and store the results.

    Args:
        search: elasticsearch.search.Search object, that internally contains
            the connection and query; this is the query that is executed. All
            we are doing is logging the input and parsing the output.
        search_terms: raw end user search terms input - what they typed into the search
            box.
        user: Django User object, the person making the query - used for logging
            purposes. Can be null.
        reference: string, can be anything you like, used for identification,
            grouping purposes.
        save: bool, if True then save the new object immediately, can be
            overridden to False to prevent logging absolutely everything.
            Defaults to True

    """
    start = time.time()
    response = search.count()
    duration = time.time() - start
    search_query = SearchQuery(
        user=user,
        search_terms=search_terms,
        index=", ".join(search._index or ["_all"])[:100],  # field length restriction
        query=search.to_dict(),
        query_type=SearchQuery.QueryType.COUNT,
        hits=[],
        aggregations={},
        total_hits=response,
        total_hits_relation=SearchQuery.TotalHitsRelation.ACCURATE,
        reference=reference or "",
        executed_at=tz_now(),
        duration=duration,
    )
    search_query.response = response
    return search_query.save() if save else search_query
