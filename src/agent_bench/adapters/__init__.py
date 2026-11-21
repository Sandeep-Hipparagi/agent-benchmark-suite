"""Adapters package: versioned protocols and flagship integrations."""

from agent_bench.adapters.base import PolicyDecision, PolicyTarget
from agent_bench.adapters.compression import get_compression_adapters
from agent_bench.adapters.policy import get_policy_adapters
from agent_bench.adapters.provenance import get_provenance_adapters
from agent_bench.adapters.routing import get_routing_adapters

__all__ = [
    "PolicyDecision",
    "PolicyTarget",
    "get_compression_adapters",
    "get_policy_adapters",
    "get_provenance_adapters",
    "get_routing_adapters",
]
