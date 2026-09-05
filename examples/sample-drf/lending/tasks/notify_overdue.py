"""Overdue notice delivery.

The scheduled job and the return flow both end up here, which is what
makes this module a shared leaf of the call graph.
"""
from datetime import date

from lending.domain.policies import calculate_fine, days_overdue
from lending.models import Loan, Member


def format_amount(cents):
    """Render an amount in cents as a human-readable currency string."""
    return "{0}.{1:02d}".format(cents // 100, cents % 100)


def build_notice(loan, today=None):
    """Build the notice payload for a single overdue loan."""
    reference = today or date.today()
    late_days = days_overdue(loan.due_date, reference)
    fine_cents = calculate_fine(late_days)
    return {
        "loan_id": loan.pk,
        "member_email": loan.member.email,
        "title": loan.copy.book.full_title(),
        "days_overdue": late_days,
        "fine": format_amount(fine_cents),
    }


def notify_overdue_member(loan, today=None):
    """Send one member the notice for one overdue loan."""
    notice = build_notice(loan, today=today)
    deliver_notice(notice)
    return notice


def deliver_notice(notice):
    """Hand the rendered notice to the delivery channel.

    The fixture only records the notice; a real deployment would push it
    onto an outbound mail queue here.
    """
    return {"delivered": True, "to": notice["member_email"]}


def notify_member_of_suspension(member_id):
    """Tell a member that borrowing has been paused on their card."""
    member = Member.objects.get(pk=member_id)
    return deliver_notice({"member_email": member.email, "loan_id": None})


def notify_batch(loans, today=None):
    """Send notices for a batch of overdue loans and report the count."""
    sent = 0
    for loan in loans:
        notify_overdue_member(loan, today=today)
        sent += 1
    return sent


def notify_all_open_loans(today=None):
    """Entrypoint used by the scheduler when no batch is supplied."""
    reference = today or date.today()
    loans = Loan.objects.filter(due_date__lt=reference)
    return notify_batch(loans, today=reference)
