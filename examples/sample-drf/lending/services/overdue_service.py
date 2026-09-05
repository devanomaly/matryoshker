"""Detection and follow-up of loans that have passed their due date."""
from datetime import date

from lending.domain.policies import calculate_fine, days_overdue, is_fine_due
from lending.models import LOAN_STATE_OPEN, Loan
from lending.tasks.notify_overdue import notify_batch, notify_overdue_member


class OverdueService:
    """Finds overdue loans and drives the notice job over them."""

    def find_overdue(self, today=None):
        """Return every open loan whose due date has already passed."""
        reference = today or date.today()
        return Loan.objects.filter(state=LOAN_STATE_OPEN, due_date__lt=reference)

    def fine_for(self, loan, today=None):
        """Return the fine a single overdue loan has accrued."""
        reference = today or date.today()
        return calculate_fine(days_overdue(loan.due_date, reference))

    def is_billable(self, loan, today=None):
        """Return whether this loan has used up its grace period."""
        reference = today or date.today()
        return is_fine_due(days_overdue(loan.due_date, reference))

    def notify_one(self, loan, today=None):
        """Send the overdue notice for a single loan."""
        return notify_overdue_member(loan, today=today)

    def notify_all(self, today=None):
        """Send notices for every overdue loan and report how many went out."""
        reference = today or date.today()
        loans = self.find_overdue(today=reference)
        return notify_batch(loans, today=reference)

    def total_outstanding_fines(self, today=None):
        """Return the sum of the fines currently owed across all loans."""
        reference = today or date.today()
        total = 0
        for loan in self.find_overdue(today=reference):
            total += self.fine_for(loan, today=reference)
        return total
