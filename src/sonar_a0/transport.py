from __future__ import annotations

import hashlib
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from .models import Status

USER_AGENT = "SONAR-A0/0.1 (+https://github.com/Batuhxn/SONAR)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FetchError(Exception):
    def __init__(self, status: Status, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Document:
    url: str
    text: str
    fetched_at: str
    sha256: str


@dataclass
class RobotsPolicy:
    rules: list[tuple[bool, str]]
    crawl_delay: float = 0

    @classmethod
    def parse(cls, text: str, agent: str = "SONAR-A0") -> RobotsPolicy:
        groups: list[tuple[list[str], list[tuple[bool, str]], float]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        delay = 0.0
        has_directives = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if has_directives:
                    groups.append((agents, rules, delay))
                    agents, rules, delay, has_directives = [], [], 0.0, False
                agents.append(value.lower())
            elif agents and key in {"allow", "disallow", "crawl-delay"}:
                has_directives = True
                if key == "crawl-delay":
                    try:
                        delay = max(0.0, float(value))
                    except ValueError:
                        pass
                elif value:
                    rules.append((key == "allow", value))
        if agents:
            groups.append((agents, rules, delay))
        specific = [group for group in groups if any(a != "*" and a in agent.lower() for a in group[0])]
        if specific:
            longest = max(len(a) for group in specific for a in group[0] if a in agent.lower())
            selected = [g for g in specific if any(len(a) == longest and a in agent.lower() for a in g[0])]
        else:
            selected = [group for group in groups if "*" in group[0]]
        return cls([rule for group in selected for rule in group[1]], max((g[2] for g in selected), default=0.0))

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        matches: list[tuple[int, bool]] = []
        for allow, pattern in self.rules:
            end = pattern.endswith("$")
            core = pattern[:-1] if end else pattern
            expression = "^" + ".*".join(re.escape(p) for p in core.split("*")) + ("$" if end else "")
            if re.search(expression, target):
                matches.append((len(core.replace("*", "")), allow))
        return max(matches, default=(0, True))[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient:
    """Sequential, cookie-free requests; robots and redirect targets checked before I/O.

    A0 intentionally does not retry 403/429, change identity, or use private APIs.
    Evidence stores body hashes, not credentials or response headers/cookies.
    """

    def __init__(self, allowed_hosts: set[str], timeout: float = 15, delay: float = 2):
        if timeout <= 0 or delay < 2:
            raise ValueError("timeout must be positive; request delay must be at least 2 seconds")
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout
        self.delay = delay
        self.evidence: list[dict] = []
        self.policies: dict[str, RobotsPolicy] = {}
        self.last_request: dict[str, float] = {}
        self.opener = urllib.request.build_opener(NoRedirect())

    def validate_url(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self.allowed_hosts or parts.username or parts.password or parts.port not in {None, 443}:
            raise FetchError(Status.BLOCKED, "Only HTTPS URLs on the selected supplier's approved hosts are allowed")
        return parts.netloc

    def _raw(self, url: str, crawl_delay: float = 0) -> tuple[int, dict, bytes, str]:
        host = self.validate_url(url)
        wait = max(self.delay, crawl_delay) - (time.monotonic() - self.last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self.last_request[host] = time.monotonic()
        record = {"url": url, "attempted": True, "fetched_at": utc_now()}
        self.evidence.append(record)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise FetchError(Status.PARSE_ERROR, "Response exceeds the 5 MB safety limit")
                headers = dict(response.headers)
                status = response.status
        except urllib.error.HTTPError as error:
            data = error.read(5_000_001)
            headers = dict(error.headers)
            status = error.code
        except (TimeoutError, socket.timeout) as error:
            record.update(status=Status.TIMEOUT, message=str(error))
            raise FetchError(Status.TIMEOUT, "Supplier request timed out") from error
        except urllib.error.URLError as error:
            status = Status.TIMEOUT if isinstance(error.reason, (TimeoutError, socket.timeout)) else Status.NETWORK_ERROR
            record.update(status=status, message=str(error.reason))
            raise FetchError(status, "Supplier request failed: " + str(error.reason)) from error
        except FetchError as error:
            record.update(status=error.status, message=str(error))
            raise
        except OSError as error:
            record.update(status=Status.NETWORK_ERROR, message=str(error))
            raise FetchError(Status.NETWORK_ERROR, "Supplier connection failed") from error
        record.update(http_status=status, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        record["fetched_at"] = utc_now()
        return status, {key.lower(): value for key, value in headers.items()}, data, record["fetched_at"]

    def policy(self, url: str) -> RobotsPolicy:
        host = self.validate_url(url)
        if host not in self.policies:
            robots_url = f"https://{host}/robots.txt"
            try:
                status, headers, data, _ = self._raw(robots_url)
            except FetchError as error:
                raise FetchError(Status.ROBOTS_UNAVAILABLE, "Cannot verify robots.txt: " + str(error)) from error
            if status in {404, 410}:
                policy = RobotsPolicy([])
            elif status == 200 and "<html" not in data[:500].decode("utf-8", errors="ignore").lower():
                policy = RobotsPolicy.parse(data.decode("utf-8-sig", errors="replace"))
            else:
                raise FetchError(Status.ROBOTS_UNAVAILABLE, f"robots.txt returned HTTP {status} or unexpected content; failing closed")
            self.policies[host] = policy
        return self.policies[host]

    def get(self, url: str) -> Document:
        for _ in range(6):
            policy = self.policy(url)
            if not policy.allows(url):
                self.evidence.append({"url": url, "attempted": False, "checked_at": utc_now(), "status": Status.ROBOTS_DISALLOWED})
                raise FetchError(Status.ROBOTS_DISALLOWED, "robots.txt disallows this URL; no request sent")
            status, headers, data, stamp = self._raw(url, policy.crawl_delay)
            if status in {301, 302, 303, 307, 308}:
                if "location" not in headers:
                    raise FetchError(Status.HTTP_ERROR, "Redirect has no Location")
                url = urljoin(url, headers["location"])
                self.validate_url(url)
                continue
            if status == 404:
                raise FetchError(Status.NOT_FOUND, "Supplier returned HTTP 404")
            if status in {401, 403}:
                raise FetchError(Status.BLOCKED, f"Supplier returned HTTP {status}; no bypass attempted")
            if status == 429:
                raise FetchError(Status.RATE_LIMITED, "HTTP 429; stop and respect Retry-After: " + headers.get("retry-after", "unspecified"))
            if status != 200:
                raise FetchError(Status.HTTP_ERROR, f"Supplier returned HTTP {status}")
            if "text/html" not in headers.get("content-type", ""):
                raise FetchError(Status.PARSE_ERROR, "Expected a public HTML page")
            charset = re.search(r"charset=([^;\s]+)", headers.get("content-type", ""), re.I)
            try:
                text = data.decode(charset.group(1).strip('"') if charset else "utf-8")
            except (UnicodeError, LookupError) as error:
                raise FetchError(Status.PARSE_ERROR, "Cannot decode the supplier response") from error
            lower = text.lower()
            if any(marker in lower for marker in ("cf-chl-", "<title>just a moment", "<title>access denied", 'id="captcha"')):
                raise FetchError(Status.BLOCKED, "Challenge page detected; no bypass attempted")
            return Document(url, text, stamp, hashlib.sha256(data).hexdigest())
        raise FetchError(Status.HTTP_ERROR, "Too many redirects")
