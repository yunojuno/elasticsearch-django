from __future__ import annotations

import copy
import logging
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Case, Value, When
from django.db.models.query import QuerySet
from django.utils.functional import SimpleLazyObject
from django.utils.translation import gettext_lazy as _lazy
from elastic_transport import ObjectApiResponse
from elasticsearch import Elasticsearch

from .context_managers import stopwatch
from .settings import (
    get_client,
    get_model_index_properties,
    get_model_indexes,
    get_setting,
)

logger = logging.getLogger(__name__)

UPDATE_STRATEGY_FULL = "full"
UPDATE_STRATEGY_PARTIAL = "partial"
UPDATE_STRATEGY = get_setting("update_strategy", UPDATE_STRATEGY_FULL)

DEFAULT_CLIENT: Elasticsearch = SimpleLazyObject(get_client)
DEFAULT_FROM: int = 0
DEFAULT_PAGE_SIZE = cast(int, get_setting("page_size"))
DEFAULT_INCLUDE_SOURCE = bool(get_setting("include_source", True))


class SearchResultsQuerySet(QuerySet):
    """
    QuerySet mixin that adds annotations from search results.

    This class is designed to be used as a QuerySet mixin for models that can
    be mapped on to a set of search results, but that are not the source models.

    As an example, if you have a Profile model and a ProfileSearchDocument model
    that is a 1:1 relationship, with the ProfileSearchDocument configured to be
    the index source, then this class can be used to map the results from the
    search result id back to the Profile.


        class ProfileQuerySet(SearchDocumentQuerySet):
            pass


        class Profile(Model):
            pass


        class ProfileSearchDocument(SearchDocumentMixing, Model):
            profile = OneToOne(Profile)

            def get_search_document_id(self):
                return self.profile.pk


        >>> search_query = execute_search(...)
        >>> profiles = (
                Profile.objects.all()
                .filter_search_results(search_query)
                .add_search_annotations(search_query)
                .add_search_highlights(search_query)
            )
        ...
        [<Profile>, <Profile>]
        >>> profiles[0].search_rank
        1
        >>> profiles[0].search_score
        3.12345
        >>> profiles[0].search_highlights
        {
            "resume": ["foo"]
        }

    """

    # the field used to map objects to search document id
    search_document_id_field = "pk"

    def filter_search_results(self, search_query: SearchQuery) -> SearchResultsQuerySet:
        """Filter queryset on PK field to match search query hits."""
        return self.filter(
            **{f"{self.search_document_id_field}__in": search_query.object_ids}
        )

    def add_search_rank(self, search_query: SearchQuery) -> SearchResultsQuerySet:
        """Add search_rank annotation to queryset."""
        if search_rank_annotation := search_query.search_rank_annotation(
            self.search_document_id_field
        ):
            return self.annotate(search_rank=search_rank_annotation)
        return self.annotate(search_rank=Value(1))

    def add_search_score(self, search_query: SearchQuery) -> SearchResultsQuerySet:
        """Add search_score annotation to queryset."""
        if search_score_annotation := search_query.search_score_annotation(
            self.search_document_id_field
        ):
            return self.annotate(search_score=search_score_annotation)
        return self.annotate(search_score=Value(1.0))

    def add_search_annotations(
        self, search_query: SearchQuery
    ) -> SearchResultsQuerySet:
        """Add search_rank and search_score annotations to queryset."""
        return self.add_search_rank(search_query).add_search_score(search_query)

    def add_search_highlights(self, search_query: SearchQuery) -> list:
        """Add search_highlights attr. to each object in the queryset (evaluates QS)."""
        obj_list = list(self)
        if not search_query.has_highlights:
            return obj_list

        for obj in obj_list:
            pk = getattr(obj, self.search_document_id_field)
            obj.search_highlights = search_query.get_doc_highlights(pk)
        return obj_list

    def from_search_results(self, search_query: SearchQuery) -> SearchResultsQuerySet:
        qs = self.filter_search_results(search_query)
        qs = qs.add_search_annotations(search_query)
        return qs.order_by("search_rank")


