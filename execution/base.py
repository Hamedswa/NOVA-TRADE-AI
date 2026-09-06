from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.models import Direction


@dataclass(frozen=True)
class OrderRequest:

    symbol: str

    direction: Direction

    quantity: float

    entry: float

    stop_loss: float

    take_profit: float


class ExecutionAdapter(ABC):

    """
    Interface commune pour les futures connexions :

    Forex :
        MetaTrader / broker API

    Crypto :
        Binance / Bybit / OKX / autre exchange

    Le moteur de stratégie ne connaîtra jamais
    directement les détails du broker.
    """

    @abstractmethod
    def place_order(
        self,
        order: OrderRequest,
    ) -> str:

        raise NotImplementedError

    @abstractmethod
    def modify_stop(
        self,
        order_id: str,
        new_stop: float,
    ) -> bool:

        raise NotImplementedError

    @abstractmethod
    def close_order(
        self,
        order_id: str,
    ) -> bool:

        raise NotImplementedError