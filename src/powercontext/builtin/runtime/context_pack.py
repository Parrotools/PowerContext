# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Prefix-reusing context packs with verifiable incremental transport."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
DEFAULT_CHUNK_BYTES = 512
_PACK_KEYS = frozenset({"schema", "items", "digest", "byte_count"})
_DELTA_KEYS = frozenset({"schema", "base_digest", "target_digest", "prefix_items", "appended"})


class ContextPackError(ValueError):
    """Raise for pack, chunking, delta, or reconstruction protocol violations."""


def _canonical(payload: Mapping[str, object], /) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _encode_items(items: tuple[bytes, ...], /) -> list[str]:
    return [base64.b64encode(item).decode("ascii") for item in items]


def _decode_items(values: object, /) -> tuple[bytes, ...]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        message = "items must be an array of base64 strings"
        raise ContextPackError(message)
    strings = [value for value in values if isinstance(value, str)]
    try:
        decoded = tuple(base64.b64decode(value, validate=True) for value in strings)
    except (binascii.Error, ValueError) as error:
        message = "items must contain valid base64 strings"
        raise ContextPackError(message) from error
    if _encode_items(decoded) != values:
        message = "items must contain canonical base64 strings"
        raise ContextPackError(message)
    return decoded


def _require_digest(value: object, field: str, /) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        message = f"{field} must be a sha256:<hex> digest string"
        raise ContextPackError(message)
    hex_part = value.removeprefix("sha256:")
    if any(char not in "0123456789abcdef" for char in hex_part):
        message = f"{field} must be a sha256:<hex> digest string"
        raise ContextPackError(message)
    return value


@dataclass(frozen=True, slots=True)
class ContextPack:
    """One complete context payload as bounded, verifiable chunks."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: Iterable[bytes], /) -> ContextPack:
        """Construct one pack from its chunk items and seal digest and byte count."""

        materialized = tuple(items)
        if any(not isinstance(item, bytes) for item in materialized):
            message = "pack items must be bytes"
            raise ContextPackError(message)
        payload = {"schema": PACK_SCHEMA, "items": _encode_items(materialized)}
        digest = "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()
        sealed = {**payload, "digest": digest}
        count = 0
        for _ in range(32):
            candidate = {**sealed, "byte_count": count}
            length = len(_canonical(candidate))
            if length == count:
                return cls(items=materialized, digest=digest, byte_count=count)
            count = length
        message = "pack byte count did not converge"
        raise ContextPackError(message)

    @classmethod
    def from_content(cls, content: str, /, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> ContextPack:
        """Chunk UTF-8 text deterministically within the caller's byte bound."""

        if not isinstance(content, str):
            message = "content must be a string"
            raise ContextPackError(message)
        if type(chunk_bytes) is not int or chunk_bytes < 1:
            message = "chunk_bytes must be a positive integer"
            raise ContextPackError(message)
        items: list[bytes] = []
        current = bytearray()
        for character in content:
            encoded = character.encode("utf-8")
            if len(encoded) > chunk_bytes:
                message = "chunk_bytes cannot hold one UTF-8 character"
                raise ContextPackError(message)
            if len(current) + len(encoded) > chunk_bytes:
                items.append(bytes(current))
                current = bytearray()
            current.extend(encoded)
        if current:
            items.append(bytes(current))
        return cls.build(tuple(items))

    def to_bytes(self, /) -> bytes:
        """Serialize the complete pack as canonical JSON."""

        return _canonical({
            "schema": PACK_SCHEMA,
            "items": _encode_items(self.items),
            "digest": self.digest,
            "byte_count": self.byte_count,
        })

    @classmethod
    def from_bytes(cls, data: bytes, /) -> ContextPack:
        """Decode and fully verify one canonical serialized pack."""

        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            message = "pack must be canonical UTF-8 JSON"
            raise ContextPackError(message) from error
        if not isinstance(payload, dict) or set(payload) != _PACK_KEYS:
            message = "pack fields must be exactly schema, items, digest, byte_count"
            raise ContextPackError(message)
        if payload["schema"] != PACK_SCHEMA:
            message = "pack schema mismatch"
            raise ContextPackError(message)
        items = _decode_items(payload["items"])
        digest = _require_digest(payload["digest"], "digest")
        expected = (
            "sha256:" + hashlib.sha256(_canonical({"schema": PACK_SCHEMA, "items": payload["items"]})).hexdigest()
        )
        if digest != expected:
            message = "pack digest does not match its items"
            raise ContextPackError(message)
        count = payload["byte_count"]
        if type(count) is not int or count < 0:
            message = "byte_count must be a non-negative integer"
            raise ContextPackError(message)
        if count != len(_canonical(payload)):
            message = "byte_count does not match the canonical serialized length"
            raise ContextPackError(message)
        return cls(items=items, digest=digest, byte_count=count)


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """One incremental step reusing a verified base-pack prefix."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    def __post_init__(self) -> None:
        _require_digest(self.base_digest, "base_digest")
        _require_digest(self.target_digest, "target_digest")
        if type(self.prefix_items) is not int or self.prefix_items < 0:
            message = "prefix_items must be a non-negative integer"
            raise ContextPackError(message)
        if any(not isinstance(item, bytes) for item in self.appended):
            message = "appended items must be bytes"
            raise ContextPackError(message)

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack, /) -> ContextPackDelta:
        """Select a valid shared prefix and carry the target-only suffix."""

        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            message = "delta endpoints must be ContextPack values"
            raise ContextPackError(message)
        limit = min(len(base.items), len(target.items))
        prefix = 0
        while prefix < limit and base.items[prefix] == target.items[prefix]:
            prefix += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=prefix,
            appended=target.items[prefix:],
        )

    @property
    def byte_count(self, /) -> int:
        return len(self.to_bytes())

    def to_bytes(self, /) -> bytes:
        """Serialize the delta as canonical JSON."""

        return _canonical({
            "schema": DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": _encode_items(self.appended),
        })

    @classmethod
    def from_bytes(cls, data: bytes, /) -> ContextPackDelta:
        """Decode and structurally verify one canonical serialized delta."""

        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            message = "delta must be canonical UTF-8 JSON"
            raise ContextPackError(message) from error
        if not isinstance(payload, dict) or set(payload) != _DELTA_KEYS:
            message = "delta fields must be exactly schema, base_digest, target_digest, prefix_items, appended"
            raise ContextPackError(message)
        if payload["schema"] != DELTA_SCHEMA:
            message = "delta schema mismatch"
            raise ContextPackError(message)
        base_digest = _require_digest(payload["base_digest"], "base_digest")
        target_digest = _require_digest(payload["target_digest"], "target_digest")
        prefix = payload["prefix_items"]
        if type(prefix) is not int or prefix < 0:
            message = "prefix_items must be a non-negative integer"
            raise ContextPackError(message)
        appended = _decode_items(payload["appended"])
        return cls(
            base_digest=base_digest,
            target_digest=target_digest,
            prefix_items=prefix,
            appended=appended,
        )


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta, /) -> ContextPack:
    """Verify one delta against its base and rebuild the target pack."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        message = "apply requires a ContextPack base and ContextPackDelta"
        raise ContextPackError(message)
    if delta.base_digest != base.digest:
        message = "delta base digest does not match the supplied base pack"
        raise ContextPackError(message)
    if delta.prefix_items > len(base.items):
        message = "delta prefix exceeds the base pack chunk count"
        raise ContextPackError(message)
    rebuilt = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if rebuilt.digest != delta.target_digest:
        message = "rebuilt pack digest does not match the delta target"
        raise ContextPackError(message)
    return rebuilt


__all__ = [
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
