"""search app models."""
import logging
import time

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.db.models.expressions import RawSQL
from django.utils.timezone import now as tz_now

from .db.fields import JSONField
from .settings import (
    get_client,
    get_model_indexes,
)

logger = logging.getLogger(__name__)


class SearchDocumentManagerMixin(object):

    """
    Model manager mixin that adds search document methods.

    There is one method in this class that must implemented -
    `get_search_queryset`. This must return a queryset that is the
    set of objects to be indexed. This queryset is then converted
    into a generator that emits the objects as JSON documents.

    """

    def get_search_queryset(self, index='_all'):
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

    def in_search_queryset(self, instance_id, index='_all'):
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
        return self.get_search_queryset(index=index).filter(id=instance_id).exists()

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
        score_sql = self._raw_sql([(h['id'], h['score']) for h in hits])
        rank_sql = self._raw_sql([(hits[i]['id'], i) for i in xrange(len(hits))])
        return (
            self.get_queryset()
            .filter(id__in=[h['id'] for h in hits])
            # add the query relevance score
            .annotate(search_score=RawSQL(score_sql, ()))
            # add the ordering number (0-based)
            .annotate(search_rank=RawSQL(rank_sql, ()))
            .order_by('search_rank')
        )

    def _raw_sql(self, values):
        """Prepare SQL statement consisting of a sequence of WHEN .. THEN statements."""
        when_ = lambda (x, y): "WHEN {} THEN {}".format(x, y)
        when_clauses = ' '.join([when_(h) for h in values])
        table_name = self.model._meta.db_table
        return "SELECT CASE {}.id {} ELSE 0 END".format(table_name, when_clauses)


