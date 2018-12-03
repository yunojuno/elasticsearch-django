from django.contrib.auth.models import User
import factory

from .models import Book


class UserFactory(factory.Factory):

    class Meta:
        model = User

    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.LazyAttribute(lambda obj: f"{obj.first_name}.{obj.last_name}@example.com")
    username = factory.LazyAttribute(lambda obj: f"{obj.first_name}_{obj.last_name}")


class BookFactory(factory.Factory):

    class Meta:
        model = Book
