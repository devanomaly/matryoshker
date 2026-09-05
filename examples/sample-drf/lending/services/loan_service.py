"""Checkout, renewal and return of individual copies.

This service is the single place that changes the state of a copy and of
the loan attached to it. Both the catalog views and the lending handlers
go through it.
"""
from datetime import date, timedelta

from lending.domain.policies import (
    calculate_fine,
    can_renew,
    days_overdue,
    due_date_for,
    is_within_loan_limit,
    loan_period_days,
)
from lending.models import LOAN_STATE_OPEN, Loan, Member


class LoanLimitReached(Exception):
    """Raised when a member already holds as many loans as their tier allows."""


class MemberSuspended(Exception):
    """Raised when a suspended card is used to start a loan."""


class LoanService:
    """Runs the lifecycle of a loan from checkout to return."""

    def get_member(self, member_id):
        """Return the member a request refers to."""
        return Member.objects.get(pk=member_id)

    def active_loans_for(self, member):
        """Return the loans this member has not returned yet."""
        return member.open_loans()

    def count_active_loans(self, member):
        """Return how many loans this member currently holds."""
        return self.active_loans_for(member).count()

    def can_borrow(self, member):
        """Return whether the member may start one more loan."""
        if member.suspended:
            return False
        return is_within_loan_limit(self.count_active_loans(member), member.tier)

    def checkout(self, member_id, copy, today=None):
        """Hand a copy to a member and open the matching loan record."""
        reference = today or date.today()
        member = self.get_member(member_id)
        if member.suspended:
            raise MemberSuspended(member.card_number)
        if not self.can_borrow(member):
            raise LoanLimitReached(member.card_number)
        copy.mark_lent()
        return Loan.objects.create(
            member=member,
            copy=copy,
            checked_out_on=reference,
            due_date=due_date_for(reference, member.tier),
            state=LOAN_STATE_OPEN,
        )

    def renew(self, loan, today=None):
        """Extend a loan by one further period when the rules allow it."""
        reference = today or date.today()
        has_queue = loan.copy.book.reservations.filter(state="open").exists()
        if not can_renew(loan.renewal_count, has_queue):
            return None
        loan.due_date = reference + timedelta(days=loan_period_days(loan.member.tier))
        loan.renewal_count = loan.renewal_count + 1
        loan.save(update_fields=["due_date", "renewal_count"])
        return loan

    def outstanding_fine(self, loan, today=None):
        """Return the fine a loan has accrued so far, in cents."""
        reference = today or date.today()
        return calculate_fine(days_overdue(loan.due_date, reference))

    def return_copy(self, loan, today=None):
        """Take a copy back, close the loan and settle the fine."""
        reference = today or date.today()
        fine_cents = self.outstanding_fine(loan, today=reference)
        loan.copy.mark_returned()
        return loan.close(reference, fine_cents)
