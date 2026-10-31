"""SPEC-002 折扣规则的回归测试。"""

from decimal import Decimal

import pytest

from checkout.pricing import apply_discount


def test_discount_reduces_total():
    assert apply_discount(Decimal("100.00"), Decimal("10")) == Decimal("90.00")


def test_discount_zero_keeps_total():
    assert apply_discount(Decimal("100.00"), Decimal("0")) == Decimal("100.00")


def test_discount_upper_boundary_allowed():
    assert apply_discount(Decimal("100.00"), Decimal("50")) == Decimal("50.00")


def test_discount_over_upper_boundary_rejected():
    with pytest.raises(ValueError):
        apply_discount(Decimal("100.00"), Decimal("50.01"))


def test_discount_negative_rejected():
    with pytest.raises(ValueError):
        apply_discount(Decimal("100.00"), Decimal("-1"))
