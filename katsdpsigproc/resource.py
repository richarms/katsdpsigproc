"""Utilities for scheduling device operations with trollius."""

import trollius
import logging
import collections
from trollius import From


_logger = logging.getLogger(__name__)


@trollius.coroutine
def wait_until(future, when, loop=None):
    """Like :meth:`trollius.wait_for`, but with an absolute timeout."""
    def ready(*args):
        if not waiter.done():
            waiter.set_result(None)

    if loop is None:
        loop = trollius.get_event_loop()
    waiter = trollius.Future(loop=loop)
    timeout_handle = loop.call_at(when, ready)
    # Ensure the that future is really a future, not a coroutine object
    future = trollius.async(future, loop=loop)
    future.add_done_callback(ready)
    try:
        yield From(waiter)
        if future.done():
            raise trollius.Return(future.result())
        else:
            future.remove_done_callback(ready)
            future.cancel()
            raise trollius.TimeoutError()
    finally:
        timeout_handle.cancel()


@trollius.coroutine
def _async_wait_for_events(events, loop=None):
    def wait_for_events(events):
        for event in events:
            event.wait()
    if loop is None:
        loop = trollius.get_event_loop()
    if events:
        yield From(loop.run_in_executor(None, wait_for_events, events))


class ResourceAllocation(object):
    """A handle representing a future acquisition of a resource. There are two
    ways to make the acquisition current:

     1. Call :meth:`wait`, which returns a future. The result of this future
        is a list of device events that must complete before it is safe to use
        the resource; they can either be waited for on the host (for example,
        using ``run_in_executor``), or by enqueuing a device wait before
        device operations on the resource.
     2. The above steps (with a blocking host wait) can be combined using
        :meth:`wait_events`.

    Instances of this class should never be constructed directly. Instead, use
    :meth:`Resource.acquire`.

    This class implements the context manager protocol, providing the
    underlying resource as the return value. This handles some cleanup if the
    method using the resource raises an exception without releasing the
    resource cleanly.
    """
    def __init__(self, start, end, value, loop):
        self._start = start
        self._end = end
        self._loop = loop
        self.value = value

    def wait(self):
        """Return a future that will be set to a list of device events that
        must be waited for.
        """
        return self._start

    @trollius.coroutine
    def wait_events(self):
        """Wait for previous use of the resource to be complete on the host.

        This is a coroutine.
        """
        events = yield From(self._start)
        yield From(_async_wait_for_events(events, loop=self._loop))

    def ready(self, events=None):
        """Indicate that we are done with the resource, and that subsequent
        acquirers may use it. Note that even if the caller decides that it
        doesn't need to use the resource, it must not call this until the
        resource is ready.

        Parameters
        ----------
        events : list
            Device events that must be waited on before the resource is ready
        """
        if events is None:
            events = []
        self._end.set_result(events)

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc_value, exc_tb):
        if not self._end.done():
            if exc_type is not None:
                self._end.cancel()
            else:
                _logger.warn('Resource allocation was not explicitly made ready')
                self.ready()


class Resource(object):
    """Abstraction of a contended resource, which may exist on a device.

    Passing of ownership is done via futures. Acquiring a resource is a
    non-blocking operation that returns two futures: a future to wait for
    before use, and a future to be signalled with a result when done. The
    value of each of these futures is a (possibly empty) list of device
    events which must be waited on before more device work is scheduled.

    Parameters
    ----------
    value : object
        Underlying resource to manage
    loop : trollius.BaseEventLoop, optional
        Event loop used for asynchronous operations. If not specified, defaults
        to ``trollius.get_event_loop()``.

    Attributes
    ----------
    value : object
        Underlying resource passed to the constructor
    """
    def __init__(self, value, loop=None):
        if loop is None:
            loop = trollius.get_event_loop()
        self._loop = loop
        self._future = trollius.Future(loop=loop)
        self._future.set_result([])
        self.value = value

    def acquire(self):
        """Indicate intent to acquire the resource. This does not actually
        acquire the resource, but instead returns a handle that can be used to
        acquire and release it later. Acquisitions always occur in the order
        in which calls to :meth:`acquire` are made.

        See :class:`ResourceAcquisition` for further details.
        """
        old = self._future
        self._future = trollius.Future(loop=self._loop)
        return ResourceAllocation(old, self._future, self.value, loop=self._loop)


class JobQueue(object):
    """Maintains a list of in-flight asynchronous jobs."""
    def __init__(self):
        self._jobs = collections.deque()

    def add(self, job):
        """Append a job to the list. If `job` is a coroutine, it is
        automatically wrapped in a task."""
        self._jobs.append(trollius.async(job))

    def clean(self):
        """Remove completed jobs from the front of the queue."""
        while self._jobs and self._jobs[0].done():
            self._jobs.popleft().result()     # Re-throws any exception

    @trollius.coroutine
    def finish(self, max_remaining=0):
        """Wait for jobs to finish until there are at most `max_remaining` in
        the queue.

        This is a coroutine.
        """
        while len(self._jobs) > max_remaining:
            yield From(self._jobs.popleft())

    def __len__(self):
        return len(self._jobs)

    def __nonzero__(self):
        return bool(self._jobs)

    def __contains__(self, item):
        return item in self._jobs


__all__ = ['wait_until', 'Resource', 'ResourceAllocation', 'JobQueue']
