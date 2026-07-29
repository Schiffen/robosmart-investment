"""market_data — Contract B providers.

    live.py     yfinance, the production source
    fixture.py  replay of a recorded snapshot, for offline runs
    refresh.py  records the snapshot

Import the providers directly (`from market_data import live`) when you mean a
specific one. For mode-aware access, go through the top-level `data_layer`
facade, which dispatches per call.
"""

from market_data.errors import TickerNotFoundError

__all__ = ["TickerNotFoundError"]
