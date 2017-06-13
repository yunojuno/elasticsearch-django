.. image:: https://travis-ci.org/yunojuno/elasticsearch-django.svg?branch=master
    :target: https://travis-ci.org/yunojuno/elasticsearch-django

.. image:: https://badge.fury.io/py/elasticsearch_django.svg
    :target: https://badge.fury.io/py/elasticsearch_django

Elasticsearch for Django
========================

This is a lightweight Django app for people who are using Elasticsearch with Django, and want to manage their indexes.

**NB the master branch is now based on ES5.x. If you are using ES2.x, please switch to the ES2 branch (released on PyPI as 2.x)**

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

The prerequisite to configuring Django to work with an index is having the mapping for the index available. This is a bit chicken-and-egg, but the underlying assumption is the you are capable of creating the index mappings outside of Django itself, as raw JSON - e.g. using the Chrome extension `Sense <https://chrome.google.com/webstore/detail/sense-beta/lhjgkmllcaadmopgmanpapmpjgmfcfig?hl=en>`_, or the API tool `Paw <https://paw.cloud/>`_.
(The easiest way to spoof this is to POST a JSON document representing your document type at URL on your ES instance (``POST http://ELASTICSEARCH_URL/{{index_name}}``) and then retrieving the auto-magic mapping that ES created via ``GET http://ELASTICSEARCH_URL/{{index_name}}/_mapping``.)

Once you have the JSON mapping, you should save it as ``search/mappings/{{index_name}}.json``.

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
            # if true, then indexes must have mapping files
            'strict_validation': False
        }
    }

The ``connections`` node is (hopefully) self-explanatory - we support multiple connections, but in practice you should only need the one - 'default' connection. This is the URL used to connect to your ES instance. The ``setting`` node contains site-wide search settings. The ``indexes`` nodes is where we configure how Django and ES play together, and is where most of the work happens.

**Index settings**

Inside the index node we have a collection of named indexes - in this case just the single index called ``blog``. Inside each index we have a ``models`` key which contains a list of Django models that should appear in the index, denoted in ``app.ModelName`` format. You can have multiple models in an index, and a model can appear in multiple indexes. How models and indexes interact is described in the next section.

**Configuration Validation**

When the app boots up it validates the settings, which involves the following:

1. Do each of the indexes specified have a mapping file?
2. Do each of the models implement the required mixins

Implement search document mixins
--------------------------------

So far we have configure Django to know the names of the indexes we want, and the models that we want to index. What it doesn't yet know is which objects to index, and how to convert an object to its search index document. This is done by implementing two separate mixins - ``SearchDocumentMixin`` and ``SearchDocumentManagerMixin``. The configuration validation routine will tell you if these are not implemented.

**SearchDocumentMixin**

This mixin must be implemented by the model itself, and it requires a single method implementation - ``as_search_document()``. This should return a dict that is the index representation of the object; the ``index`` kwarg can be used to provide different representations for different indexes. By default this is ``_all`` which means that all indexes receive the same document for a given object.

.. code:: python

    def as_search_document(self, index='_all'):
        return {name: “foo”} if index == 'foo' else {name = “bar”}

**SearchDocumentManagerMixin**

This mixin must be implemented by the model's default manager (``objects``). It also requires a single method implementation - ``get_search_queryset()`` - which returns a queryset of objects that are to be indexed. This can also use the ``index`` kwarg to provide different sets of objects to different indexes.

.. code:: python

    def get_search_queryset(self, index):
        return self.get_queryset().filter(foo="bar")

We now have the bare bones of our search implementation. We can now use the included management commands to create and populate our search index:

.. code:: bash

    # create the index 'foo' from the 'foo.json' mapping file
    $ ./manage.py create_search_index foo

    # populate foo with all the relevant objects
    $ ./manage.py update_search_index foo

The next step is to ensure that our models stay in sync with the index.

Add model signal handlers to update index
-----------------------------------------

If the setting `auto_sync` is True, then on `AppConfig.ready` each model configured for use in an index has its `post_save` and `post_delete` signals connected. This means that they will be kept in sync across all indexes that they appear in whenever the relevant model method is called. (There is some very basic caching to prevent too many updates - the object document is cached for one minute, and if there is no change in the document the index update is ignored.)

There is a VERY IMPORTANT caveat to the signal handling. It will **only** pick on changes the the model itself, and not on related (`ForeignKey`, `ManyToManyField`) model changes. If the search document it affected by such a change then you will need to implement additional signal handling yourself.

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
    from elasticsearch_django.models import SearchQuery
    from elasticsearch_dsl import Search

    # run a default match_all query
    search = Search(using=get_client(), index='blog')
    sq = SearchQuery.execute(search)

Calling the ``SearchQuery.execute`` class method will execute the underlying search, log the query JSON, the number of hits, and the list of hit meta information for future analysis. The ``execute`` method also includes these additional kwargs:

* ``user`` - the user who is making the query, useful for logging
* ``reference`` - a free text reference field - used for grouping searches together - could be session id, or brief id.
*  ``save`` - by default the SearchQuery created will be saved, but passing in False will prevent this.

In conclusion - running a search against an index means getting to grips with the ``elasticsearch_dsl`` library, and when playing with search in the shell there is no need to use anything else. However, in production, searches should always be executed using the ``SearchQuery.execute`` method.

Converting search hits into Django objects
------------------------------------------

Running a search against an index will return a page of results, each containing the ``_source`` attribute which is the search document itself (as created by the ``SearchDocumentMixin.as_search_document`` method), together with meta info about the result - most significantly the relevance **score**, which is the magic value used for ranking (ordering) results. However, the search document probably doesn't contain all the of the information that you need to display the result, so what you really need is a standard Django QuerySet, containing the objects in the search results, but maintaining the order. This means injecting the ES score into the queryset, and then using it for ordering. There is a method on the ``SearchDocumentManagerMixin`` called ``from_search_query`` which will do this for you. It uses raw SQL to add the score as an annotation to each object in the queryset. (It also adds the 'rank' - so that even if the score is identical for all hits, the ordering is preserved.)

.. code:: python

    from models import BlogPost

    # run a default match_all query
    search = Search(using=get_client(), index='blog')
    sq = SearchQuery.execute(search)
    for obj in BlogPost.objects.from_search_query(sq):
        print obj.search_score, obj.search_rank
