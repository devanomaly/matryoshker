"""Persistence models for the bibliographic catalog.

An ``Author`` writes many ``Book`` titles; each title is held by the
library as one or more physical ``Copy`` records. Lending always happens
against a copy, never against a title.
"""
from django.db import models

COPY_STATUS_AVAILABLE = "available"
COPY_STATUS_LENT = "lent"
COPY_STATUS_WITHDRAWN = "withdrawn"

COPY_STATUS_CHOICES = [
    (COPY_STATUS_AVAILABLE, "Available"),
    (COPY_STATUS_LENT, "On loan"),
    (COPY_STATUS_WITHDRAWN, "Withdrawn"),
]


class Author(models.Model):
    """A person credited on one or more titles held by the library."""

    given_name = models.CharField(max_length=120)
    family_name = models.CharField(max_length=120)
    birth_year = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["family_name", "given_name"]

    def display_name(self):
        """Return the name as it should appear on a catalog card."""
        return "{0}, {1}".format(self.family_name, self.given_name)

    def title_count(self):
        """Return how many titles are credited to this author."""
        return self.books.count()

    def __str__(self):
        return self.display_name()


class Book(models.Model):
    """A bibliographic title, independent of how many copies exist."""

    isbn = models.CharField(max_length=17, unique=True)
    title = models.CharField(max_length=250)
    subtitle = models.CharField(max_length=250, blank=True)
    author = models.ForeignKey(Author, related_name="books", on_delete=models.PROTECT)
    published_year = models.IntegerField(null=True, blank=True)
    shelf_code = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["title"]

    def full_title(self):
        """Return title and subtitle joined the way the catalog prints it."""
        if not self.subtitle:
            return self.title
        return "{0}: {1}".format(self.title, self.subtitle)

    def available_copies(self):
        """Return the copies of this title that can be lent right now."""
        return self.copies.filter(status=COPY_STATUS_AVAILABLE)

    def is_available(self):
        """Return whether at least one copy of this title can be lent."""
        return self.available_copies().exists()

    def __str__(self):
        return self.full_title()


class Copy(models.Model):
    """One physical item on the shelf, identified by its barcode."""

    book = models.ForeignKey(Book, related_name="copies", on_delete=models.CASCADE)
    barcode = models.CharField(max_length=32, unique=True)
    status = models.CharField(
        max_length=16, choices=COPY_STATUS_CHOICES, default=COPY_STATUS_AVAILABLE
    )
    acquired_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["barcode"]

    def is_available(self):
        """Return whether this copy is on the shelf and lendable."""
        return self.status == COPY_STATUS_AVAILABLE

    def mark_lent(self):
        """Flag this copy as being out on loan."""
        self.status = COPY_STATUS_LENT
        self.save(update_fields=["status"])
        return self

    def mark_returned(self):
        """Flag this copy as back on the shelf."""
        self.status = COPY_STATUS_AVAILABLE
        self.save(update_fields=["status"])
        return self

    def withdraw(self):
        """Take this copy permanently out of circulation."""
        self.status = COPY_STATUS_WITHDRAWN
        self.save(update_fields=["status"])
        return self

    def __str__(self):
        return self.barcode