class SearchDocumentManagerMixin(models.Manager):
    """
    Model manager mixin that adds search document methods.

    There is one method in this class that must implemented -
    `get_search_queryset`. This must return a queryset that is the set
    of objects to be indexed. This queryset is then converted into a
    generator that emits the objects as JSON documents.

    If you are using a different database connection for the
    `get_search_queryset` method from the one that you use to save
    models you may run into a situation where the `in_search_queryset`
    method returns False for an object that has been created because the
    `get_search_queryset` query runs in a different transaction from the
    one that created the object.

    To avoid this, you can set the `IN_SEARCH_QUERYSET_DB_ALIAS`
    settings to force `in_search_queryset` to use the same database
    connection as that used to create the object.

    Edge case, but it does happen.

    """

    IN_SEARCH_QUERYSET_DB_ALIAS = get_setting("in_search_queryset_db_alias", "")

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

    def in_search_queryset(self, instance_pk: Any, index: str = "_all") -> bool:
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
            instance_pk: the primary key of model object that we are looking for.

        Kwargs:
            index: string, the name of the index in which to check.
                Defaults to '_all'.

        """
        qs = self.get_search_queryset(index=index).filter(pk=instance_pk)
        if alias := self.IN_SEARCH_QUERYSET_DB_ALIAS:
            qs = qs.using(alias)
        return qs.exists()


class SearchDocumentMixin:
    """
    Mixin used by models that are indexed for ES.

    This mixin defines the interface exposed by models that
    are indexed ready for ES. The only method that needs
    implementing is `as_search_document`.

    """

    @property
    def _model_meta(self) -> Any:
        if not (meta := getattr(self, "_meta")):
            raise ValueError(
                "SearchDocumentMixin missing _meta attr - "
                "have you forgotten to subclass models.Model?"
            )
        return meta

    @property
    def search_indexes(self) -> list[str]:
        """Return the list of indexes for which this model is configured."""
        return get_model_indexes(self.__class__)

    @property
    def search_document_cache_key(self) -> str:
        """Key used for storing search docs in local cache."""
        return "elasticsearch_django:{}.{}.{}".format(
            self._model_meta.app_label,
            self._model_meta.model_name,
            self.get_search_document_id(),
        )

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

    def get_search_document_id(self) -> str:
        """
        Return the value to be used as the search document id.

        This value defaults to the object pk value - which is cast to a
        str value as that is what ES uses.

        It can be overridden in subclasses if you want to use a different
        value.

        """
        return str(getattr(self, "pk"))

    @property
    def _related_fields(self) -> list[str]:
        """Return the list of fields that are relations and not serializable."""
        return [f.name for f in self._model_meta.get_fields() if f.is_relation]

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
            logger.debug("Ignoring fields from partial update: %s", ignore)

        for f in clean_fields:
            if f in self._related_fields:
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

        document: dict[str, str | dict] = {
            "_index": index,
            "_op_type": action,
            "_id": self.get_search_document_id(),
        }

        if action == "index":
            document["_source"] = self.as_search_document(index=index)
        elif action == "update":
            document["doc"] = self.as_search_document(index=index)
        return document

    def fetch_search_document(self, *, index: str) -> ObjectApiResponse:
        """Fetch the object's document from a search index by id."""
        if not self.pk:  # type: ignore
            raise ValueError("Object must have a primary key before being indexed.")
        return get_client().get(index=index, id=self.get_search_document_id())

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
        _ = get_client().index(
            index=index,
            document=new_doc,
            id=self.get_search_document_id(),
        )

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
        _ = get_client().update(
            index=index,
            id=self.get_search_document_id(),
            doc=doc,
            retry_on_conflict=retry_on_conflict,
        )

    def delete_search_document(self, *, index: str) -> None:
        """Delete document from named index."""
        cache.delete(self.search_document_cache_key)
        _ = get_client().delete(index=index, id=self.get_search_document_id())


