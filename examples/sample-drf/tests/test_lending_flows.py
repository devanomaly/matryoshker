"""Tests for the lending services and handlers.

These exercise the collaboration between handlers, services and the
domain rules using hand-written stand-ins for the ORM objects. They
import the app modules, so running them needs Django on the path; the
fixture ships them for the shape of the call graph, not to be executed.
"""
import unittest
from datetime import date

from lending.domain.policies import TIER_BASIC, calculate_fine
from lending.handlers.place_reservation import (
    PlaceReservationHandler,
    ReservationLimitReached,
)
from lending.services.loan_service import LoanService
from lending.services.overdue_service import OverdueService
from lending.tasks.notify_overdue import build_notice, format_amount


class FakeQuery(list):
    """A list that answers the few queryset methods the code calls."""

    def count(self):
        return len(self)

    def first(self):
        return self[0] if self else None

    def exists(self):
        return bool(self)


class FakeMember:
    """Stand-in for ``lending.models.Member``."""

    def __init__(self, tier=TIER_BASIC, loans=0, reservations=0, suspended=False):
        self.pk = 1
        self.card_number = "M-0001"
        self.email = "member@example.org"
        self.tier = tier
        self.suspended = suspended
        self._loans = FakeQuery([object()] * loans)
        self._reservations = FakeQuery([object()] * reservations)

    def open_loans(self):
        return self._loans

    def open_reservations(self):
        return self._reservations


class FakeBook:
    """Stand-in for ``catalog.models.Book``."""

    def __init__(self, available=0):
        self.isbn = "978-0-000-00000-0"
        self.available = available

    def full_title(self):
        return "A Sample Title"


class FakeCatalog:
    """Stand-in for ``catalog.services.catalog_service.CatalogService``."""

    def count_available_copies(self, book):
        return book.available


class FakeLoans:
    """Stand-in for ``LoanService`` that resolves members from memory."""

    def __init__(self, member):
        self.member = member

    def get_member(self, member_id):
        return self.member


class PlaceReservationTests(unittest.TestCase):
    """Cover the reservation guard rails."""

    def test_limit_is_reported_from_the_tier(self):
        member = FakeMember(reservations=2)
        handler = PlaceReservationHandler(
            catalog=FakeCatalog(), loans=FakeLoans(member)
        )
        self.assertFalse(handler.can_place(member))
        self.assertEqual(handler.remaining_slots(member), 0)

    def test_suspended_member_cannot_reserve(self):
        member = FakeMember(suspended=True)
        handler = PlaceReservationHandler(
            catalog=FakeCatalog(), loans=FakeLoans(member)
        )
        self.assertFalse(handler.can_place(member))

    def test_reservation_limit_error_is_available(self):
        self.assertTrue(issubclass(ReservationLimitReached, Exception))


class LoanServiceTests(unittest.TestCase):
    """Cover the borrowing guard rails."""

    def test_member_within_limit_can_borrow(self):
        service = LoanService()
        self.assertTrue(service.can_borrow(FakeMember(loans=1)))

    def test_member_at_limit_cannot_borrow(self):
        service = LoanService()
        self.assertFalse(service.can_borrow(FakeMember(loans=3)))

    def test_suspended_member_cannot_borrow(self):
        service = LoanService()
        self.assertFalse(service.can_borrow(FakeMember(suspended=True)))


class OverdueTests(unittest.TestCase):
    """Cover the overdue reporting helpers."""

    def test_fine_for_matches_the_policy(self):
        service = OverdueService()
        loan = FakeLoan(due_date=date(2026, 3, 1))
        self.assertEqual(
            service.fine_for(loan, today=date(2026, 3, 20)), calculate_fine(19)
        )

    def test_notice_carries_the_formatted_fine(self):
        loan = FakeLoan(due_date=date(2026, 3, 1))
        notice = build_notice(loan, today=date(2026, 3, 20))
        self.assertEqual(notice["days_overdue"], 19)
        self.assertEqual(notice["fine"], format_amount(calculate_fine(19)))

    def test_format_amount_pads_the_cents(self):
        self.assertEqual(format_amount(5), "0.05")
        self.assertEqual(format_amount(1234), "12.34")


class FakeCopy:
    """Stand-in for ``catalog.models.Copy``."""

    def __init__(self, book):
        self.book = book


class FakeLoan:
    """Stand-in for ``lending.models.Loan``."""

    def __init__(self, due_date):
        self.pk = 7
        self.due_date = due_date
        self.member = FakeMember()
        self.copy = FakeCopy(FakeBook())


if __name__ == "__main__":
    unittest.main()
