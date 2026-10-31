"""Analyzer v1 与任务标识符抽取测试。"""

from sddctx.analyzer import analyze_text, analyze_terms, extract_identifiers


def test_english_words_kept():
    # 词序保持出现顺序;大小写统一 casefold。
    assert analyze_text("OrderService min_total filter") == "orderservice min_total filter"


def test_casefold_and_nfc():
    assert analyze_text("Min_TOTAL") == "min_total"


def test_cjk_unigrams_and_bigrams():
    terms = analyze_terms("订单查询")
    assert "u_8ba2" in terms          # 订
    assert "u_5355" in terms          # 单
    assert "b_8ba2_5355" in terms     # 订单
    assert "b_5355_67e5" in terms     # 单查
    assert "订单" not in " ".join(terms)  # 原文串不直接作为词


def test_mixed_text():
    terms = analyze_text("为 customer_orders 增加最小金额筛选")
    assert "customer_orders" in terms
    assert "b_6700_5c0f" in terms     # 最小


def test_dedup_preserves_order():
    # 词序保持出现顺序,且同一词只保留一次(CJK 单字/二元词同样去重)。
    assert analyze_text("查询 查询 订单") == " ".join(dict.fromkeys(analyze_terms("查询 查询 订单")))
    assert analyze_text("查询 查询 订单") == analyze_text("查询 订单")


def test_extract_identifiers_snake_and_camel():
    identifiers = extract_identifiers("在 customer_orders 中支持 minTotal 参数")
    assert "customer_orders" in identifiers
    assert "minTotal" in identifiers


def test_extract_identifiers_skips_plain_words_and_short():
    identifiers = extract_identifiers("add a filter for min values")
    assert identifiers == []  # 纯小写普通词与过短词不算标识符
