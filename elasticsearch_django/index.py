import logging

from elasticsearch import helpers

from .settings import get_setting, get_index_mapping, get_index_models, get_client

logger = logging.getLogger(__name__)


def create_index(index):
    """Create an index and apply mapping if appropriate."""
    logger.info("Creating search index: '%s'", index)
    client = get_client()
    return client.indices.create(index=index, body=get_index_mapping(index))


def update_index(index):
    """Re-index every document in a named index."""
    logger.info("Updating search index: '%s'", index)
    client = get_client()
    responses = []
    for model in get_index_models(index):
        logger.info("Updating search index model: '%s'", model.search_doc_type)
        objects = model.objects.get_search_queryset(index).iterator()
        actions = bulk_actions(objects, index=index, action="index")
        response = helpers.bulk(client, actions, chunk_size=get_setting("chunk_size"))
        responses.append(response)
    return responses


def delete_index(index):
    """Delete index entirely (removes all documents and mapping)."""
    logger.info("Deleting search index: '%s'", index)
    client = get_client()
    return client.indices.delete(index=index)


def prune_index(index):
    """Remove all orphaned documents from an index.

    This function works by scanning the remote index, and in each returned
    batch of documents looking up whether they appear in the default index
    queryset. If they don't (they've been deleted, or no longer fit the qs
    filters) then they are deleted from the index. The deletion is done in
    one hit after the entire remote index has been scanned.

    The elasticsearch.helpers.scan function returns each document one at a
    time, so this function can swamp the database with SELECT requests.

    Please use sparingly.

    Returns a list of ids of all the objects deleted.

    """
    logger.info("Pruning missing objects from index '%s'", index)
    prunes = []
    responses = []
    client = get_client()
    for model in get_index_models(index):
        for hit in scan_index(index, model):
            obj = _prune_hit(hit, model)
            if obj:
                prunes.append(obj)
        logger.info(
            "Found %s objects of type '%s' for deletion from '%s'.",
            len(prunes),
            model,
            index,
        )
        if len(prunes) > 0:
            actions = bulk_actions(prunes, index, "delete")
            response = helpers.bulk(
                client, actions, chunk_size=get_setting("chunk_size")
            )
            responses.append(response)
    return responses


def _prune_hit(hit, model):
    """
    Check whether a document should be pruned.

    This method uses the SearchDocumentManagerMixin.in_search_queryset method
    to determine whether a 'hit' (search document) should be pruned from an index,
    and if so it returns the hit as a Django object(id=hit_id).

    Args:
        hit: dict object the represents a document as returned from the scan_index
            function. (Contains object id and index.)
        model: the Django model (not object) from which the document was derived.
            Used to get the correct model manager and bulk action.

    Returns:
        an object of type model, with id=hit_id. NB this is not the object
        itself, which by definition may not exist in the underlying database,
        but a temporary object with the document id - which is enough to create
        a 'delete' action.

    """
    hit_id = hit["_id"]
    hit_index = hit["_index"]
    if model.objects.in_search_queryset(hit_id, index=hit_index):
        logger.debug(
            "%s with id=%s exists in the '%s' index queryset.", model, hit_id, hit_index
        )
        return None
    else:
        logger.debug(
            "%s with id=%s does not exist in the '%s' index queryset and will be pruned.",
            model,
            hit_id,
            hit_index,
        )
        # we don't need the full obj for a delete action, just the id.
        # (the object itself may not even exist.)
        return model(pk=hit_id)


def scan_index(index, model):
    """
    Yield all documents of model type in an index.

    This function calls the elasticsearch.helpers.scan function,
    and yields all the documents in the index that match the doc_type
    produced by a specific Django model.

    Args:
        index: string, the name of the index to scan, must be a configured
            index as returned from settings.get_index_names.
        model: a Django model type, used to filter the the documents that
            are scanned.

    Yields each document of type model in index, one at a time.

    """
    # see https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-type-query.html
    query = {"query": {"type": {"value": model._meta.model_name}}}
    client = get_client()
    for hit in helpers.scan(client, index=index, query=query):
        yield hit


def bulk_actions(objects, index, action):
    """
    Yield bulk api 'actions' from a collection of objects.

    The output from this method can be fed in to the bulk
    api helpers - each document returned by get_documents
    is decorated with the appropriate bulk api op_type.

    Args:
        objects: iterable (queryset, list, ...) of SearchDocumentMixin
            objects. If the objects passed in is a generator, then this
                function will yield the results rather than returning them.
        index: string, the name of the index to target - the index name
            is embedded into the return value and is used by the bulk api.
        action: string ['index' | 'update' | 'delete'] - this decides
            how the final document is formatted.

    """
    assert (
        index != "_all"
    ), "index arg must be a valid index name. '_all' is a reserved term."
    logger.info("Creating bulk '%s' actions for '%s'", action, index)
    for obj in objects:
        try:
            logger.debug("Appending '%s' action for '%r'", action, obj)
            yield obj.as_search_action(index=index, action=action)
        except Exception:
            logger.exception("Unable to create search action for %s", obj)
