import io
import unittest
import urllib.error
from unittest.mock import Mock, patch

from sonar_a0.models import Status
from sonar_a0.transport import FetchError, HttpClient, RobotsPolicy


class Response:
    def __init__(self, body=b"<html>product</html>", status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {"Content-Type":"text/html; charset=utf-8"}
    def read(self, limit): return self.body[:limit]
    def __enter__(self): return self
    def __exit__(self, *args): return False


class RobotsTests(unittest.TestCase):
    def test_wildcards_forbidden_search_and_api(self):
        policy = RobotsPolicy.parse("User-agent: *\nCrawl-delay: 3\nDisallow: /*search=\nDisallow: /api/\nAllow: /api/public$")
        self.assertFalse(policy.allows("https://www.ozdisan.com/c?search=LM358P"))
        self.assertFalse(policy.allows("https://www.ozdisan.com/api/data"))
        self.assertTrue(policy.allows("https://www.ozdisan.com/p/product"))
        self.assertTrue(policy.allows("https://www.ozdisan.com/api/public"))
        self.assertFalse(policy.allows("https://www.ozdisan.com/api/public/private"))
        self.assertEqual(policy.crawl_delay,3)

    def test_user_agent_groups_are_not_confused(self):
        text = "User-agent: Python\nDisallow: /\n\nUser-agent: *\nAllow: /\nDisallow: /srv/\n\nUser-agent: SONAR-A0\nDisallow: /private"
        self.assertTrue(RobotsPolicy.parse(text).allows("https://www.direnc.net/arama?q=LM358P"))
        self.assertFalse(RobotsPolicy.parse(text).allows("https://www.direnc.net/private"))
        self.assertFalse(RobotsPolicy.parse(text,agent="Python").allows("https://www.direnc.net/"))

    def test_equal_length_allow_wins(self):
        policy = RobotsPolicy.parse("User-agent: *\nAllow: /same\nDisallow: /same")
        self.assertTrue(policy.allows("https://www.direnc.net/same"))


class TransportTests(unittest.TestCase):
    def client(self):
        client = HttpClient({"www.direnc.net"})
        client.policies["www.direnc.net"] = RobotsPolicy([])
        return client

    def test_robots_disallowed_sends_no_product_request(self):
        client = self.client()
        client.policies["www.direnc.net"] = RobotsPolicy.parse("User-agent: *\nDisallow: /arama")
        client.opener = Mock()
        with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/arama?q=TEST")
        self.assertEqual(ctx.exception.status,Status.ROBOTS_DISALLOWED)
        client.opener.open.assert_not_called()
        self.assertFalse(client.evidence[-1]["attempted"])

    def test_robots_unavailable_fails_closed(self):
        client = HttpClient({"www.direnc.net"})
        client.opener = Mock()
        client.opener.open.side_effect = TimeoutError("timeout")
        with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/product")
        self.assertEqual(ctx.exception.status,Status.ROBOTS_UNAVAILABLE)
        self.assertEqual(client.opener.open.call_count,1)

    def test_robots_404_allows_following_request(self):
        client = HttpClient({"www.direnc.net"})
        client.opener = Mock()
        client.opener.open.side_effect = [urllib.error.HTTPError("https://www.direnc.net/robots.txt",404,"missing",{},io.BytesIO(b"missing")),Response()]
        with patch("sonar_a0.transport.time.sleep"):
            self.assertIn("product",client.get("https://www.direnc.net/product").text)

    def test_hash_timestamp_and_status_recorded(self):
        client = self.client()
        client.opener = Mock()
        client.opener.open.return_value = Response()
        document = client.get("https://www.direnc.net/product")
        self.assertEqual(len(document.sha256),64)
        self.assertIn("+00:00",document.fetched_at)
        self.assertEqual(client.evidence[-1]["http_status"],200)

    def test_timeout_and_network_failure(self):
        for error,status in [(TimeoutError(),Status.TIMEOUT),(urllib.error.URLError(TimeoutError()),Status.TIMEOUT),(urllib.error.URLError("dns"),Status.NETWORK_ERROR)]:
            client = self.client()
            client.opener = Mock()
            client.opener.open.side_effect = error
            with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/product")
            self.assertEqual(ctx.exception.status,status)

    def test_http_failures_and_no_retry(self):
        for code,status in [(403,Status.BLOCKED),(401,Status.BLOCKED),(404,Status.NOT_FOUND),(429,Status.RATE_LIMITED),(500,Status.HTTP_ERROR)]:
            client = self.client()
            client.opener = Mock()
            client.opener.open.side_effect = urllib.error.HTTPError("https://www.direnc.net/product",code,"error",{"Retry-After":"30"},io.BytesIO(b"error"))
            with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/product")
            self.assertEqual(ctx.exception.status,status)
            self.assertEqual(client.opener.open.call_count,1)

    def test_redirect_target_checked_before_request(self):
        client = self.client()
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError("https://www.direnc.net/product",302,"redirect",{"Location":"https://other.test/private"},io.BytesIO())
        with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/product")
        self.assertEqual(ctx.exception.status,Status.BLOCKED)
        self.assertEqual(client.opener.open.call_count,1)

    def test_redirect_to_disallowed_path_checked(self):
        client = self.client()
        client.policies["www.direnc.net"] = RobotsPolicy.parse("User-agent: *\nDisallow: /srv/")
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError("https://www.direnc.net/product",302,"redirect",{"Location":"/srv/private"},io.BytesIO())
        with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/product")
        self.assertEqual(ctx.exception.status,Status.ROBOTS_DISALLOWED)
        self.assertEqual(client.opener.open.call_count,1)

    def test_non_html_and_challenge_page(self):
        for response,status in [(Response(b"{}",headers={"Content-Type":"application/json"}),Status.PARSE_ERROR),(Response(b"<html><title>Just a moment</title>cf-chl-test</html>"),Status.BLOCKED)]:
            client=self.client()
            client.opener=Mock()
            client.opener.open.return_value=response
            with self.assertRaises(FetchError) as ctx: client.get("https://www.direnc.net/product")
            self.assertEqual(ctx.exception.status,status)

    def test_host_scheme_and_credentials_rejected(self):
        client=self.client()
        for url in ["http://www.direnc.net/p","https://other.test/p","https://user:pass@www.direnc.net/p","https://www.direnc.net:444/p"]:
            with self.assertRaises(FetchError): client.validate_url(url)

    def test_minimum_delay_and_crawl_delay(self):
        client=self.client()
        client.policies["www.direnc.net"] = RobotsPolicy([],3)
        client.last_request["www.direnc.net"] = 100
        client.opener=Mock()
        client.opener.open.return_value=Response()
        with patch("sonar_a0.transport.time.monotonic",return_value=101),patch("sonar_a0.transport.time.sleep") as sleep:
            client.get("https://www.direnc.net/p")
            sleep.assert_called_once_with(2)
        with self.assertRaises(ValueError): HttpClient({"www.direnc.net"},delay=0)
