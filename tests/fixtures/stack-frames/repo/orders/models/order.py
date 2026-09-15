"""The order aggregate."""


class Order:
    """One order: its lines, its total, and the states it moves through."""

    def __init__(self, order_id, items):
        self.id = order_id
        self.items = list(items)
        self.state = "new"

    def total(self):
        """Quantity times unit price, summed over every line."""
        return sum(line["quantity"] * line["price"] for line in self.items)

    def mark_paid(self):
        """Move the order to `paid`; armed as a commit hook by the service."""
        self.state = "paid"
        return self.state

    def mark_shipped(self):
        """Move the order to `shipped`; called from the background job."""
        self.state = "shipped"
        return self.state
