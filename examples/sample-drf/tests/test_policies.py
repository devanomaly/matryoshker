"""Unit tests for the pure lending rules.

This module imports nothing but the domain layer, so it is the one test
file in the fixture that runs without Django installed.
"""
import unittest
from datetime import date

from lending.domain.policies import (
    TIER_BASIC,
    TIER_SCHOLAR,
    TIER_STAFF,
    calculate_fine,
    can_renew,
    days_overdue,
    due_date_for,
    is_fine_due,
    is_overdue,
    is_within_loan_limit,
    loan_limit_for,
    loan_period_days,
    reservation_expiry,
)


class LoanLimitTests(unittest.TestCase):
    """Cover the per-tier loan allowances."""

    def test_known_tiers_have_distinct_limits(self):
        self.assertEqual(loan_limit_for(TIER_BASIC), 3)
        self.assertEqual(loan_limit_for(TIER_SCHOLAR), 10)
        self.assertEqual(loan_limit_for(TIER_STAFF), 20)

    def test_unknown_tier_falls_back_to_basic(self):
        self.assertEqual(loan_limit_for("unknown"), loan_limit_for(TIER_BASIC))

    def test_limit_is_exclusive(self):
        self.assertTrue(is_within_loan_limit(2, TIER_BASIC))
        self.assertFalse(is_within_loan_limit(3, TIER_BASIC))


class DueDateTests(unittest.TestCase):
    """Cover due dates, overdue counting and reservation expiry."""

    def test_due_date_uses_the_tier_period(self):
        start = date(2026, 3, 1)
        self.assertEqual(
            due_date_for(start, TIER_BASIC).toordinal() - start.toordinal(),
            loan_period_days(TIER_BASIC),
        )

    def test_days_overdue_is_never_negative(self):
        due = date(2026, 3, 10)
        self.assertEqual(days_overdue(due, date(2026, 3, 1)), 0)
        self.assertEqual(days_overdue(due, date(2026, 3, 15)), 5)

    def test_is_overdue_matches_days_overdue(self):
        due = date(2026, 3, 10)
        self.assertFalse(is_overdue(due, due))
        self.assertTrue(is_overdue(due, date(2026, 3, 11)))

    def test_reservation_expiry_is_after_placement(self):
        placed = date(2026, 3, 1)
        self.assertGreater(reservation_expiry(placed), placed)


class FineTests(unittest.TestCase):
    """Cover the grace period, the daily rate and the ceiling."""

    def test_grace_period_is_free(self):
        self.assertFalse(is_fine_due(3))
        self.assertEqual(calculate_fine(3), 0)

    def test_fine_starts_after_the_grace_period(self):
        self.assertTrue(is_fine_due(4))
        self.assertEqual(calculate_fine(4), 25)

    def test_fine_is_capped(self):
        self.assertEqual(calculate_fine(10000), calculate_fine(20000))


class RenewalTests(unittest.TestCase):
    """Cover the renewal rules."""

    def test_renewal_blocked_by_a_waiting_queue(self):
        self.assertFalse(can_renew(0, True))

    def test_renewal_allowed_until_the_cap(self):
        self.assertTrue(can_renew(0, False))
        self.assertTrue(can_renew(1, False))
        self.assertFalse(can_renew(2, False))


if __name__ == "__main__":
    unittest.main()
