"""One view: it starts the checkout of a basket.

The view keeps no rule of its own. It audits the request through a method it
inherits from ``AuditMixin`` — declared in another file — and hands the basket to
the application service.
"""
from orders.common.mixins import AuditMixin
from orders.services.checkout import CheckoutService


class CheckoutView(AuditMixin):
    """POST /orders/{order_id}/checkout."""

    def __init__(self):
        self.checkout = CheckoutService()

    def post(self, request, order_id):
        """Audit the request and delegate to the service."""
        self.record_audit("checkout", order_id)
        placed = self.checkout.place(order_id, request["items"])
        return {"status": "accepted", "order": placed}
