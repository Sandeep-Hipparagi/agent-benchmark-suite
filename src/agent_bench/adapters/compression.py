"""Compression adapters: reference compactor + native flagship integrations.

The reference compactor is a real redundancy-elimination engine (verbatim
duplicate suppression, filler stripping, whitespace collapse, payload pruning)
executed against every trace. Native adapters wrap `agent_snr`'s SNR firewall
and `context_guard`'s ledger compressor when importable.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Iterable
from typing import Any

from agent_bench.adapters.base import CompressionTarget

_WS = re.compile(r"\s+")
_MAX_JSON_DEPTH = 5
_MAX_LIST_ITEMS = 15


def _strip_fillers(text: str) -> str:
    """Drop pleasantries and status-noise lines the workloads inject."""
    keep: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith(("let me know if", "this is an automated", "no changes were detected")):
            continue
        keep.append(stripped)
    return "\n".join(keep)


def _prune_json(value: Any, depth: int = 0) -> Any:
    """Recursively prune oversized JSON payloads deterministically."""
    if depth >= _MAX_JSON_DEPTH:
        return "…"
    if isinstance(value, dict):
        return {k: _prune_json(v, depth + 1) for k, v in list(value.items())[:_MAX_LIST_ITEMS]}
    if isinstance(value, list):
        return [_prune_json(v, depth + 1) for v in value[:_MAX_LIST_ITEMS]]
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "…"
    return value


class ReferenceCompressionAdapter:
    """Real redundancy-aware compactor executed in-process."""

    name = "reference-compactor"
    implementation = "reference"

    def available(self) -> bool:
        return True

    def compress(self, messages: list[dict[str, str]]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for msg in messages:
            content = msg.get("content", "")
            if msg.get("role") == "system":
                out.append(content)
                continue
            content = _strip_fillers(content)
            # Collapse emoji/whitespace padding runs.
            content = _WS.sub(" ", content).strip()
            # Prune embedded JSON payloads.
            if content.startswith("{") and content.endswith("}"):
                with contextlib.suppress(json.JSONDecodeError, ValueError):
                    content = json.dumps(_prune_json(json.loads(content)), separators=(",", ":"))
            # Verbatim duplicate suppression (exact-content echo frames).
            key = f"{msg.get('role')}:{content}"
            if key in seen:
                continue
            seen.add(key)
            out.append(content if content else "∅")
        return out


class AgentSNRCompressionAdapter:
    """Wraps agent-snr's SNR firewall (in-process, real library)."""

    name = "agent-snr/firewall"
    implementation = "native:agent-snr"

    # OpenAI role -> agent-snr FrameRole vocabulary.
    _ROLE_MAP = {"tool": "tool_result"}

    def __init__(self) -> None:
        self._firewall: Any = None

    def available(self) -> bool:
        try:
            from agent_snr import AgentSNRFirewall  # noqa: PLC0415
        except ImportError:
            return False
        if self._firewall is None:
            self._firewall = AgentSNRFirewall()
        return True

    def compress(self, messages: list[dict[str, str]]) -> list[str]:
        assert self._firewall is not None
        mapped = [
            {**m, "role": self._ROLE_MAP.get(m.get("role", ""), m.get("role", ""))}
            for m in messages
        ]
        budgeted, _action, _metrics = self._firewall.process_outbound(
            session_id="agent-bench", node_id="bench", messages=mapped
        )
        return [str(m.get("content", "")) for m in budgeted]


class ContextGuardCompressionAdapter:
    """Wraps context-guard's ledger compressor (in-process, real library)."""

    name = "context-guard/compressor"
    implementation = "native:context-guard"

    def __init__(self) -> None:
        self._compressor: Any = None

    def available(self) -> bool:
        try:
            from context_guard.compressors.engine import ContextCompressor  # noqa: PLC0415
        except ImportError:
            return False
        if self._compressor is None:
            self._compressor = ContextCompressor()
        return True

    def compress(self, messages: list[dict[str, str]]) -> list[str]:
        import asyncio  # noqa: PLC0415

        assert self._compressor is not None

        async def _run() -> list[str]:
            result = await self._compressor.compress(messages)
            parts: list[str] = []
            if getattr(result, "system_directive", ""):
                parts.append(str(result.system_directive))
            if getattr(result, "state_ledger_markdown", ""):
                parts.append(str(result.state_ledger_markdown))
            for turn in getattr(result, "recent_raw_turns", []):
                parts.append(str(turn.get("content", "")))
            return parts

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError("ContextGuard adapter cannot run inside a live event loop")
        return asyncio.run(_run())


def get_compression_adapters(prefer_native: bool) -> list[CompressionTarget]:
    """Ordered adapter list; native adapters are included only when usable."""
    adapters: list[CompressionTarget] = []
    if prefer_native:
        for candidate in (AgentSNRCompressionAdapter(), ContextGuardCompressionAdapter()):
            if candidate.available():
                adapters.append(candidate)
    adapters.append(ReferenceCompressionAdapter())
    return adapters


def keyword_retention(before: Iterable[str], after: Iterable[str], min_len: int = 4) -> float:
    """Fraction of distinctive content keywords preserved after compression."""
    stop = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "were",
        "their",
        "which",
        "about",
        "would",
        "there",
        "your",
        "will",
        "they",
        "them",
    }

    def keywords(parts: Iterable[str]) -> set[str]:
        words: set[str] = set()
        for p in parts:
            for w in _WS.sub(" ", p).split():
                w = w.strip(".,;:!?()[]{}\"'—")
                if len(w) >= min_len and w.lower() not in stop and not w.startswith("🚀"):
                    words.add(w.lower())
        return words

    before_k = keywords(before)
    if not before_k:
        return 1.0
    return len(before_k & keywords(after)) / len(before_k)
