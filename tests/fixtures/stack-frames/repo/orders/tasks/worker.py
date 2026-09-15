"""The worker process: it pulls jobs off the queue and runs them by name."""
from orders.common.queue import drain

REGISTRY = {}


def register(job_name, function):
    """Bind a dotted job name to the function that runs it."""
    REGISTRY[job_name] = function
    return job_name


def run_pending():
    """Run every pending job whose name is registered, and count them."""
    done = 0
    for job_name, payload in drain():
        function = REGISTRY.get(job_name)
        if function is not None:
            function(**payload)
            done += 1
    return done
