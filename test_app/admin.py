from django.contrib import admin

from .models import Book


class BookAdmin(admin.ModelAdmin):

    list_fields = [
        'author',
        'title',
        'date_published',
        'price'
    ]
    fields = [
        'author',
        'title',
        'sample',
        'date_published',
        'price'
    ]

admin.site.register(Book, BookAdmin)