class SearchQuery(models.Model):
    """
    Model used to capture ES queries and responses.

    For low-traffic sites it's useful to be able to replay
    searches, and to track how a user filtered and searched.
    This model can be used to store a search query and meta
    information about the results (document type, id and score).

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
        blank=True,
        null=True,
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
        default=None,
        blank=True,
        null=True,
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.query_response = kwargs.pop("query_response", None)
        super().__init__(*args, **kwargs)

    def save(self, *args: Any, **kwargs: Any) -> SearchQuery:
        if user := kwargs.pop("user", None):
            self.user = user
        if reference := kwargs.pop("reference", ""):
            self.reference = reference
        if search_terms := kwargs.pop("search_terms", ""):
            self.search_terms = search_terms
        super().save(*args, **kwargs)
        return self

    def _hit_values(self, property_name: str) -> list[str | float]:
        """Extract list of property values from each hit in search results."""
        return [] if self.hits is None else [h[property_name] for h in self.hits]

    @property
    def max_score(self) -> float:
        """Max relevance score in the returned page."""
        if self.hits:
            return float(max(self._hit_values("score")))
        return 0.0

    @property
    def min_score(self) -> float:
        """Min relevance score in the returned page."""
        if self.hits:
            return float(min(self._hit_values("score")))
        return 0.0

    @property
    def object_ids(self) -> list[str]:
        """List of model ids extracted from hits."""
        return self._hit_values("id")  # type: ignore

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
        """Return True if the query includes highlights."""
        if not self.query:
            raise ValueError("Missing query attribute.")
        return "highlight" in self.query

    @property
    def has_fields(self) -> bool:
        """Return True if the query includes explicit fields."""
        if not self.query:
            raise ValueError("Missing query attribute.")
        return "fields" in self.query

    def search_rank_annotation(self, pk_field_name: str = "pk") -> Case | None:
        """Return SQL CASE statement used to annotate results with rank."""
        if not self.hits:
            return None
        case_when_rank = []
        for rank, hit in enumerate(self.hits, start=1):
            case_when_rank.append(When(**{pk_field_name: hit["id"]}, then=rank))
        return Case(*case_when_rank)

    def search_score_annotation(self, pk_field_name: str = "pk") -> Case | None:
        """Return SQL CASE statement used to annotate results with score."""
        if not self.hits:
            return None
        case_when_score = []
        for hit in self.hits:
            # if custom sorting has been applied, score is null
            score = None if hit["score"] is None else float(hit["score"])
            case_when_score.append(When(**{pk_field_name: hit["id"]}, then=score))
        return Case(*case_when_score)

    def get_hit(self, doc_id: str) -> dict:
        """
        Return the hit with a give document id.

        Raises KeyError if the id does not exist.

        """
        if hit := [h for h in self.hits if h["id"] == str(doc_id)]:
            return hit[0]
        raise KeyError("Document id not found in search results.")

    def get_doc_rank(self, doc_id: str) -> int:
        """Return the position of a document in the results."""
        return self.object_ids.index(str(doc_id))

    def get_doc_score(self, doc_id: str) -> float:
        """Return specific document score."""
        return self.get_hit(str(doc_id))["score"]

    def get_doc_highlights(self, doc_id: str) -> dict | None:
        """Return specific document highlights."""
        return self.get_hit(str(doc_id)).get("highlight")

    @classmethod
    def do_search(
        self,
        index: str,
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **search_kwargs: Any,
    ) -> SearchQuery:
        """Perform a search query and parse the response."""
        # if "from" has been passed in we need to convert it to "from_"
        # for the search method, ensuring that we don't overwrite
        # "from_" if it's been passed in correctly.
        from_ = search_kwargs.pop("from", DEFAULT_FROM)
        search_kwargs.setdefault("from_", from_)
        search_kwargs.setdefault("size", DEFAULT_PAGE_SIZE)
        search_kwargs.setdefault("_source", DEFAULT_INCLUDE_SOURCE)
        with stopwatch() as timer:
            response = client.search(index=index, query=query, **search_kwargs)
        parser = SearchResponseParser(response)
        # HACK: we want the "query" that we store to be the raw wire query, which
        # is a dict that contains query, aggs, highlights, from_, size, min_score,
        # etc.
        raw_query = {"query": copy.deepcopy(query)}
        raw_query.update(**search_kwargs)
        # now we need to replace "from_" with "from" for the stored
        # JSON as this is what gets sent over the wire.
        raw_query["from"] = raw_query.pop("from_")
        return SearchQuery(
            index=index,
            query=raw_query,
            query_type=SearchQuery.QueryType.SEARCH,
            hits=parser.hits,
            aggregations=parser.aggregations,
            total_hits=parser.total_hits,
            total_hits_relation=parser.total_hits_relation,
            executed_at=timer.started_at,
            duration=timer.elapsed,
            query_response=response,
        )

    @classmethod
    def do_count(
        self,
        index: str,
        query: dict,
        client: Elasticsearch = DEFAULT_CLIENT,
        **count_kwargs: Any,
    ) -> SearchQuery:
        """Perform a count query and parse the response."""
        with stopwatch() as timer:
            response = client.count(index=index, query=query, **count_kwargs)
        parser = CountResponseParser(response)
        return SearchQuery(
            index=index,
            query=query,
            query_type=SearchQuery.QueryType.COUNT,
            # hits=[],
            # aggregations={},
            total_hits=parser.total_hits,
            total_hits_relation=parser.total_hits_relation,
            executed_at=timer.started_at,
            duration=timer.elapsed,
        )


class SearchResponseParser:
    def __init__(self, response: ObjectApiResponse) -> None:
        self.body = response.body
        self._hits = self.body.get("hits", {})

    @property
    def raw_hits(self) -> list[dict]:
        return self._hits.get("hits", {})

    @property
    def hits(self) -> list[dict]:
        def _hit(hit: dict) -> dict:
            retval = {
                "id": hit["_id"],
                "index": hit["_index"],
                "score": hit["_score"],
            }
            if highlight := hit.get("highlight"):
                retval["highlight"] = highlight
            if fields := hit.get("fields"):
                retval["fields"] = fields
            return retval

        return [_hit(h) for h in self.raw_hits]

    @property
    def total(self) -> dict:
        return self._hits.get("total", {})

    @property
    def total_hits(self) -> int:
        return self.total.get("value", 0)

    @property
    def total_hits_relation(self) -> str:
        return self.total.get("relation", "")

    @property
    def aggregations(self) -> dict:
        return self.body.get("aggregations", {})


class CountResponseParser:
    def __init__(self, response: ObjectApiResponse) -> None:
        self.body = response.body

    @property
    def total_hits(self) -> int:
        return self.body.get("count", 0)

    @property
    def total_hits_relation(self) -> str:
        return str(SearchQuery.TotalHitsRelation.ACCURATE)
