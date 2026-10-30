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

"""HTTP scoring-service reranking with cross-batch global selection."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision
from powercontext.builtin.inference import InferenceUsage

DEFAULT_HTTP_RERANKER_POLICY_ID = "http-cross-encoder-v1"


class HTTPMemoryReranker:
    """Rerank one coarse pool with a batched HTTP scoring service."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = DEFAULT_HTTP_RERANKER_POLICY_ID,
    ) -> None:
        if batch_size < 1:
            raise ValueError("rerank batch_size must be a positive integer")  # noqa: TRY003
        if not endpoint:
            raise ValueError("rerank endpoint must be a non-empty URL")  # noqa: TRY003
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size
        self.policy_id = policy_id

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score every candidate once, then select globally by service score."""

        if len(candidates) < 1:
            raise ValueError("rerank requires at least one candidate")  # noqa: TRY003
        if limit < 1 or limit > len(candidates):
            raise ValueError("rerank limit must be between one and the candidate count")  # noqa: TRY003

        scores: dict[int, float] = {}
        requests = 0
        for start in range(0, len(candidates), self._batch_size):
            batch = candidates[start : start + self._batch_size]
            expected = set(range(start + 1, start + len(batch) + 1))
            payload = {
                "query": query,
                "candidates": [{"rank": rank, "text": candidates[rank - 1].text} for rank in sorted(expected)],
            }
            response = await self._client.post(self._endpoint, json=payload)
            response.raise_for_status()
            batch_scores = _parse_scores(response, expected)
            scores.update(batch_scores)
            requests += 1

        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        selected_ranks = tuple(rank for rank, _score in ordered[:limit])
        return MemoryRerankDecision(
            selected_ranks=selected_ranks,
            usage=InferenceUsage(requests=requests),
        )


def _parse_scores(response: httpx.Response, expected: set[int], /) -> dict[int, float]:
    try:
        payload: Any = json.loads(response.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message = "rerank response must be valid JSON"
        raise ValueError(message) from error
    if not isinstance(payload, dict) or set(payload) != {"scores"}:
        message = "rerank response must contain exactly a scores field"
        raise ValueError(message)
    entries = payload["scores"]
    if not isinstance(entries, list):
        message = "rerank scores must be a list"
        raise ValueError(message)  # noqa: TRY004 - invalid provider response
    scores: dict[int, float] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"rank", "score"}:
            message = "each rerank score must contain exactly rank and score"
            raise ValueError(message)
        rank = entry["rank"]
        score = entry["score"]
        if type(rank) is not int or type(score) not in (int, float):
            message = "rerank score rank and score must be numeric"
            raise ValueError(message)
        if not math.isfinite(score):
            message = "rerank score must be a finite number"
            raise ValueError(message)
        if rank not in expected or rank in scores:
            message = "rerank scores must cover each batch rank exactly once"
            raise ValueError(message)
        scores[rank] = float(score)
    if set(scores) != expected:
        message = "rerank scores must cover each batch rank exactly once"
        raise ValueError(message)
    return scores


__all__ = ["DEFAULT_HTTP_RERANKER_POLICY_ID", "HTTPMemoryReranker"]
