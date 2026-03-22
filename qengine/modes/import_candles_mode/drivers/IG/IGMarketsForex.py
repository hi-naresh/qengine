from qengine.enums import brokers
from .IGMarketsMain import IGMarketsMain


class IGMarketsForex(IGMarketsMain):
    def __init__(self) -> None:
        super().__init__(
            name=brokers.IG_MARKETS,
            demo=False,
        )


class IGMarketsDemoForex(IGMarketsMain):
    def __init__(self) -> None:
        super().__init__(
            name=brokers.IG_MARKETS_DEMO,
            demo=True,
        )
