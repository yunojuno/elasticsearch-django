import django.dispatch

# signal fired just before calling model.index_search_document
pre_index = django.dispatch.Signal(providing_args=["instance", "index"])

# signal fired just before calling model.update_search_document
pre_update = django.dispatch.Signal(
    providing_args=["instance", "index", "update_fields"]
)

# signal fired just before calling model.delete_search_document
pre_delete = django.dispatch.Signal(providing_args=["instance", "index"])
