"""Drop duplicate webhook deliveries.

Meta retries a delivery if it doesn't get a fast 200, so the same message can
arrive more than once. Without this, a user could get two answers (and two
paid LLM runs) for one question.

v2 limitation, stated plainly: this is in-process memory. It is lost on
restart and not shared between workers. The production fix is a unique
constraint on message_id in the database or a Redis SET NX — that comes with
the move from BackgroundTasks to a real queue.
"""
import threading
import time
from collections import OrderedDict


class SeenMessages:
    def __init__(self, ttl_seconds: int = 24 * 3600, max_size: int = 10_000):
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._ttl = ttl_seconds
        self._max = max_size
        self._lock = threading.Lock()

    def first_time(self, message_id: str) -> bool:
        """True the first time an id is seen; False for every repeat."""
        now = time.time()
        with self._lock:
            # Evict expired entries (oldest first) and cap the size.
            while self._seen and (
                len(self._seen) >= self._max
                or now - next(iter(self._seen.values())) > self._ttl
            ):
                self._seen.popitem(last=False)
            if message_id in self._seen:
                return False
            self._seen[message_id] = now
            return True


seen_messages = SeenMessages()
