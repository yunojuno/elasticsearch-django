import django.dispatch

# signal fired just before calling model.index_search_document
pre_index = django.dispatch.Signal()

# signal fired just before calling model.update_search_document
pre_update = django.dispatch.Signal()

# signal fired just before calling model.delete_search_document
pre_delete = django.dispatch.Signal()
