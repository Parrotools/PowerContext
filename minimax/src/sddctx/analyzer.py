"""Analyzer v1:把任意文本(含中文)拆成空格分隔的检索词,供 seekdb 全文索引使用。

与 PowerContext 的 Analyzer v1 同思路:
- 英文/数字/下划线连续串作为一个词;
- CJK 字符拆成单字词(u_<码点>)与相邻二元词(b_<码点>_<码点>),保证中文子串可命中;
- 统一 NFC 规范化 + casefold。
"""

from __future__ import annotations

import re
import unicodedata

_CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
)


def _is_cjk(character: str) -> bool:
    code = ord(character)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def analyze_terms(value: str) -> list[str]:
    """返回去重前的词序列(保持出现顺序)。"""
    normalized = unicodedata.normalize("NFC", value).casefold()
    terms: list[str] = []
    cjk: list[tuple[str, int]] = []
    word_start: int | None = None

    def flush_word(end: int) -> None:
        nonlocal word_start
        if word_start is not None:
            terms.append(normalized[word_start:end])
            word_start = None

    def flush_cjk() -> None:
        if not cjk:
            return
        for character, position in cjk:
            terms.append(f"u_{ord(character):x}")
        for (left, _), (right, _) in zip(cjk, cjk[1:]):
            terms.append(f"b_{ord(left):x}_{ord(right):x}")
        cjk.clear()

    for position, character in enumerate(normalized):
        if _is_cjk(character):
            flush_word(position)
            cjk.append((character, position))
        elif character.isalnum() or character == "_":
            flush_cjk()
            if word_start is None:
                word_start = position
        else:
            flush_word(position)
            flush_cjk()
    flush_word(len(normalized))
    flush_cjk()
    return terms


def analyze_text(value: str) -> str:
    """返回空格分隔、去重后的检索词串。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for term in analyze_terms(value):
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return " ".join(ordered)


def extract_identifiers(value: str) -> list[str]:
    """从任务文本中抽取可能的代码标识符。

    只保留“像标识符”的词:snake_case(含下划线)或 camelCase(含大写)的
    英文数字串,长度 >= 4;纯小写普通单词不算,避免把任务描述里的每个英文
    词都当标识符。在未 casefold 的原文上匹配,保留大小写信息。
    """
    identifiers: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]{3,}", unicodedata.normalize("NFC", value)):
        term = match.group(0)
        looks_like_identifier = "_" in term or any(character.isupper() for character in term)
        if looks_like_identifier and term not in seen:
            seen.add(term)
            identifiers.append(term)
    return identifiers
