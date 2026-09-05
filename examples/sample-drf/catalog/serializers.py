"""DRF serializers for the catalog resources."""
from rest_framework import serializers

from catalog.models import Author, Book, Copy
from catalog.services.catalog_service import CatalogService


class AuthorSerializer(serializers.ModelSerializer):
    """Serialize an author together with a display-ready name."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ["id", "given_name", "family_name", "birth_year", "display_name"]

    def get_display_name(self, author):
        """Return the catalog-card form of the author name."""
        return author.display_name()


class CopySerializer(serializers.ModelSerializer):
    """Serialize a single physical copy."""

    class Meta:
        model = Copy
        fields = ["id", "barcode", "status", "acquired_on"]


class BookSerializer(serializers.ModelSerializer):
    """Serialize a title with its author and live availability."""

    author = AuthorSerializer(read_only=True)
    available_copies = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id",
            "isbn",
            "title",
            "subtitle",
            "author",
            "published_year",
            "shelf_code",
            "available_copies",
        ]

    def get_available_copies(self, book):
        """Return how many copies of this title can be lent right now."""
        service = CatalogService()
        return service.count_available_copies(book)
