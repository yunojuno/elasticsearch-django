import django.dispatch

# signal fired just before calling model.index_search_document
# providing_args=["instance", "index"]
pre_index = django.dispatch.Signal()

# signal fired just before calling model.update_search_document
# providing_args=["instance", "index", "update_fields"]
pre_update = django.dispatch.Signal()

# signal fired just before calling model.delete_search_document
# providing_args=["instance", "index"]
pre_delete = django.dispatch.Signal()
