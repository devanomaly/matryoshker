"""The central rule of the flow: validate a basket, charge it, place the order."""
from orders.common.hooks import on_commit
from orders.common.queue import enqueue
from orders.gateway.payments import PaymentGateway
from orders.models.order import Order

RECEIPT_JOB = "orders.tasks.notify.send_receipt"


def validate_items(items):
    """Reject an empty basket and any line with a non-positive quantity."""
    if not items:
        raise ValueError("an order needs at least one item")
    for item in items:
        if item["quantity"] <= 0:
            raise ValueError("quantity must be positive")
    return len(items)


class CheckoutService:
    """Turns a validated basket into a paid order."""

    def __init__(self):
        self.gateway = PaymentGateway()

    def place(self, order_id, items):
        """Validate, charge, arm the commit hook and schedule the receipt."""
        lines = validate_items(items)
        order = Order(order_id, items)
        self.gateway.charge(order.total())
        on_commit(order.mark_paid)
        enqueue(RECEIPT_JOB, order_id=order_id)
        return {"id": order_id, "lines": lines}
