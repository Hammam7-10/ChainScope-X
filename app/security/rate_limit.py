from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from typing import Protocol

from fastapi import HTTPException, Request


class RateLimitStore(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]: ...


class InMemoryRateLimitStore:
    """Development/test store only; it is intentionally not multi-instance safe."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        async with self._lock:
            events = self._events[key]
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry = max(1, int(events[0] + window_seconds - now + 0.999))
                return False, retry
            events.append(now)
            return True, max(1, int(events[0] + window_seconds - now + 0.999))


class SharedRateLimitStore:
    """Contract placeholder for a shared atomic store behind a future load balancer.

    A deployment must provide an implementation backed by an atomic shared service
    such as Redis or a database. R6 deliberately refuses to pretend this class is
    distributed while no shared service has been configured.
    """

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        raise RuntimeError("A shared rate-limit backend is not configured")


def client_ip(request: Request, trusted_proxy_networks: tuple[str, ...] = ()) -> str:
    peer = request.client.host if request.client else ""
    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return "unknown"
    trusted = any(peer_ip in ip_network(network) for network in trusted_proxy_networks)
    if not trusted:
        return str(peer_ip)
    forwarded = request.headers.get("x-forwarded-for", "")
    candidates = []
    for value in forwarded.split(","):
        try:
            candidates.append(ip_address(value.strip()))
        except ValueError:
            continue
    for candidate in reversed(candidates):
        if not any(candidate in ip_network(network) for network in trusted_proxy_networks):
            return str(candidate)
    return str(peer_ip)


@dataclass
class RateLimiter:
    store: RateLimitStore

    async def enforce(self, request: Request, *, key: str, limit: int, window_seconds: int) -> None:
        allowed, retry_after = await self.store.hit(key, limit=limit, window_seconds=window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"code": "rate_limit_exceeded", "message": "Too many requests; retry later."},
                headers={"Retry-After": str(retry_after)},
            )
