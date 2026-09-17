"""Transaction hooks: callbacks that run once the unit of work commits."""

AFTER_COMMIT = []


def on_commit(callback):
    """Register `callback` to run when the current unit of work commits."""
    AFTER_COMMIT.append(callback)
    return callback


def commit():
    """Run every registered callback, oldest first, and forget them."""
    callbacks = list(AFTER_COMMIT)
    AFTER_COMMIT.clear()
    for callback in callbacks:
        callback()
    return len(callbacks)
