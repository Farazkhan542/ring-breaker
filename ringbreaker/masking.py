"""Consortium masking service. Account IDs never cross banks in the clear, only HMAC-SHA256 pseudonyms.

The key is held by the consortium operator (Secret Manager in production); banks call mask() as a service and
can only reverse the pseudonyms of their own customers, by masking their own account list.
"""
import hashlib
import hmac

from . import config


def mask(account_id: str) -> str:
    return "M-" + hmac.new(config.CONSORTIUM_KEY, account_id.encode(), hashlib.sha256).hexdigest()[:12]


def amount_band(amount: float) -> str:
    """Coarse amount band shared instead of exact amounts."""
    edges = [0, 1000, 3000, 5000, 8000, 10000, 20000, 50000]
    for lo, hi in zip(edges, edges[1:]):
        if amount < hi:
            return f"{lo // 1000}k-{hi // 1000}k" if lo else f"<{hi // 1000}k"
    return ">=50k"


def time_window(ts) -> str:
    """Six-hour window shared instead of exact timestamps."""
    h = (ts.hour // 6) * 6
    return f"{ts:%Y-%m-%d} {h:02d}:00-{h + 6:02d}:00"
