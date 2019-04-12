from django.contrib import admin

try:
    from django.urls import re_path, include
except ImportError:
    from django.conf.urls import url as re_path, include

admin.autodiscover()

urlpatterns = [re_path(r"^admin/", admin.site.urls)]
