import asyncio
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

class CapacityError(Exception):
    pass

@dataclass
class Session:
    touched: float
    history: list = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0

class Sessions:
    """Bounded, expiring, process-local history; never written to disk."""
    def __init__(self, ttl, capacity, clock=time.monotonic):
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self.entries = OrderedDict()

    @asynccontextmanager
    async def conversation(self, key):
        now = self.clock()
        for k, entry in list(self.entries.items()):
            if not entry.users and now - entry.touched >= self.ttl:
                del self.entries[k]
        if key not in self.entries:
            if len(self.entries) >= self.capacity:
                idle = next((k for k, v in self.entries.items() if not v.users), None)
                if idle is None:
                    raise CapacityError()
                del self.entries[idle]
            self.entries[key] = Session(now)
        entry = self.entries[key]
        entry.users += 1  # Reserve before awaiting; an in-flight/queued turn cannot be evicted.
        self.entries.move_to_end(key)
        try:
            async with entry.lock:
                yield entry.history
        finally:
            entry.users -= 1
            entry.touched = self.clock()

    def clear(self, key):
        entry = self.entries.get(key)
        if entry and entry.users:
            return False
        self.entries.pop(key, None)
        return True