class SearchDocumentMixin(object):

    """
    Mixin used by models that are indexed for ES.

    This mixin defines the interface exposed by models that
    are indexed ready for ES. The only method that needs
    implementing is `as_search_document`.

    """

    @property
    def search_indexes(self):
        """Return the list of indexes for which this model is configured."""
        return get_model_indexes(self.__class__)

    @property
    def search_document_cache_key(self):
        """Key used for storing search docs in local cache."""
        return 'elasticsearch_django:{}.{}.{}'.format(
            self._meta.app_label,
            self._meta.model_name,
            self.id
        )

    @property
    def search_doc_type(self):
        """Return the doc_type used for the model."""
        return self._meta.model_name

    def as_search_document(self, index='_all'):
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
            "{} does not implement 'get_search_document'.".format(self.__class__.__name__)
        )

    def as_search_action(self, index, action):
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
        assert action in ('index', 'update', 'delete'), ("Action must be 'index', 'update' or 'delete'.")  # noqa

        document = {
            '_index': index,
            '_type': self.search_doc_type,
            '_op_type': action,
            '_id': self.id,
        }

        if action == 'index':
            document['_source'] = self.as_search_document(index)
        elif action == 'update':
            document['doc'] = self.as_search_document(index)
        return document

    def fetch_search_document(self, index):
        """Fetch the object's document from a search index by id."""
        assert self.id, ("Object must have a primary key before being indexed.")
        client = get_client()
        return client.get(
            index=index,
            doc_type=self.search_doc_type,
            id=self.id
        )

    def update_search_index(self, action, index='_all', force=False):
        """
        Update the object in a remote index.

        This method is used to run index, update and delete actions on
        the index. We have a single method rather than individual methods
        in order to preserve the semantics of what we are doing. Irrespective
        of whether we are creating a new document, or deleting an existing
        document, from the point of view of the client we are updating the
        state of the remote search index.

        Before attempting to update the index, this method will check to see
        if the object is in the search queryset to determine whether it should
        be indexed at all.

        Args:
            action: string ['index' | 'update' | 'delete'] - the action to
                take - resolves to a POST, PUT, DELETE action

        Kwargs:
            index: string, the name of the index to update. Defaults to '_all',
                which is a reserved ES term meaning all indexes. In this case we
                use the config to look up all configured indexes for the model.
            force: bool, if True then ignore caching and force the update. Defaults
                to False.

        NB In reality we only support 'index' and 'delete' - 'update' is really
        a PATCH operation, updating partial documents in the search index - and
        we don't currently support this - we only ever update the entire document.

        Returns the HTTP response.

        """
        assert action in ('index', 'update', 'delete'), ("Action must be 'index', 'update' or 'delete'.")  # noqa
        assert self.id, ("Object must have a primary key before being indexed.")

        if not self._default_manager.in_search_queryset(self.id, index=index):
            logger.debug(
                "%r is not in the source queryset for '%s', aborting update.",
                self, index
            )
            return None

        if action == 'update':
            logger.warn(
                "'update' action is unsupported - switching to 'index' instead."
            )
            action = 'index'

        # use all configured indexes if none was passed in, else whatever we were given
        indexes = self.search_indexes if index == '_all' else [index]
        responses = []
        for i in indexes:
            responses.append(self._do_search_action(i, action, force=force))
        return responses

    def _do_search_action(self, index, action, force=False):
        """
        Call the relevant api function.

        This is where the API itself is used (for single document actions),
        but it shouldn't be used directly - the public method is `update_search_index`.

        Args:
            index: string, the name of the index to update.
            action: string, must be either 'index' or 'delete'.
            force: bool, if True then ignore cache and force the update

        Returns the HTTP response from the API call.

        NB this contains one of the core assumptions - that the model name is
        used as the search index document type name.

        """
        assert self.id, ("Object must have a primary key before being indexed.")
        assert action in ('index', 'delete'), (
            "Search action '{}' is invalid; must be 'index' or 'delete'.".format(action)
        )
        client = get_client()
        cache_key = self.search_document_cache_key
        if action == 'index':
            # if the locally cached search doc is the same as the new one,
            # then don't bother pushing to ES.
            new_doc = self.as_search_document(index)
            if not force:
                cached_doc = cache.get(cache_key)
                if new_doc == cached_doc:
                    logger.debug("Search document for %r is unchanged, ignoring update.", self)
                    return []
            cache.set(cache_key, new_doc, timeout=60)  # TODO: remove hard-coded timeout
            return client.index(
                index=index,
                doc_type=self.search_doc_type,
                body=new_doc,
                id=self.id
            )

        if action == 'delete':
            cache.delete(cache_key)
            return client.delete(
                index=index,
                doc_type=self.search_doc_type,
                id=self.id
            )


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

    user = models.ForeignKey(
        User,
        related_name='search_queries',
        blank=True, null=True,
        help_text="The user who made the search query (nullable)."
    )
    index = models.CharField(
        max_length=100,
        default='_all',
        help_text="The name of the ElasticSearch index(es) being queried."
    )
    query = JSONField(
        help_text="The raw ElasticSearch DSL query."
    )
    hits = JSONField(
        help_text="The list of meta info for each of the query matches returned."
    )
    total_hits = models.IntegerField(
        default=0,
        help_text="Total number of matches found for the query (!= the hits returned)."
    )
    reference = models.CharField(
        max_length=100,
        default='',
        blank=True,
        help_text="Custom reference used to identify and group related searches."
    )
    executed_at = models.DateTimeField(
        help_text="When the search was executed - set via execute() method."
    )
    duration = models.FloatField(
        help_text="Time taken to execute the search itself, in seconds."
    )

    class Meta:
        app_label = 'elasticsearch_django'
        verbose_name = "Search query"
        verbose_name_plural = "Search queries"

    def __unicode__(self):
        return (
            u"Query (id=%s) run against index '%s'" % (
                self.id, self.index
            )
        )

    def __repr__(self):
        return (
            u"<QueryLog id=%s user=%s index='%s' total_hits=%i >" % (
                self.id, self.user, self.index, self.total_hits
            )
        )

    @classmethod
    def execute(cls, search, user=None, reference=None, save=True):
        """
        Create a new SearchQuery instance and execute a search against ES.

        Args:
            search: elasticsearch.search.Search object, that internally contains
                the connection and query; this is the query that is executed. All
                we are doing is logging the input and parsing the output.
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
        duration = time.time() - start
        log = SearchQuery(
            user=user,
            index=', '.join(search._index or ['_all'])[:100],  # field length restriction
            query=search.to_dict(),
            hits=[h.meta.to_dict() for h in response.hits],
            total_hits=response.hits.total,
            reference=reference or '',
            executed_at=tz_now(),
            duration=duration
        )
        return log.save() if save else log

    def save(self, **kwargs):
        """Save and return the object (for chainging)."""
        super(SearchQuery, self).save(**kwargs)
        return self

    def _extract_set(self, _property):
        return [] if self.hits is None else (
            list(set([h[_property] for h in self.hits]))
        )

    @property
    def doc_types(self):
        """List of doc_types extracted from hits."""
        return self._extract_set('doc_type')

    @property
    def max_score(self):
        """The max relevance score in the returned page."""
        return max(self._extract_set('score') or [0])

    @property
    def min_score(self):
        """The min relevance score in the returned page."""
        return min(self._extract_set('score') or [0])

    @property
    def object_ids(self):
        """List of model ids extracted from hits."""
        return self._extract_set('id')

    @property
    def page_slice(self):
        """Return the query from:size tuple (0-based)."""
        return None if self.query is None else (
            self.query.get('from', 0),
            self.query.get('size', 10)
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
