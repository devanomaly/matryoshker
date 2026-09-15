"""The only place that talks to the payment provider's library.

``payments_sdk`` is third-party: it is never part of an extraction of this repo,
so a frame that crosses into it carries the edge ``other`` and says so in its
edge note.
"""
try:
    import payments_sdk
except ImportError:  # the fixture runs without the provider library installed
    payments_sdk = None


class PaymentGateway:
    """Adapter over the provider library, so no rule ever sees it."""

    def charge(self, amount):
        """Charge `amount`; without the library this is a no-op."""
        if payments_sdk is None:
            return {"amount": amount, "status": "skipped"}
        return payments_sdk.charge(amount=amount)
