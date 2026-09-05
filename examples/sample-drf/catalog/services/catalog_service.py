"""Read and write operations over the bibliographic catalog.

Views never touch the ORM directly; they go through this service so the
query shapes stay in one place.
"""
from catalog.models import COPY_STATUS_AVAILABLE, Author, Book, Copy


class CatalogService:
    """Coordinates catalog queries and copy bookkeeping."""

    def list_books(self, search=None):
        """Return every title, optionally narrowed by a free-text search."""
        queryset = Book.objects.select_related("author")
        if search:
            queryset = queryset.filter(title__icontains=search)
        return queryset

    def get_book(self, book_id):
        """Return a single title by primary key."""
        return Book.objects.select_related("author").get(pk=book_id)

    def list_authors(self):
        """Return every author known to the catalog."""
        return Author.objects.all()

    def available_copies(self, book):
        """Return the lendable copies of a title."""
        return book.available_copies()

    def count_available_copies(self, book):
        """Return how many copies of a title are lendable right now."""
        return self.available_copies(book).count()

    def first_available_copy(self, book):
        """Return the copy that should be handed over next, if any."""
        return self.available_copies(book).first()

    def register_copy(self, book, barcode):
        """Add a new physical copy of a title to the shelves."""
        return Copy.objects.create(
            book=book, barcode=barcode, status=COPY_STATUS_AVAILABLE
        )

    def withdraw_copy(self, copy):
        """Take a damaged or lost copy out of circulation."""
        return copy.withdraw()
