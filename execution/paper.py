from uuid import uuid4

from execution.base import (
    ExecutionAdapter,
    OrderRequest,
)


class PaperExecutionAdapter(
    ExecutionAdapter
):

    def __init__(self):

        self.orders: dict[
            str,
            OrderRequest
        ] = {}

    def place_order(
        self,
        order: OrderRequest,
    ) -> str:

        order_id = (
            f"PAPER-"
            f"{uuid4().hex[:10].upper()}"
        )

        self.orders[
            order_id
        ] = order

        return order_id

    def modify_stop(
        self,
        order_id: str,
        new_stop: float,
    ) -> bool:

        if order_id not in self.orders:
            return False

        old = self.orders[
            order_id
        ]

        self.orders[
            order_id
        ] = OrderRequest(
            symbol=old.symbol,
            direction=old.direction,
            quantity=old.quantity,
            entry=old.entry,
            stop_loss=new_stop,
            take_profit=old.take_profit,
        )

        return True

    def close_order(
        self,
        order_id: str,
    ) -> bool:

        if order_id not in self.orders:
            return False

        del self.orders[
            order_id
        ]

        return True