from qengine.enums import brokers
from .OandaMain import OandaMain


class OandaForex(OandaMain):
    def __init__(self) -> None:
        super().__init__(
            name=brokers.OANDA,
            practice=False,
        )


class OandaDemoForex(OandaMain):
    def __init__(self) -> None:
        super().__init__(
            name=brokers.OANDA_DEMO,
            practice=True,
        )
