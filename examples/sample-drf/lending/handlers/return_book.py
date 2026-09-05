"""Use case: take a copy back at the desk.

Returning a copy closes the loan, settles any fine, and then decides what
should happen to the people waiting for that title.
"""
from datetime import date

from lending.domain.policies import calculate_fine, days_overdue
from lending.models import RESERVATION_STATE_OPEN, Reservation
from lending.services.loan_service import LoanService
from lending.services.overdue_service import OverdueService
from lending.tasks.notify_overdue import deliver_notice


class ReturnBookHandler:
    """Closes a loan and hands the freed copy to the next member in line."""

    def __init__(self, loans=None, overdue=None):
        self.loans = loans or LoanService()
        self.overdue = overdue or OverdueService()

    def fine_for(self, loan, today=None):
        """Return the fine owed on this loan, in cents."""
        reference = today or date.today()
        return calculate_fine(days_overdue(loan.due_date, reference))

    def next_in_queue(self, book):
        """Return the oldest open reservation for a title, if there is one."""
        return Reservation.objects.filter(
            book=book, state=RESERVATION_STATE_OPEN
        ).first()

    def notify_next_member(self, reservation):
        """Tell the next member in line that a copy is waiting for them."""
        return deliver_notice(
            {"member_email": reservation.member.email, "loan_id": None}
        )

    def handle(self, loan, today=None):
        """Close the loan and return a summary of what happened."""
        reference = today or date.today()
        fine_cents = self.fine_for(loan, today=reference)
        closed = self.loans.return_copy(loan, today=reference)
        reservation = self.next_in_queue(loan.copy.book)
        if reservation is not None:
            self.notify_next_member(reservation)
            reservation.fulfill()
        return {
            "loan_id": closed.pk,
            "fine_cents": fine_cents,
            "reservation_fulfilled": reservation is not None,
        }
