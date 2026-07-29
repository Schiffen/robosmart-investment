"""Errors shared by every market-data provider.

Lives in its own module so `live` and `fixture` can both raise the identical
class without importing each other, and so `data_layer` can re-export it
without pulling a provider in.
"""

from __future__ import annotations


class TickerNotFoundError(Exception):
    """Raised only when a ticker has no price history at all.

    Deliberately narrow: missing fundamentals, empty news, or an absent sector
    are NOT this error. Partial data is normal and every provider returns it
    with None-filled keys rather than failing the whole context.
    """
