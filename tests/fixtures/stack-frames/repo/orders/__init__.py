"""A very small order-taking service, used as a fixture for stack frames.

The package re-exports the one service a caller normally needs, so an importer
may reach it either through this module or through its defining file.
"""
from orders.services.checkout import CheckoutService

__all__ = ["CheckoutService"]
