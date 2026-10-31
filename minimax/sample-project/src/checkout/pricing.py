"""折扣计算(SPEC-002 折扣规则)。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
MIN_DISCOUNT_PERCENT = Decimal("0")
MAX_DISCOUNT_PERCENT = Decimal("50")
HUNDRED = Decimal("100")


def apply_discount(total: Decimal, percent: Decimal) -> Decimal:
    """对订单总额按百分比打折,结果保留两位小数。

    SPEC-002 约束:折扣百分比必须在 [0, 50] 区间内(含边界),
    超出范围抛出 ValueError。
    """
    if percent < MIN_DISCOUNT_PERCENT or percent > MAX_DISCOUNT_PERCENT:
        raise ValueError(f"折扣百分比必须在 [{MIN_DISCOUNT_PERCENT}, {MAX_DISCOUNT_PERCENT}] 内,收到 {percent}")
    discounted = total * (HUNDRED - percent) / HUNDRED
    return discounted.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
