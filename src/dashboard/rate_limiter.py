import threading
import time
from collections import defaultdict
from typing import Dict, List

class RateLimiter:
    """
    Thread-safe sliding-window rate limiter.
    Limits requests per client key (e.g. client IP or auth token)
    to protect against runaway shortcuts, spam, or denial-of-service.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_key: str) -> bool:
        if not client_key:
            client_key = "anonymous"

        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            # Clean expired timestamps
            self.requests[client_key] = [t for t in self.requests[client_key] if t > cutoff]

            if len(self.requests[client_key]) >= self.max_requests:
                return False

            self.requests[client_key].append(now)
            return True

    def get_remaining(self, client_key: str) -> int:
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            active = [t for t in self.requests.get(client_key, []) if t > cutoff]
            return max(0, self.max_requests - len(active))

    def reset(self):
        with self._lock:
            self.requests.clear()
