"""Use case: put a member in the queue for a title.

A reservation only makes sense when no copy is on the shelf. If one is
available the handler says so and lets the caller start a loan instead.
"""
from datetime import date

from catalog.services.catalog_service import CatalogService
from lending.domain.policies import (
    is_within_reservation_limit,
    reservation_expiry,
    reservation_limit_for,
)
from lending.models import RESERVATION_STATE_OPEN, Reservation
from lending.services.loan_service import LoanService


class CopyStillAvailable(Exception):
    """Raised when a title is reserved although a copy could be lent now."""


class ReservationLimitReached(Exception):
    """Raised when a member already holds their maximum open reservations."""


class PlaceReservationHandler:
    """Places a reservation, or explains why it is not allowed."""

    def __init__(self, catalog=None, loans=None):
        self.catalog = catalog or CatalogService()
        self.loans = loans or LoanService()

    def count_open_reservations(self, member):
        """Return how many reservations this member is already waiting on."""
        return member.open_reservations().count()

    def remaining_slots(self, member):
        """Return how many further reservations the member's tier allows."""
        return reservation_limit_for(member.tier) - self.count_open_reservations(member)

    def can_place(self, member):
        """Return whether one more reservation fits inside the tier limit."""
        if member.suspended:
            return False
        return is_within_reservation_limit(
            self.count_open_reservations(member), member.tier
        )

    def handle(self, member_id, book, today=None):
        """Place the reservation and return the stored record."""
        reference = today or date.today()
        member = self.loans.get_member(member_id)
        if self.catalog.count_available_copies(book) > 0:
            raise CopyStillAvailable(book.isbn)
        if not self.can_place(member):
            raise ReservationLimitReached(member.card_number)
        return Reservation.objects.create(
            member=member,
            book=book,
            placed_on=reference,
            expires_on=reservation_expiry(reference),
            state=RESERVATION_STATE_OPEN,
        )
