"""Limite de tentativas de login (janela deslizante, em memória)."""

import threading
import time
from collections import defaultdict, deque


class LoginLimiter:
    def __init__(self, max_attempts: int, window_seconds: int, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and now - attempts[0] >= self.window:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str) -> int | None:
        """Segundos até poder tentar de novo, ou None se ainda pode tentar."""
        with self._lock:
            now = self.clock()
            attempts = self._prune(key, now)
            if len(attempts) < self.max_attempts:
                return None
            return max(1, int(self.window - (now - attempts[0])) + 1)

    def register_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key, self.clock()).append(self.clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
