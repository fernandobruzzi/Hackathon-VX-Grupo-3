# Shared Material Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make batch, MCP search and API approval apply the same conservative identity decision, preserving the item noun across chat checks.

**Architecture:** Extend identity-v2 from PR #74 with a small pair decision and shared item-name/signature helpers. Search translates that decision to existing verified/pending fields; approval rechecks it before any write. No new service or model.

**Tech Stack:** Python 3.12, existing dataclasses/PDM repositories, pytest, PostgreSQL.

**Spec:** docs/superpowers/specs/2026-11-06-shared-material-identity-design.md

## Global Constraints

- No LLM, dependencies, schema changes or automatic approval.
- Preserve original data, frozen labels, pending proposals and applied state.
- Separate equivalence/substitution from duplication; retain uncertainty.
- Work only in the #144 branch, building on the integrated #73 correction from PR #74.

## Review Focus

- Matching PN with contradictory nouns must require review in all consumers.
- Missing noun in a specification class must not become verified identity.
- Unknown manufacturer cannot join distinct known manufacturers.
- A changed noun invalidates a previous chat search even when attributes match.
- Current original evidence and a stale candidate key must not bypass approval/search guards.

---

### Task 1: Shared domain decision and transactional guard

**Files:** `back/domain/{identity,identity_decision}.py`, `back/pipelines/{sanitize,identity_review,import_orders}.py`, `back/repositories/candidates/exact_identity_v1.py`, `back/tests/test_identity_decision.py`, `api/vx_materials_api/services/approval_service.py`, `api/tests/test_approval_identity.py`.

**Interfaces:** Produce `IdentityDecision(status, reasons)` and `decide_identity(catalog: PdmCatalog, left: AnalyzedMaterial, right: AnalyzedMaterial) -> IdentityDecision` in `domain/identity_decision.py`; statuses `SAME_MATERIAL`, `DIFFERENT_MATERIAL`, `REVIEW_REQUIRED`. Produce `resolve_item_name(pdm_class: PdmClass, matched_names: Iterable[str]) -> str | None` and `identity_signature(pdm_class_id: str | None, item_name: str | None, attributes: Mapping[str, str | None]) -> str` in `domain/identity.py`.

- [ ] Add domain and API regressions for contradictory names, manufacturer/model/revision cases, true equal materials and differing required dimensions; run to observe the relevant failure.
- [ ] Implement the shared decision, retaining existing #73 constraints and checking class/noun/required-attribute conflicts before declaring identity. Use it in batch and API approval, including current material evidence.
- [ ] Run back/API focused tests and full suites with separate disposable `_test` databases; commit the tested change.

### Task 2: Search and chat noun propagation

**Files:** `mcp/vx_materials_mcp/repositories/search/hybrid_v1.py`, `mcp/vx_materials_mcp/chatbot/{agent,candidates}.py`, related tool/schema registration, `api/vx_materials_api/services/chat_service.py`, MCP/API chat tests.

**Interfaces:** Consume Task 1 helpers. Preserve public response shape; optional item-name input travels from validated context to search. Both API and Agent calculate the same identity signature including the noun.

- [ ] Add failing real-TAMPA and identical-NIPLE regressions, plus NIPLE-to-COTOVELO invalidation and a genuine-reference positive control.
- [ ] Resolve requested/candidate nouns from classifier evidence, without inventing a name for a multi-item class. Call the shared decision for verification and expose review reasons through existing fields.
- [ ] Carry the item name through chat search and shared signature; reject legacy/different-noun reuse. Run focused tests, full MCP/API suites and contract checks; commit.

### Task 3: Evidence and integration

**Files:** `docs/identidade-materiais.md`, `AGENTS.md`, measurement artifact under `docs/measurements/`.

- [ ] Measure PR #74 baseline versus this branch on the same original kit and frozen cohorts; report retained/withdrawn/new groups and abstentions without changing labels.
- [ ] Document rules, examples, human evidence, IA's actual role and index rebuilding; update workflow pointers.
- [ ] Run Ruff, diff checks and required suites; obtain independent code review and fix material findings with RED→GREEN evidence.
- [ ] Push only the #144 branch, create a Portuguese PR against main, attach it and inspect CI. Never merge another person's work.
