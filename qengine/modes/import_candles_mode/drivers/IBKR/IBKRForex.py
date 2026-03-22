from qengine.enums import brokers
from .IBKRMain import IBKRMain


class IBKRForex(IBKRMain):
    def __init__(self) -> None:
        super().__init__(
            name=brokers.IBKR,
            port=7497,  # TWS live
        )


class IBKRPaperForex(IBKRMain):
    def __init__(self) -> None:
        super().__init__(
            name=brokers.IBKR_PAPER,
            port=7497,  # TWS paper (same port, different account)
        )
