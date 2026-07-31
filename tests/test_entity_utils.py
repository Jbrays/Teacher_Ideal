import asyncio
import concurrent.futures
import unittest

from backend.services.entity_utils import run_async


class LoopBoundResource:
    def __init__(self):
        self.loop = None

    async def call(self):
        current = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = current
        elif self.loop is not current:
            raise RuntimeError("Event loop is closed")
        await asyncio.sleep(0)
        return id(current)


class RunAsyncTests(unittest.TestCase):
    def test_reuses_same_loop_for_sequential_calls(self):
        resource = LoopBoundResource()

        first = run_async(resource.call())
        second = run_async(resource.call())

        self.assertEqual(first, second)

    def test_is_thread_safe(self):
        resource = LoopBoundResource()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            loops = list(executor.map(lambda _: run_async(resource.call()), range(8)))

        self.assertEqual(len(set(loops)), 1)


if __name__ == "__main__":
    unittest.main()
