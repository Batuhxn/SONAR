from .base import SupplierAdapter
from .direnc import DirencAdapter
from .ozdisan import OzdisanAdapter

ADAPTERS = {"ozdisan": OzdisanAdapter, "direnc": DirencAdapter}

__all__ = ["SupplierAdapter", "DirencAdapter", "OzdisanAdapter", "ADAPTERS"]
