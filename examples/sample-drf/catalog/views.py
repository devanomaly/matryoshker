"""HTTP surface of the sample library system.

Views stay thin: they validate the request, delegate to an application
service or a lending handler, and serialize the result. Every branch of
the call graph below this layer lives in ``catalog.services`` or in the
``lending`` app.
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.serializers import AuthorSerializer, BookSerializer, CopySerializer
from catalog.services.catalog_service import CatalogService
from lending.handlers.place_reservation import PlaceReservationHandler
from lending.services.loan_service import LoanService


class BookViewSet(viewsets.ViewSet):
    """Browse titles and start a loan or a reservation on one."""

    serializer_class = BookSerializer

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.catalog = CatalogService()
        self.loans = LoanService()
        self.reservations = PlaceReservationHandler()

    def list(self, request):
        """Return the titles matching an optional ``search`` parameter."""
        books = self.catalog.list_books(search=request.query_params.get("search"))
        serializer = BookSerializer(books, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Return a single title."""
        book = self.catalog.get_book(pk)
        serializer = BookSerializer(book)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def copies(self, request, pk=None):
        """Return the lendable copies of a title."""
        book = self.catalog.get_book(pk)
        copies = self.catalog.available_copies(book)
        serializer = CopySerializer(copies, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def borrow(self, request, pk=None):
        """Check out the next available copy of a title to a member."""
        book = self.catalog.get_book(pk)
        copy = self.catalog.first_available_copy(book)
        if copy is None:
            return Response(
                {"detail": "No copy of this title is on the shelf."},
                status=status.HTTP_409_CONFLICT,
            )
        loan = self.loans.checkout(request.data.get("member_id"), copy)
        return Response({"loan_id": loan.pk}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reserve(self, request, pk=None):
        """Put a member in the queue for a title that is fully lent out."""
        book = self.catalog.get_book(pk)
        reservation = self.reservations.handle(request.data.get("member_id"), book)
        return Response(
            {"reservation_id": reservation.pk}, status=status.HTTP_201_CREATED
        )


class AuthorViewSet(viewsets.ViewSet):
    """Browse the authors credited in the catalog."""

    serializer_class = AuthorSerializer

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.catalog = CatalogService()

    def list(self, request):
        """Return every author."""
        authors = self.catalog.list_authors()
        serializer = AuthorSerializer(authors, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Return one author together with a title count."""
        authors = self.catalog.list_authors()
        author = authors.get(pk=pk)
        payload = AuthorSerializer(author).data
        payload["title_count"] = author.title_count()
        return Response(payload)


class HealthView(APIView):
    """Liveness probe mounted both at the root and under the app router."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Report that the process is up and the catalog is reachable."""
        catalog = CatalogService()
        return Response({"status": "ok", "titles": catalog.list_books().count()})
