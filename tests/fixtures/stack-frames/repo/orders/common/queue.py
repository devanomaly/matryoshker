"""A tiny job queue that dispatches by name.

A job is published as a dotted string, so this module never imports the module
that runs it: the hand-off is invisible to an import graph, which is exactly why
a frame crossing it is reported as not provable instead of broken.
"""

PENDING = []


def enqueue(job_name, **payload):
    """Publish a job by dotted name; the worker resolves it at run time."""
    PENDING.append((job_name, payload))
    return len(PENDING)


def drain():
    """Pop every pending job, oldest first."""
    jobs = list(PENDING)
    PENDING.clear()
    return jobs
