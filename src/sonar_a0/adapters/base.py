from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Offer, Result, Status
from ..transport import Document, FetchError, HttpClient


class SupplierAdapter(ABC):
    name: str
    hosts: set[str]

    def __init__(self, client: HttpClient | None = None):
        self.client = client or HttpClient(self.hosts)

    @abstractmethod
    def search(self, mpn: str, *, limit: int = 5) -> Result:
        """Discover URLs from a supplier search response, then retrieve public offers."""

    @abstractmethod
    def parse_product(self, document: Document, query: str | None = None) -> Offer:
        """Pure normalization; no network access or implicit part substitution."""

    def product(self, url: str, *, mpn: str | None = None) -> Result:
        start = len(self.client.evidence)
        try:
            document = self.client.get(url)
            offer = self.parse_product(document, mpn)
            result = Result(self.name, "product", mpn, Status.PARTIAL if offer.warnings else Status.OK, [offer])
        except FetchError as error:
            result = Result(self.name, "product", mpn, error.status, message=str(error))
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            result = Result(self.name, "product", mpn, Status.PARSE_ERROR, message="Supplier format not recognized: " + str(error))
        result.evidence = self.client.evidence[start:]
        return result

    def health(self) -> Result:
        start = len(self.client.evidence)
        try:
            self.client.policy("https://" + sorted(self.hosts, key=len, reverse=True)[0] + "/")
            result = Result(self.name, "health", None, Status.OK, message="robots.txt readable; product/search availability not implied")
        except FetchError as error:
            result = Result(self.name, "health", None, error.status, message=str(error))
        result.evidence = self.client.evidence[start:]
        return result
