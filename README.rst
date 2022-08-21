**This project now requires Python 3.8+ and Django 3.2+.
For previous versions please refer to the relevant tag or branch.**

Elasticsearch for Django
========================

This is a lightweight Django app for people who are using Elasticsearch with Django, and want to manage their indexes.

**NB the master branch is now based on Elasticsearch 7/8. If you are using older versions, please switch to the relevant branch (released on PyPI as 2.x, 5.x, 6.x)**

----

Search Index Lifecycle
----------------------

The basic lifecycle for a search index is simple:

1. Create an index
2. Post documents to the index
3. Query the index

Relating this to our use of search within a Django project it looks like this:

1. Create mapping file for a named index
2. Add index configuration to Django settings
3. Map models to document types in the index
4. Post document representation of objects to the index
5. Update the index when an object is updated
6. Remove the document when an object is deleted
7. Query the index
8. Convert search results into a QuerySet (preserving relevance)

----

Django Implementation
=====================

This section shows how to set up Django to recognise ES indexes, and the models that should appear in an index. From this setup you should be able to run the management commands that will create and populate each index, and keep the indexes in sync with the database.

Create index mapping file
-------------------------

The prerequisite to configuring Django to work with an index is having the mapping for the index available. This is a bit chicken-and-egg, but the underlying assumption is that you are capable of creating the index mappings outside of Django itself, as raw JSON - e.g. using the Chrome extension `Sense <https://chrome.google.com/webstore/detail/sense-beta/lhjgkmllcaadmopgmanpapmpjgmfcfig?hl=en>`_, or the API tool `Paw <https://paw.cloud/>`_.
(The easiest way to spoof this is to POST a JSON document representing your document type at URL on your ES instance (``POST http://ELASTICSEARCH_URL/{{index_name}}``) and then retrieving the auto-magic mapping that ES created via ``GET http://ELASTICSEARCH_URL/{{index_name}}/_mapping``.)

Once you have the JSON mapping, you should save it in the root of the Django project as ``search/mappings/{{index_name}}.json``.

Configure Django settings
-------------------------

The Django settings for search are contained in a dictionary called ``SEARCH_SETTINGS``, which should be in the main ``django.conf.settings`` file. The dictionary has three root nodes, ``connections``, ``indexes`` and ``settings``. Below is an example:

.. code:: python

    SEARCH_SETTINGS = {
        'connections': {
            'default': getenv('ELASTICSEARCH_URL'),
        },
        'indexes': {
            'blog': {
                'models': [
                    'website.BlogPost',
                ]
            }
        },
        'settings': {
            # batch size for ES bulk api operations
            'chunk_size': 500,
            # default page size for search results
            'page_size': 25,
            # set to True to connect post_save/delete signals
            'auto_sync': True,
            # List of models which will never auto_sync even if auto_sync is True
            'never_auto_sync': [],
            # if true, then indexes must have mapping files
            'strict_validation': False
        }
    }

The ``connections`` node is (hopefully) self-explanatory - we support multiple connections, but in practice you should only need the one - 'default' connection. This is the URL used to connect to your ES instance. The ``settings`` node contains site-wide search settings. The ``indexes`` nodes is where we configure how Django and ES play together, and is where most of the work happens.

**Index settings**

Inside the index node we have a collection of named indexes - in this case just the single index called ``blog``. Inside each index we have a ``models`` key which contains a list of Django models that should appear in the index, denoted in ``app.ModelName`` format. You can have multiple models in an index, and a model can appear in multiple indexes. How models and indexes interact is described in the next section.

**Configuration Validation**

When the app boots up it validates the settings, which involves the following:

1. Do each of the indexes specified have a mapping file?
2. Do each of the models implement the required mixins?

Implement search document mixins
--------------------------------

So far we have configured Django to know the names of the indexes we want, and the models that we want to index. What it doesn't yet know is which objects to index, and how to convert an object to its search index document. This is done by implementing two separate mixins - ``SearchDocumentMixin`` and ``SearchDocumentManagerMixin``. The configuration validation routine will tell you if these are not implemented.

**SearchDocumentMixin**

This mixin is responsible for the seaerch index document format. We are indexing JSON representations of each object, and we have two methods on the mixin responsible for outputting the correct format - ``as_search_document`` and ``as_search_document_update``.

An aside on the mechanics of the ``auto_sync`` process, which is hooked up using Django's ``post_save`` and ``post_delete`` model signals. ES supports partial updates to documents that already exist, and we make a fundamental assumption about indexing models - that **if you pass the ``update_fields`` kwarg to a ``model.save`` method call, then you are performing a partial update**, and this will be propagated to ES as a partial update only.

To this end, we have two methods for generating the model's JSON representation - ``as_search_document``, which should return a dict that represents the entire object; and ``as_search_document_update``, which takes the ``update_fields`` kwarg. This method handler
two partial update 'strategies', defined in the ``SEARCH_SETTINGS``, 'full' and 'partial'. The
default 'full' strategy simply proxies the ``as_search_document`` method - i.e. partial updates
are treated as a full document update. The 'partial' strategy is more intelligent - it will
map the update_fields specified to the field names defined in the index mapping files. If a
field name is passed into the save method but is not in the mapping file, it is ignored. In
addition, if the underlying Django model field is a related object, a ``ValueError`` will be
raised, as we cannot serialize this automatically. In this scenario, you will need to
override the method in your subclass - see the code for more details.

To better understand this, let us say that we have a model (``MyModel``) that is configured to be included in an index called ``myindex``. If we save an object, without passing ``update_fields``, then this is considered a full document update, which triggers the object's ``index_search_document`` method:

.. code:: python

    obj = MyModel.objects.first()
    obj.save()
    ...
    # AUTO_SYNC=true will trigger a re-index of the complete object document:
    obj.index_search_document(index='myindex')

However, if we only want to update a single field (say the ``timestamp``), and we pass this in to the save method, then this will trigger the ``update_search_document`` method, passing in the names of the fields that we want updated.

.. code:: python

    # save a single field on the object
    obj.save(update_fields=['timestamp'])
    ...
    # AUTO_SYNC=true will trigger a partial update of the object document
    obj.update_search_document(index, update_fields=['timestamp'])

We pass the name of the index being updated as the first arg, as objects may have different representations in different indexes:

.. code:: python

    def as_search_document(self, index):
        return {'name': "foo"} if index == 'foo' else {'name': "bar"}

In the case of the second method, the simplest possible implementation would be a dictionary containing the names of the fields being updated and their new values, and this is the default
implementation. If the fields passed in are simple fields (numbers, dates, strings, etc.) then
a simple ``{'field_name': getattr(obj, field_name}`` is returned. However, if the field name
relates to a complex object (e.g. a related object) then this method will raise an ``InvalidUpdateFields`` exception. In this scenario you should override the default implementationwith one of your own.

.. code:: python

    def as_search_document_update(self, index, update_fields):
        if 'user' in update_fields:
            # remove so that it won't raise a ValueError
            update_fields.remove('user')
            doc = super().as_search_document_update(index, update_fields)
            doc['user'] = self.user.get_full_name()
            return doc
        return super().as_search_document_update(index, update_fields)

The reason we have split out the update from the full-document index comes from a real problem that we ourselves suffered. The full object representation that we were using was quite DB intensive - we were storing properties of the model that required walking the ORM tree. However, because we were also touching the objects (see below) to record activity timestamps, we ended up flooding the database with queries simply to update a single field in the output document. Partial updates solves this issue:

.. code:: python

    def touch(self):
        self.timestamp = now()
        self.save(update_fields=['timestamp'])

    def as_search_document_update(self, index, update_fields):
        if list(update_fields) == ['timestamp']:
            # only propagate changes if it's +1hr since the last timestamp change
            if now() - self.timestamp < timedelta(hours=1):
                return {}
            else:
                return {'timestamp': self.timestamp}
        ....

**Processing updates async**

If you are generating a lot of index updates you may want to run them async (via some kind
of queueing mechanism). There is no built-in method to do this, given the range of queueing
libraries and patterns available, however it is possible using the ``pre_index``, ``pre_update``
and ``pre_delete`` signals. In this case, you should also turn off ``AUTO_SYNC`` (as this will
run the updates synchronously), and process the updates yourself. The signals pass in the kwargs
required by the relevant model methods, as well as the ``instance`` involved:

.. code:: python

    # ensure that SEARCH_AUTO_SYNC=False

    from django.dispatch import receiver
    import django_rq
    from elasticsearch_django.signals import (
        pre_index,
        pre_update,
        pre_delete
    )

    queue = django_rq.get_queue("elasticsearch")


    @receiver(pre_index, dispatch_uid="async_index_document")
    def index_search_document_async(sender, **kwargs):
        """Queue up search index document update via RQ."""
        instance = kwargs.pop("instance")
        queue.enqueue(
            instance.update_search_document,
            index=kwargs.pop("index"),
        )


    @receiver(pre_update, dispatch_uid="async_update_document")
    def update_search_document_async(sender, **kwargs):
        """Queue up search index document update via RQ."""
        instance = kwargs.pop("instance")
        queue.enqueue(
            instance.index_search_document,
            index=kwargs.pop("index"),
            update_fields=kwargs.pop("update_fields"),
        )


    @receiver(pre_delete, dispatch_uid="async_delete_document")
    def delete_search_document_async(sender, **kwargs):
        """Queue up search index document deletion via RQ."""
        instance = kwargs.pop("instance")
        queue.enqueue(
            instance.delete_search_document,
            index=kwargs.pop("index"),
        )


**SearchDocumentManagerMixin**

This mixin must be implemented by the model's default manager (``objects``). It also requires a single method implementation - ``get_search_queryset()`` - which returns a queryset of objects that are to be indexed. This can also use the ``index`` kwarg to provide different sets of objects to different indexes.

.. code:: python

    def get_search_queryset(self, index='_all'):
        return self.get_queryset().filter(foo='bar')

We now have the bare bones of our search implementation. We can now use the included management commands to create and populate our search index:

.. code:: bash

    # create the index 'foo' from the 'foo.json' mapping file
    $ ./manage.py create_search_index foo

    # populate foo with all the relevant objects
    $ ./manage.py update_search_index foo

The next step is to ensure that our models stay in sync with the index.

Add model signal handlers to update index
-----------------------------------------

If the setting ``auto_sync`` is True, then on ``AppConfig.ready`` each model configured for use in an index has its ``post_save`` and ``post_delete`` signals connected. This means that they will be kept in sync across all indexes that they appear in whenever the relevant model method is called. (There is some very basic caching to prevent too many updates - the object document is cached for one minute, and if there is no change in the document the index update is ignored.)

There is a **VERY IMPORTANT** caveat to the signal handling. It will **only** pick up on changes to the model itself, and not on related (``ForeignKey``, ``ManyToManyField``) model changes. If the search document is affected by such a change then you will need to implement additional signal handling yourself.

In addition to ``object.save()``, SeachDocumentMixin also provides the ``update_search_index(self, action, index='_all', update_fields=None, force=False)`` method. Action should be 'index', 'update' or 'delete'. The difference between 'index' and 'update' is that 'update' is a partial update that only changes the fields specified, rather than re-updating the entire document. If ``action`` is 'update' whilst ``update_fields`` is None, action will be changed to ``index``.

We now have documents in our search index, kept up to date with their Django counterparts. We are ready to start querying ES.

----

Search Queries (How to Search)
==============================

Running search queries
----------------------

The search itself is done using ``elasticsearch_dsl``, which provides a pythonic abstraction over the QueryDSL, but also allows you to use raw JSON if required:

.. code:: python

    from elasticsearch_django.settings import get_client
    from elasticsearch_dsl import Search

    # run a default match_all query
    search = Search(using=get_client())
    response = search.execute()

    # change the query using the python interface
    search = search.query("match", title="python")

    # change the query from the raw JSON
    search.update_from_dict({"query": {"match": {"title": "python"}}})

The response from ``execute`` is a ``Response`` object which wraps up the ES JSON response, but is still basically JSON.

**SearchQuery**

The ``elasticsearch_django.models.SearchQuery`` model wraps this functionality up and provides helper properties, as well as logging the query:

.. code:: python

    from elasticsearch_django.settings import get_client
    from elasticsearch_django.models import execute_search
    from elasticsearch_dsl import Search

    # run a default match_all query
    search = Search(using=get_client(), index='blog')
    sq = execute_search(search)
    # the raw response is stored on the return object,
    # but is not stored on the object in the database.
    print(sq.response)

Calling the ``execute_search`` function will execute the underlying search, log the query JSON, the number of hits, and the list of hit meta information for future analysis. The ``execute`` method also includes these additional kwargs:

* ``user`` - the user who is making the query, useful for logging
* ``search_terms`` - the search query supplied by the user (as opposed to the DSL) - not used by ES, but stored in the logs
* ``reference`` - a free text reference field - used for grouping searches together - could be session id.
* ``save`` - by default the SearchQuery created will be saved, but passing in False will prevent this.

In conclusion - running a search against an index means getting to grips with the ``elasticsearch_dsl`` library, and when playing with search in the shell there is no need to use anything else. However, in production, searches should always be executed using the ``SearchQuery.execute`` method.

Converting search hits into Django objects
------------------------------------------

Running a search against an index will return a page of results, each containing the ``_source`` attribute which is the search document itself (as created by the ``SearchDocumentMixin.as_search_document`` method), together with meta info about the result - most significantly the relevance **score**, which is the magic value used for ranking (ordering) results. However, the search document probably doesn't contain all the of the information that you need to display the result, so what you really need is a standard Django QuerySet, containing the objects in the search results, but maintaining the order. This means injecting the ES score into the queryset, and then using it for ordering. There is a method on the ``SearchDocumentManagerMixin`` called ``from_search_query`` which will do this for you. It uses raw SQL to add the score as an annotation to each object in the queryset. (It also adds the 'rank' - so that even if the score is identical for all hits, the ordering is preserved.)

.. code:: python

    from models import BlogPost

    # run a default match_all query
    search = Search(using=get_client(), index='blog')
    sq = execute_search(search)
    for obj in BlogPost.objects.from_search_query(sq):
        print obj.search_score, obj.search_rank
