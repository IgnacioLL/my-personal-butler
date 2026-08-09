# Harness map — personal-memory

| Production tool | `ActionGateway` action | Python implementation |
| --- | --- | --- |
| `memory_read` | `memory_read` | `intelligence.memory.store.MemoryStore` |
| `memory_update` | `memory_update` | `MemoryStore.remember` (after soft Accept) |

CI integration: `scripts/run_test_ci.py` → `integration.memory.*` and `INV-MEM-001`.

Approval tier: `policy.approvals.SOFT_ACTION_TYPES` includes `memory_update`; `AUTO_ACTION_TYPES` includes `memory_read`.

Call-mode allowlist (`channels.voice.allowlist`): `memory_read` allowed mid-call; `memory_update` blocked.
