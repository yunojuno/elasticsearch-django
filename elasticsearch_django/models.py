import logging
import time
import warnings

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.expressions import RawSQL
from django.db.models.fields import CharField
from django.utils.timezone import now as tz_now

from .settings import (
    get_client,
    get_setting,
    get_model_indexes,
    get_model_index_properties,
)

logger = logging.getLogger(__name__)

UPDATE_STRATEGY_FULL = "full"
UPDATE_STRATEGY_PARTIAL = "partial"
UPDATE_STRATEGY = get_setting("update_strategy", UPDATE_STRATEGY_FULL)


class SearchDocumentManagerMixin(object):

    """
    Model manager mixin that adds search document methods.

    There is one method in this class that must implemented -
    `get_search_queryset`. This must return a queryset that is the
    set of objects to be indexed. This queryset is then converted
    into a generator that emits the objects as JSON documents.

    """

    def get_search_queryset(self, index="_all"):
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

    def in_search_queryset(self, instance_id, index="_all"):
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

    def from_search_query(self, search_query):
        """
        Return queryset of objects from SearchQuery.results, **in order**.

        EXPERIMENTAL: this will only work with results from a single index,
        with a single doc_type - as we are returning a single QuerySet.

        This method takes the hits JSON and converts that into a queryset
        of all the relevant objects. The key part of this is the ordering -
        the order in which search results are returned is based on relevance,
        something that only ES can calculate, and that cannot be replicated
        in the database.

        It does this by adding custom SQL which annotates each record with
        the score from the search 'hit'. This is brittle, caveat emptor.

        The RawSQL clause is in the form:

            SELECT CASE {{model}}.id WHEN {{id}} THEN {{score}} END

        The "WHEN x THEN y" is repeated for every hit. The resulting SQL, in
        full is like this:

            SELECT "freelancer_freelancerprofile"."id",
                (SELECT CASE freelancer_freelancerprofile.id
                    WHEN 25 THEN 1.0
                    WHEN 26 THEN 1.0
                    [...]
                    ELSE 0
                END) AS "search_score"
            FROM "freelancer_freelancerprofile"
            WHERE "freelancer_freelancerprofile"."id" IN (25, 26, [...])
            ORDER BY "search_score" DESC

        It should be very fast, as there is no table lookup, but there is an
        assumption at the heart of this, which is that the search query doesn't
        contain the entire database - i.e. that it has been paged. (ES itself
        caps the results at 10,000.)

        """
        hits = search_query.hits
        score_sql = self._raw_sql([(h["id"], h["score"] or 0) for h in hits])
        rank_sql = self._raw_sql([(hits[i]["id"], i) for i in range(len(hits))])
        return (
            self.get_queryset()
            .filter(pk__in=[h["id"] for h in hits])
            # add the query relevance score
            .annotate(search_score=RawSQL(score_sql, ()))
            # add the ordering number (0-based)
            .annotate(search_rank=RawSQL(rank_sql, ()))
            .order_by("search_rank")
        )

    def _when(self, x, y):
        return "WHEN {} THEN {}".format(x, y)

    def _raw_sql(self, values):
        """Prepare SQL statement consisting of a sequence of WHEN .. THEN statements."""
        if isinstance(self.model._meta.pk, CharField):
            when_clauses = " ".join(
                [self._when("'{}'".format(x), y) for (x, y) in values]
            )
        else:
            when_clauses = " ".join([self._when(x, y) for (x, y) in values])
        table_name = self.model._meta.db_table
        primary_key = self.model._meta.pk.column
        return 'SELECT CASE {}."{}" {} ELSE 0 END'.format(
            table_name, primary_key, when_clauses
        )


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
    def search_indexes(self):
        """Return the list of indexes for which this model is configured."""
        return get_model_indexes(self.__class__)

    @property
    def search_document_cache_key(self):
        """Key used for storing search docs in local cache."""
        return "elasticsearch_django:{}.{}.{}".format(
            self._meta.app_label, self._meta.model_name, self.pk
        )

    @property
    def search_doc_type(self):
        """Return the doc_type used for the model."""
        return self._meta.model_name

    def as_search_document(self, *, index):
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

    def _is_field_serializable(self, field_name):
        """Return True if the field can be serialized into a JSON doc."""
        return (
            self._meta.get_field(field_name).get_internal_type()
            in self.SIMPLE_UPDATE_FIELD_TYPES
        )

    def clean_update_fields(self, index, update_fields):
        """
        Clean the list of update_fields based on the index being updated.\

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
                    "'%s' cannot be automatically serialized into a search document property. Please override as_search_document_update.",
                    f,
                )
        return clean_fields

    def as_search_document_update(self, *, index, update_fields):
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

    def as_search_action(self, *, index, action):
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
            "_type": self.search_doc_type,
            "_op_type": action,
            "_id": self.pk,
        }

        if action == "index":
            document["_source"] = self.as_search_document(index=index)
        elif action == "update":
            document["doc"] = self.as_search_document(index=index)
        return document

    def fetch_search_document(self, *, index):
        """Fetch the object's document from a search index by id."""
        assert self.pk, "Object must have a primary key before being indexed."
        client = get_client()
        return client.get(index=index, doc_type=self.search_doc_type, id=self.pk)

    def index_search_document(self, *, index):
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
            return []
        cache.set(cache_key, new_doc, timeout=get_setting("cache_expiry", 60))
        get_client().index(
            index=index, doc_type=self.search_doc_type, body=new_doc, id=self.pk
        )

    def update_search_document(self, *, index, update_fields):
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
        see: https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html

        """
        doc = self.as_search_document_update(index=index, update_fields=update_fields)
        if not doc:
            logger.debug("Ignoring object update as document is empty.")
            return

        get_client().update(
            index=index, doc_type=self.search_doc_type, body={"doc": doc}, id=self.pk
        )

    def delete_search_document(self, *, index):
        """Delete document from named index."""
        cache.delete(self.search_document_cache_key)
        get_client().delete(index=index, doc_type=self.search_doc_type, id=self.pk)


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

    # whether this is a search query (returns results), or a count API
    # query (returns the number of results, but no detail),
    QUERY_TYPE_SEARCH = "SEARCH"
    QUERY_TYPE_COUNT = "COUNT"
    QUERY_TYPE_CHOICES = (
        (QUERY_TYPE_SEARCH, "Search results"),
        (QUERY_TYPE_COUNT, "Count only"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="search_queries",
        blank=True,
        null=True,
        help_text="The user who made the search query (nullable).",
        on_delete=models.SET_NULL,
    )
    index = models.CharField(
        max_length=100,
        default="_all",
        help_text="The name of the ElasticSearch index(es) being queried.",
    )
    # The query property contains the raw DSL query, which can be arbitrarily complex - there
    # is no one way of mapping input text to the query itself. However, it's often helpful to
    # have the terms that the user themselves typed easily accessible without having to parse
    # JSON.
    search_terms = models.CharField(
        max_length=400,
        default="",
        blank=True,
        help_text="Free text search terms used in the query, stored for easy reference.",
    )
    query = JSONField(
        help_text="The raw ElasticSearch DSL query.", encoder=DjangoJSONEncoder
    )
    query_type = CharField(
        help_text="Does this query return results, or just the hit count?",
        choices=QUERY_TYPE_CHOICES,
        default=QUERY_TYPE_SEARCH,
        max_length=10,
    )
    hits = JSONField(
        help_text="The list of meta info for each of the query matches returned.",
        encoder=DjangoJSONEncoder,
    )
    total_hits = models.IntegerField(
        default=0,
        help_text="Total number of matches found for the query (!= the hits returned).",
    )
    reference = models.CharField(
        max_length=100,
        default="",
        blank=True,
        help_text="Custom reference used to identify and group related searches.",
    )
    executed_at = models.DateTimeField(
        help_text="When the search was executed - set via execute() method."
    )
    duration = models.FloatField(
        help_text="Time taken to execute the search itself, in seconds."
    )

    class Meta:
        app_label = "elasticsearch_django"
        verbose_name = "Search query"
        verbose_name_plural = "Search queries"

    def __str__(self):
        return "Query (id={}) run against index '{}'".format(self.pk, self.index)

    def __repr__(self):
        return "<SearchQuery id={} user={} index='{}' total_hits={} >".format(
            self.pk, self.user, self.index, self.total_hits
        )

    @classmethod
    def execute(cls, search, search_terms="", user=None, reference=None, save=True):
        """Create a new SearchQuery instance and execute a search against ES."""
        warnings.warn(
            "Pending deprecation - please use `execute_search` function instead.",
            PendingDeprecationWarning,
        )
        return execute_search(
            search, search_terms=search_terms, user=user, reference=reference, save=save
        )

    def save(self, **kwargs):
        """Save and return the object (for chaining)."""
        if self.search_terms is None:
            self.search_terms = ""
        super().save(**kwargs)
        return self

    def _extract_set(self, _property):
        return (
            [] if self.hits is None else (list(set([h[_property] for h in self.hits])))
        )

    @property
    def doc_types(self):
        """List of doc_types extracted from hits."""
        return self._extract_set("doc_type")

    @property
    def max_score(self):
        """The max relevance score in the returned page."""
        return max(self._extract_set("score") or [0])

    @property
    def min_score(self):
        """The min relevance score in the returned page."""
        return min(self._extract_set("score") or [0])

    @property
    def object_ids(self):
        """List of model ids extracted from hits."""
        return self._extract_set("id")

    @property
    def page_slice(self):
        """Return the query from:size tuple (0-based)."""
        return (
            None
            if self.query is None
            else (self.query.get("from", 0), self.query.get("size", 10))
        )

    @property
    def page_from(self):
        """1-based index of the first hit in the returned page."""
        return 0 if self.page_size == 0 else self.page_slice[0] + 1

    @property
    def page_to(self):
        """1-based index of the last hit in the returned page."""
        return 0 if self.page_size == 0 else self.page_from + self.page_size - 1

    @property
    def page_size(self):
        """The number of hits returned in this specific page."""
        return 0 if self.hits is None else len(self.hits)


def execute_search(
    search,
    search_terms="",
    user=None,
    reference="",
    save=True,
    query_type=SearchQuery.QUERY_TYPE_SEARCH,
):
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
        query_type: string, used to determine whether to run a search query or
            a count query (returns hit count, but no results).

    """
    start = time.time()
    if query_type == SearchQuery.QUERY_TYPE_SEARCH:
        response = search.execute()
        hits = [h.meta.to_dict() for h in response.hits]
        total_hits = response.hits.total
    elif query_type == SearchQuery.QUERY_TYPE_COUNT:
        response = total_hits = search.count()
        hits = []
    else:
        raise ValueError(f"Invalid SearchQuery.query_type value: '{query_type}'")
    duration = time.time() - start
    search_query = SearchQuery(
        user=user,
        search_terms=search_terms,
        index=", ".join(search._index or ["_all"])[:100],  # field length restriction
        query=search.to_dict(),
        query_type=query_type,
        hits=hits,
        total_hits=total_hits,
        reference=reference or "",
        executed_at=tz_now(),
        duration=duration,
    )
    search_query.response = response
    return search_query.save() if save else search_query
