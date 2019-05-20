"""Tests for :mod:`katsdpsigproc.resource`."""

import functools
import time
import asyncio
import queue
from unittest import mock

from nose.tools import (assert_equal, assert_true, assert_false,
                        assert_in, assert_not_in, assert_raises, nottest)

from .. import resource


@nottest
def async_test(func):
    func = asyncio.coroutine(func)

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        self.loop.run_until_complete(func(self, *args, **kwargs))
    return wrapper


class TestWaitUntil(object):
    def setup(self):
        self.loop = asyncio.get_event_loop_policy().new_event_loop()

    def teardown(self):
        self.loop.close()

    @async_test
    def test_result(self):
        """wait_until returns before the timeout if a result is set"""
        future = asyncio.Future(loop=self.loop)
        self.loop.call_later(0.1, future.set_result, 42)
        result = yield from(resource.wait_until(future, self.loop.time() + 1000000, loop=self.loop))
        assert_equal(42, result)

    @async_test
    def test_already_set(self):
        """wait_until returns if a future has a result set before the call"""
        future = asyncio.Future(loop=self.loop)
        future.set_result(42)
        result = yield from(resource.wait_until(future, self.loop.time() + 1000000, loop=self.loop))
        assert_equal(42, result)

    @async_test
    def test_exception(self):
        """wait_until rethrows an exception set on the future"""
        future = asyncio.Future(loop=self.loop)
        self.loop.call_later(0.1, future.set_exception, ValueError('test'))
        with assert_raises(ValueError):
            yield from(resource.wait_until(future, self.loop.time() + 1000000, loop=self.loop))

    @async_test
    def test_timeout(self):
        """wait_until throws `asyncio.TimeoutError` if it times out, and cancels the future"""
        future = asyncio.Future(loop=self.loop)
        with assert_raises(asyncio.TimeoutError):
            yield from(resource.wait_until(future, self.loop.time() + 0.01, loop=self.loop))
        assert_true(future.cancelled())

    @async_test
    def test_shield(self):
        """wait_until does not cancel the future if it is wrapped in shield"""
        future = asyncio.Future(loop=self.loop)
        with assert_raises(asyncio.TimeoutError):
            yield from(resource.wait_until(asyncio.shield(future),
                                           self.loop.time() + 0.01, loop=self.loop))
        assert_false(future.cancelled())


class DummyEvent(object):
    """Dummy version of katsdpsigproc.accel event, whose wait method just
    sleeps for a small time and then appends the event to a queue.
    """
    def __init__(self, completed):
        self.complete = False
        self.completed = completed

    def wait(self):
        if not self.complete:
            time.sleep(0.1)
            self.completed.put(self)
            self.complete = True


class TestResource(object):
    def setup(self):
        self.loop = asyncio.get_event_loop_policy().new_event_loop()
        self.completed = queue.Queue()

    def teardown(self):
        self.loop.close()

    @asyncio.coroutine
    def _run_frame(self, acq, event):
        with acq as value:
            assert_equal(42, value)
            yield from(acq.wait_events())
            acq.ready([event])
            self.completed.put(acq)

    @async_test
    def test_wait_events(self):
        """Test :meth:`resource.ResourceAcquisition.wait_events`"""
        r = resource.Resource(42, loop=self.loop)
        a0 = r.acquire()
        a1 = r.acquire()
        e0 = DummyEvent(self.completed)
        e1 = DummyEvent(self.completed)
        run1 = asyncio.ensure_future(self._run_frame(a1, e1), loop=self.loop)
        run0 = asyncio.ensure_future(self._run_frame(a0, e0), loop=self.loop)
        yield from(run0)
        yield from(run1)
        order = []
        try:
            while True:
                order.append(self.completed.get_nowait())
        except queue.Empty:
            pass
        assert_equal(order, [a0, e0, a1])

    @async_test
    def test_context_manager_exception(self):
        """Test using :class:`resource.ResourceAcquisition` as a context
        manager when an error is raised.
        """
        r = resource.Resource(None, loop=self.loop)
        a0 = r.acquire()
        a1 = r.acquire()
        with assert_raises(RuntimeError):
            with a0:
                yield from(a0.wait_events())
                raise RuntimeError('test exception')
        with assert_raises(RuntimeError):
            with a1:
                yield from(a1.wait_events())
                a1.ready()

    @mock.patch('katsdpsigproc.resource._logger')
    @async_test
    def test_context_manager_no_ready(self, mock_logging):
        """Test using :class:`resource.ResourceAllocation` as a context
        manager when the user does not call
        :meth:`~resource.ResourceAllocation.ready`.
        """
        r = resource.Resource(None, loop=self.loop)
        a0 = r.acquire()
        with a0:
            pass
        mock_logging.warn.assert_called_once_with(
            'Resource allocation was not explicitly made ready')


class TestJobQueue(object):
    def setup(self):
        self.loop = asyncio.get_event_loop_policy().new_event_loop()
        self.jobs = resource.JobQueue()
        self.finished = [asyncio.Future(loop=self.loop) for i in range(5)]
        self.unfinished = [asyncio.Future(loop=self.loop) for i in range(5)]
        for i, future in enumerate(self.finished):
            future.set_result(i)

    def teardown(self):
        self.loop.close()

    def test_clean(self):
        self.jobs.add(self.finished[0])
        self.jobs.add(self.unfinished[0])
        self.jobs.add(self.finished[1])
        self.jobs.clean()
        assert_equal(2, len(self.jobs._jobs))

    @asyncio.coroutine
    def _finish(self):
        for i, future in enumerate(self.unfinished):
            yield from(asyncio.sleep(0.02, loop=self.loop))
            future.set_result(i)

    @async_test
    def test_finish(self):
        self.jobs.add(self.finished[0])
        self.jobs.add(self.unfinished[0])
        self.jobs.add(self.unfinished[1])
        self.jobs.add(self.unfinished[2])
        finisher = asyncio.ensure_future(self._finish(), loop=self.loop)
        yield from(self.jobs.finish(max_remaining=1))
        assert_true(self.unfinished[0].done())
        assert_true(self.unfinished[1].done())
        assert_false(self.unfinished[2].done())
        assert_equal(1, len(self.jobs))
        yield from(finisher)

    def test_nonzero(self):
        assert_false(self.jobs)
        self.jobs.add(self.finished[0])
        assert_true(self.jobs)

    def test_len(self):
        assert_equal(0, len(self.jobs))
        self.jobs.add(self.finished[0])
        self.jobs.add(self.unfinished[1])
        self.jobs.add(self.finished[1])
        assert_equal(3, len(self.jobs))

    def test_contains(self):
        assert_not_in(self.finished[0], self.jobs)
        self.jobs.add(self.finished[0])
        assert_in(self.finished[0], self.jobs)
        assert_not_in(self.finished[1], self.jobs)
