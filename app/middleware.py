from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """Allow normal fast replies while stopping message floods."""

    def __init__(self, limit: int = 8, window: float = 5.0) -> None:
        self.limit = limit
        self.window = window
        self.events: dict[int, deque[float]] = defaultdict(deque)
        self.last_warning: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            now = time.monotonic()
            user_id = event.from_user.id
            timestamps = self.events[user_id]
            while timestamps and timestamps[0] <= now - self.window:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                if now - self.last_warning[user_id] > self.window:
                    self.last_warning[user_id] = now
                    await event.answer("Juda tez yuboryapsiz. Bir necha soniyadan keyin davom eting.")
                return None
            timestamps.append(now)
        return await handler(event, data)
