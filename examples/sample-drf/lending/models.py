"""Persistence models for members, loans and reservations."""
from django.db import models

from catalog.models import Book, Copy
from lending.domain.policies import TIER_BASIC, TIER_SCHOLAR, TIER_STAFF

LOAN_STATE_OPEN = "open"
LOAN_STATE_RETURNED = "returned"

RESERVATION_STATE_OPEN = "open"
RESERVATION_STATE_FULFILLED = "fulfilled"
RESERVATION_STATE_EXPIRED = "expired"

TIER_CHOICES = [
    (TIER_BASIC, "Basic"),
    (TIER_SCHOLAR, "Scholar"),
    (TIER_STAFF, "Staff"),
]


class Member(models.Model):
    """Somebody entitled to borrow from the library."""

    card_number = models.CharField(max_length=24, unique=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    tier = models.CharField(max_length=16, choices=TIER_CHOICES, default=TIER_BASIC)
    joined_on = models.DateField(null=True, blank=True)
    suspended = models.BooleanField(default=False)

    class Meta:
        ordering = ["full_name"]

    def open_loans(self):
        """Return the loans this member has not returned yet."""
        return self.loans.filter(state=LOAN_STATE_OPEN)

    def open_reservations(self):
        """Return the reservations still waiting in the queue."""
        return self.reservations.filter(state=RESERVATION_STATE_OPEN)

    def __str__(self):
        return self.card_number


class Loan(models.Model):
    """One copy handed to one member for a bounded period."""

    member = models.ForeignKey(Member, related_name="loans", on_delete=models.PROTECT)
    copy = models.ForeignKey(Copy, related_name="loans", on_delete=models.PROTECT)
    checked_out_on = models.DateField()
    due_date = models.DateField()
    returned_on = models.DateField(null=True, blank=True)
    renewal_count = models.IntegerField(default=0)
    fine_cents = models.IntegerField(default=0)
    state = models.CharField(max_length=16, default=LOAN_STATE_OPEN)

    class Meta:
        ordering = ["-checked_out_on"]

    def is_open(self):
        """Return whether the copy is still out with the member."""
        return self.state == LOAN_STATE_OPEN

    def close(self, returned_on, fine_cents):
        """Record the return of the copy and the fine that came with it."""
        self.returned_on = returned_on
        self.fine_cents = fine_cents
        self.state = LOAN_STATE_RETURNED
        self.save(update_fields=["returned_on", "fine_cents", "state"])
        return self

    def __str__(self):
        return "loan #{0}".format(self.pk)


class Reservation(models.Model):
    """A member's claim on the next copy of a title to come back."""

    member = models.ForeignKey(
        Member, related_name="reservations", on_delete=models.CASCADE
    )
    book = models.ForeignKey(Book, related_name="reservations", on_delete=models.CASCADE)
    placed_on = models.DateField()
    expires_on = models.DateField()
    state = models.CharField(max_length=16, default=RESERVATION_STATE_OPEN)

    class Meta:
        ordering = ["placed_on"]

    def is_open(self):
        """Return whether this reservation still holds a place in the queue."""
        return self.state == RESERVATION_STATE_OPEN

    def fulfill(self):
        """Mark the reservation as satisfied by a returned copy."""
        self.state = RESERVATION_STATE_FULFILLED
        self.save(update_fields=["state"])
        return self

    def expire(self):
        """Drop the reservation once it has waited past its expiry date."""
        self.state = RESERVATION_STATE_EXPIRED
        self.save(update_fields=["state"])
        return self

    def __str__(self):
        return "reservation #{0}".format(self.pk)
