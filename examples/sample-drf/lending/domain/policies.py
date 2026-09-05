"""Lending rules expressed as plain functions.

Nothing in this module touches the database or the framework, which makes
it the only part of the lending app that is trivially unit-testable. Every
service and handler that needs a limit, a due date or a fine asks here.
"""
from datetime import timedelta

TIER_BASIC = "basic"
TIER_SCHOLAR = "scholar"
TIER_STAFF = "staff"

#: How many loans a member of each tier may hold at the same time.
LOAN_LIMIT_BY_TIER = {
    TIER_BASIC: 3,
    TIER_SCHOLAR: 10,
    TIER_STAFF: 20,
}

#: How long a loan runs, in days, for each tier.
LOAN_PERIOD_BY_TIER = {
    TIER_BASIC: 21,
    TIER_SCHOLAR: 42,
    TIER_STAFF: 90,
}

#: How many open reservations a member of each tier may hold.
RESERVATION_LIMIT_BY_TIER = {
    TIER_BASIC: 2,
    TIER_SCHOLAR: 5,
    TIER_STAFF: 5,
}

DAILY_FINE_CENTS = 25
MAX_FINE_CENTS = 2000
GRACE_PERIOD_DAYS = 3
RESERVATION_VALID_DAYS = 7
MAX_RENEWALS = 2


def loan_limit_for(tier):
    """Return how many simultaneous loans a tier allows."""
    return LOAN_LIMIT_BY_TIER.get(tier, LOAN_LIMIT_BY_TIER[TIER_BASIC])


def loan_period_days(tier):
    """Return the loan length in days for a tier."""
    return LOAN_PERIOD_BY_TIER.get(tier, LOAN_PERIOD_BY_TIER[TIER_BASIC])


def reservation_limit_for(tier):
    """Return how many open reservations a tier allows."""
    return RESERVATION_LIMIT_BY_TIER.get(tier, RESERVATION_LIMIT_BY_TIER[TIER_BASIC])


def is_within_loan_limit(active_loan_count, tier):
    """Return whether one more loan would still fit inside the tier limit."""
    return active_loan_count < loan_limit_for(tier)


def is_within_reservation_limit(open_reservation_count, tier):
    """Return whether one more reservation fits inside the tier limit."""
    return open_reservation_count < reservation_limit_for(tier)


def due_date_for(checked_out_on, tier):
    """Return the due date of a loan started on ``checked_out_on``."""
    return checked_out_on + timedelta(days=loan_period_days(tier))


def reservation_expiry(placed_on):
    """Return the moment a reservation stops holding a place in the queue."""
    return placed_on + timedelta(days=RESERVATION_VALID_DAYS)


def days_overdue(due_date, today):
    """Return how many days a loan is past its due date, never negative."""
    if today <= due_date:
        return 0
    return (today - due_date).days


def is_overdue(due_date, today):
    """Return whether a loan has passed its due date."""
    return days_overdue(due_date, today) > 0


def is_fine_due(overdue_days):
    """Return whether the grace period has been used up."""
    return overdue_days > GRACE_PERIOD_DAYS


def calculate_fine(overdue_days):
    """Return the fine in cents for a loan that is ``overdue_days`` late.

    The first few days are free, and the fine stops growing once it hits
    the ceiling so a forgotten book can never become unpayable.
    """
    if not is_fine_due(overdue_days):
        return 0
    billable_days = overdue_days - GRACE_PERIOD_DAYS
    return min(billable_days * DAILY_FINE_CENTS, MAX_FINE_CENTS)


def can_renew(renewal_count, has_reservations):
    """Return whether a loan may be extended once more."""
    if has_reservations:
        return False
    return renewal_count < MAX_RENEWALS
