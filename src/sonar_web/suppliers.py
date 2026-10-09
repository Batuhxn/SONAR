"""A1 facade retains A0 policy checks, host restrictions and process-wide pacing."""
from __future__ import annotations

import ipaddress
import socket
import threading
from urllib.parse import urlsplit

from sonar_a0.adapters import ADAPTERS


class SupplierService:
    def __init__(self):
        self.adapters = {key: cls() for key, cls in ADAPTERS.items()}
        self.lock = threading.Lock()

    def validate_url(self, supplier: str, url: str):
        adapter = self.adapters[supplier]
        adapter.client.validate_url(url)
        if len(url) > 2000 or any(ord(c) < 32 for c in url) or urlsplit(url).fragment:
            raise ValueError("Use a supplier HTTPS product URL without fragments or control characters")

    def retrieve(self, supplier: str, mpn: str, url: str | None = None) -> dict:
        with self.lock:
            adapter = self.adapters[supplier]
            if url:
                self.validate_url(supplier, url)
            # Fixed, allowlisted supplier domains only; fail closed on private DNS answers.
            for host in adapter.hosts:
                addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                    raise ValueError("Supplier DNS resolved to a non-public address")
            # Recheck policies each job while keeping the same transport pacing clock.
            adapter.client.policies.clear()
            adapter.client.evidence.clear()
            result = adapter.product(url, mpn=mpn or None) if url else adapter.search(mpn, limit=3)
            return result.to_dict()
