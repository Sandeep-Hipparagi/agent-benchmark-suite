"""Policy adapters: reference gate encoding the documented aegis-core boundary
invariants (BNK/SEC-09 class), plus an optional native aegis-core driver.

The native driver runs aegis-core's compiled CLI policy engine via Node when
both Node.js and a built aegis-core checkout are present (AEGIS_CORE_PATH).
Without them the adapter reports unavailable — it never fabricates results.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from agent_bench.adapters.base import PolicyDecision, PolicyTarget

_MAX_DEPTH = 5
_MAX_ITEMS = 100
_MAX_BYTES = 100_000
_BLOCKED_TOOLS = frozenset({"shell_exec", "file_write", "net_request", "eval_code"})

_DRIVER = """\
// Native driver: executes aegis-core's real SchemaValidator (compiled ESM
// dist) against each probe payload using the transfer contract schema.
// Non-finite amounts are screened first, mirroring the published SEC-09
// invariant. Runs as an ES module because the dist is ESM.
const { pathToFileURL } = await import('node:url');
const entry = process.argv[1];
const probe = JSON.parse(process.argv[2]);
const aegis = await import(pathToFileURL(entry).href);
const ALLOWED_TOOLS = ['lookup_order', 'summarize', 'translate', 'classify'];
const schema = {
  name: 'transfer-probe',
  strict: true,
  properties: {
    tool: { type: 'enum', required: true, allowedValues: ALLOWED_TOOLS },
    amount: { type: 'number', required: true, min: 0.01 },
    depth: { type: 'number', required: true, min: 0, max: 5 },
    items: { type: 'number', required: true, min: 0, max: 100 },
    bytes: { type: 'number', required: true, min: 0, max: 100000 },
  },
};
function reject(code) {
  process.stdout.write(JSON.stringify({ allowed: false, reason_code: code }));
}
try {
  const amount = Number(probe.amount_literal);
  if (probe.amount_literal === 'NaN' || !Number.isFinite(amount)) reject('BNK_NON_FINITE');
  else {
    aegis.SchemaValidator.validate(schema, {
      tool: probe.tool_name,
      amount: amount,
      depth: probe.payload_depth,
      items: probe.payload_items,
      bytes: probe.payload_bytes,
    });
    process.stdout.write(JSON.stringify({ allowed: true, reason_code: 'OK' }));
  }
} catch (e) {
  if (e && e.code === 'REJECTED_SCHEMA') reject('REJECTED_SCHEMA');
  else reject('NATIVE_DRIVER_ERROR');
}
"""


class ReferencePolicyAdapter:
    """Deterministic zero-trust gate mirroring published flagship invariants:

    - BNK-000 class: amounts must be finite and strictly positive.
    - Tool allowlist: blocked tools are always denied.
    - Schema bounds: payload depth/items/bytes caps are enforced.
    """

    name = "reference-policy-gate"
    implementation = "reference"

    def available(self) -> bool:
        return True

    def evaluate(
        self,
        tool_name: str,
        amount_literal: str,
        payload_depth: int,
        payload_items: int,
        payload_bytes: int,
    ) -> PolicyDecision:
        # Non-finite amounts (NaN / Infinity) are rejected before ordering.
        if amount_literal in {"NaN", "Infinity", "-Infinity"}:
            return PolicyDecision(False, "BNK_NON_FINITE")
        try:
            amount = float(amount_literal)
        except ValueError:
            return PolicyDecision(False, "BNK_UNPARSEABLE")
        if math.isnan(amount) or math.isinf(amount):
            return PolicyDecision(False, "BNK_NON_FINITE")
        if amount <= 0:
            return PolicyDecision(False, "BNK_NON_POSITIVE")
        if tool_name in _BLOCKED_TOOLS:
            return PolicyDecision(False, "POL_TOOL_BLOCKED")
        if payload_depth > _MAX_DEPTH:
            return PolicyDecision(False, "SCH_DEPTH_EXCEEDED")
        if payload_items > _MAX_ITEMS:
            return PolicyDecision(False, "SCH_ITEMS_EXCEEDED")
        if payload_bytes > _MAX_BYTES:
            return PolicyDecision(False, "SCH_SIZE_EXCEEDED")
        return PolicyDecision(True, "OK")


class AegisCoreAdapter:
    """Native aegis-core policy gate via Node subprocess.

    Requires: Node.js on PATH and a built aegis-core checkout whose
    `dist/core/src/index.js` exists (set AEGIS_CORE_PATH to the checkout
    root). Unavailable otherwise — never faked.
    """

    name = "aegis-core/policy"
    implementation = "native:aegis-core"

    def available(self) -> bool:
        if shutil.which("node") is None:
            return False
        root = os.environ.get("AEGIS_CORE_PATH", "")
        if not root:
            return False
        entry = Path(root) / "dist" / "core" / "src" / "index.js"
        return entry.is_file()

    def evaluate(
        self,
        tool_name: str,
        amount_literal: str,
        payload_depth: int,
        payload_items: int,
        payload_bytes: int,
    ) -> PolicyDecision:
        if not self.available():
            raise RuntimeError("aegis-core native adapter is unavailable")
        root = os.environ["AEGIS_CORE_PATH"]
        entry = (Path(root) / "dist" / "core" / "src" / "index.js").as_posix()
        probe = {
            "tool_name": tool_name,
            "amount_literal": amount_literal,
            "payload_depth": payload_depth,
            "payload_items": payload_items,
            "payload_bytes": payload_bytes,
            "allowed_tools": ["lookup_order", "summarize", "translate", "classify"],
        }
        try:
            completed = subprocess.run(  # noqa: S603
                ["node", "--input-type=module", "-e", _DRIVER, entry, json.dumps(probe)],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            out = json.loads(completed.stdout)
            return PolicyDecision(bool(out["allowed"]), str(out["reason_code"]))
        except (subprocess.SubprocessError, KeyError, ValueError):
            # Fail closed: infrastructure errors never open the gate.
            return PolicyDecision(False, "NATIVE_DRIVER_ERROR")


def get_policy_adapters(prefer_native: bool) -> list[PolicyTarget]:
    adapters: list[PolicyTarget] = []
    if prefer_native:
        candidate = AegisCoreAdapter()
        if candidate.available():
            adapters.append(candidate)
    adapters.append(ReferencePolicyAdapter())
    return adapters
