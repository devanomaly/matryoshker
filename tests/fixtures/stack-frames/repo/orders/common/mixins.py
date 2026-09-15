"""Behaviour the views inherit instead of repeating."""

AUDIT_LOG = []


class AuditMixin:
    """Writes one audit line per request. Inherited, never instantiated."""

    def record_audit(self, action, subject):
        """Append one audit line and return how many there are."""
        AUDIT_LOG.append((action, subject))
        return len(AUDIT_LOG)
