## _section_guide
Common imports and utilities available in strategy files.

## common_imports
```python
# Core imports
import qengine.indicators as ta        # 170+ indicators
from qengine.strategies import Strategy  # base class
import qengine.helpers as jh            # utility helpers
import numpy as np                      # arrays

# Caching (recompute once per candle, not per call)
from qengine.services.cache import cached

# Logging in strategies
self.log("Entry signal fired", "info")

# Environment checks
jh.is_live()         # True in livetrade AND papertrade
jh.is_livetrading()  # True ONLY in livetrade mode
jh.is_backtesting()  # True in backtest mode
```
