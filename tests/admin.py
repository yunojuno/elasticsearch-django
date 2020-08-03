from django.contrib import admin

from .models import ExampleModel


class ExampleModelAdmin(admin.ModelAdmin):

    list_display = ("simple_field_1", "simple_field_2", "complex_field")


admin.site.register(ExampleModel, ExampleModelAdmin)
