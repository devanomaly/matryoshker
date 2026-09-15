"""The job that tells a customer their order is on its way."""


def send_receipt(order_id):
    """Send the receipt and move the order on.

    ``Order`` is imported inside the function body on purpose: that is the shape
    an import graph built from module-level imports cannot see, so the call below
    has no edge to back it.
    """
    from orders.models.order import Order

    order = Order(order_id, [])
    order.mark_shipped()
    return {"order": order_id, "receipt": "sent"}
