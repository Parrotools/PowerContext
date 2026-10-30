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

"""Cross-call embedding request coalescing with a bounded LRU vector cache."""

from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from dataclasses import dataclass, field

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage


def _merge_usage(total: InferenceUsage, addition: InferenceUsage | None, /) -> InferenceUsage:
    if addition is None:
        return total
    total.requests += addition.requests
    for name in ("input_tokens", "output_tokens"):
        value = getattr(addition, name)
        if value is not None:
            setattr(total, name, (getattr(total, name) or 0) + value)
    return total


@dataclass
class _SharedBatch:
    """One in-flight underlying request shared by every waiting caller."""

    texts: list[str] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    full_event: asyncio.Event = field(default_factory=asyncio.Event)
    completed: asyncio.Event = field(default_factory=asyncio.Event)
    dispatched: bool = False
    scheduled: bool = False
    result: dict[str, tuple[float, ...]] | None = None
    usage: InferenceUsage | None = None
    error: BaseException | None = None


class CoalescingEmbeddingModel:
    """Deduplicate, batch, share, and cache embedding work across callers."""

    def __init__(
        self,
        base_model,
        /,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if type(max_batch_size) is not int or max_batch_size < 1:
            message = "max_batch_size must be a positive integer"
            raise ValueError(message)
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, (int, float)) or coalesce_ms < 0:
            message = "coalesce_ms must be a non-negative number"
            raise ValueError(message)
        if type(cache_size) is not int or cache_size < 0:
            message = "cache_size must be a non-negative integer"
            raise ValueError(message)
        self._base = base_model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = coalesce_ms / 1000.0
        self._cache_size = cache_size
        self._lock = asyncio.Lock()
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._index: dict[str, _SharedBatch] = {}
        self._open_batch: _SharedBatch | None = None

    @property
    def profile(self):
        return self._base.profile

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        """Return one vector per input text, sharing batches and cached work."""

        sequence = tuple(texts)
        if not sequence:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        async with self._lock:
            vector_map, batches = self._collect(sequence)

        for batch in batches:
            await batch.completed.wait()

        usage = InferenceUsage(requests=0)
        for batch in batches:
            if batch.error is not None:
                raise batch.error
            if batch.result is None:
                message = "embedding batch completed without a result"
                raise ValueError(message)
            _merge_usage(usage, batch.usage)
            vector_map.update(batch.result)
        return EmbeddingResult(vectors=tuple(vector_map[text] for text in sequence), usage=usage)

    def _collect(self, sequence: tuple[str, ...]) -> tuple[dict[str, tuple[float, ...]], list[_SharedBatch]]:
        vector_map: dict[str, tuple[float, ...]] = {}
        batches: list[_SharedBatch] = []
        for text in dict.fromkeys(sequence):
            if self._cache_size > 0:
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    vector_map[text] = cached
                    continue
            batch = self._index.get(text)
            if batch is None:
                batch = self._open_batch
                if batch is None or len(batch.texts) >= self._max_batch_size:
                    batch = _SharedBatch()
                    self._open_batch = batch
                    self._schedule(batch)
                batch.texts.append(text)
                self._index[text] = batch
                if len(batch.texts) >= self._max_batch_size:
                    batch.full_event.set()
            if batch not in batches:
                batches.append(batch)

        return vector_map, batches

    def _schedule(self, batch: _SharedBatch, /) -> None:
        if batch.scheduled:
            return
        batch.scheduled = True
        batch.task = asyncio.get_running_loop().create_task(self._run_batch(batch))

    async def _run_batch(self, batch: _SharedBatch, /) -> None:
        try:
            if self._coalesce_seconds > 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(batch.full_event.wait(), timeout=self._coalesce_seconds)
            else:
                await asyncio.sleep(0)
            async with self._lock:
                if batch.dispatched:
                    return
                batch.dispatched = True
                if self._open_batch is batch:
                    self._open_batch = None
                texts = tuple(batch.texts)
            result = await self._base.embed(texts)
            vectors = tuple(result.vectors)
            _validate_vector_count(vectors, texts)
            completed = dict(zip(texts, vectors, strict=True))
            async with self._lock:
                if self._cache_size > 0:
                    for text, vector in completed.items():
                        self._cache[text] = vector
                        self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                self._release(batch)
            batch.result = completed
            batch.usage = result.usage
        except BaseException as error:
            async with self._lock:
                self._release(batch)
            batch.error = error
        finally:
            batch.completed.set()

    def _release(self, batch: _SharedBatch, /) -> None:
        for text in batch.texts:
            if self._index.get(text) is batch:
                del self._index[text]
        if self._open_batch is batch:
            self._open_batch = None


__all__ = ["CoalescingEmbeddingModel"]


def _validate_vector_count(vectors, texts) -> None:
    if len(vectors) != len(texts):
        message = "embedding model returned a mismatched vector count"
        raise ValueError(message)
