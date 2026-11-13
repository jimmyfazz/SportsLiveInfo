# Documentation index and precedence

**Reconciled 13 November 2026 for the v0.3.4 integration.**

SportsLiveInfo is the public App source repository. LiveSports-EPG is the separate public data destination. Installation and in-place update steps are in the [operator guide](../sportsliveinfo/DOCS.md).

## Precedence

1. Owner-confirmed decisions and `AGENTS.md` govern scope, privacy and work organization.
2. [CURRENT_STATUS.md](CURRENT_STATUS.md) governs current implementation and verification claims; [IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md) records chronology and handover.
3. [MASTER_IMPLEMENTATION_ROADMAP.md](MASTER_IMPLEMENTATION_ROADMAP.md) and focused specifications govern required future behavior, which may exceed implemented source.
4. [FEED_CONTRACT_SLI_V1.md](FEED_CONTRACT_SLI_V1.md), actual source and `../schemas/` govern existing wire fields and paths. Public EPG programme supplements remain unimplemented.
5. Dated audits retain source baselines. Their unmerged branches, pass counts, source availability/terms and B1 findings are historical evidence, not current facts. Older architecture/JSON/Proxmox proposals cannot override the primary HAOS/two-product/read-only-TV requirements.

## Inventory

| Document | Role |
|---|---|
| [AGENTS.md](../AGENTS.md) | Current specification / guide |
| [CLAUDE.md](../CLAUDE.md) | Current specification / guide |
| [README.md](../README.md) | Current specification / guide |
| [docs/AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md](AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md) | Historical audit / receipt |
| [docs/B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md](B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md) | Current specification / guide |
| [docs/B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md](B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md) | Historical audit / receipt |
| [docs/B1_INTEGRATION.md](B1_INTEGRATION.md) | Current specification / guide |
| [docs/B1G_INTEGRATION_FEEDBACK_BACKLOG_2026-11-13.md](B1G_INTEGRATION_FEEDBACK_BACKLOG_2026-11-13.md) | Backlog: producer improvements and B1G feedback import |
| [docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md](CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md) | Current specification / guide |
| [docs/CODEX_B1G_SUBSCRIPTION_INVENTORY_HANDOVER.md](CODEX_B1G_SUBSCRIPTION_INVENTORY_HANDOVER.md) | Current specification / guide |
| [docs/CODEX_CLAUDE_COLLABORATION.md](CODEX_CLAUDE_COLLABORATION.md) | Current specification / guide |
| [Claude’s 13 November audit](CODE_AUDIT_AND_FIXES_2026-11-13.md) | Historical audit and integration input |
| [docs/CURRENT_STATUS.md](CURRENT_STATUS.md) | Current implementation and evidence authority |
| [docs/DELIVERY_PLAN.md](DELIVERY_PLAN.md) | Current specification / guide |
| [docs/FEED_CONTRACTS_AND_PUBLICATION.md](FEED_CONTRACTS_AND_PUBLICATION.md) | Current specification / guide |
| [docs/FEED_CONTRACT_SLI_V1.md](FEED_CONTRACT_SLI_V1.md) | Current specification / guide |
| [docs/FORENSIC_AUDIT_TOKEN_SETUP_EPG_SPORTS_MANIFEST_2026-11-12.md](FORENSIC_AUDIT_TOKEN_SETUP_EPG_SPORTS_MANIFEST_2026-11-12.md) | Historical audit / receipt |
| [docs/FORENSIC_INTEGRATION_AND_CORRECTIONS_2026-11-12.md](FORENSIC_INTEGRATION_AND_CORRECTIONS_2026-11-12.md) | Historical audit / receipt |
| [docs/FORENSIC_SOURCE_AND_LOGIC_INVESTIGATION_2026-11-12.md](FORENSIC_SOURCE_AND_LOGIC_INVESTIGATION_2026-11-12.md) | Historical audit / receipt |
| [docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md](HOME_ASSISTANT_BARE_METAL_PRIMARY.md) | Current specification / guide |
| [docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md](HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md) | Current specification / guide |
| [docs/HOME_ASSISTANT_PROXMOX_HOSTING.md](HOME_ASSISTANT_PROXMOX_HOSTING.md) | Superseded proposal / fallback |
| [docs/IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md) | Current handover + labeled historical receipts |
| [docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md](INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md) | Current specification / guide |
| [docs/LICENSING_AND_HOSTING.md](LICENSING_AND_HOSTING.md) | Current specification / guide |
| [docs/MASTER_IMPLEMENTATION_ROADMAP.md](MASTER_IMPLEMENTATION_ROADMAP.md) | Current specification / guide |
| [docs/QUALITY_SECURITY_AND_ACCEPTANCE.md](QUALITY_SECURITY_AND_ACCEPTANCE.md) | Current specification / guide |
| [docs/RESEARCH_FINDINGS_2026-11-12.md](RESEARCH_FINDINGS_2026-11-12.md) | Historical audit / receipt |
| [docs/SOURCES_AND_IMPROVEMENTS_AUDIT_2026-11-12.md](SOURCES_AND_IMPROVEMENTS_AUDIT_2026-11-12.md) | Historical audit / receipt |
| [docs/SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md](SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md) | Historical audit / receipt |
| [docs/SOURCE_REGISTRY.md](SOURCE_REGISTRY.md) | Current specification / guide |
| [docs/SUBSCRIPTION_DRIVEN_MULTIREGION_EPG.md](SUBSCRIPTION_DRIVEN_MULTIREGION_EPG.md) | Current specification / guide |
| [docs/TEST_PLAN.md](TEST_PLAN.md) | Current specification / guide |
| [docs/UK_BROADCAST_MATCHING.md](UK_BROADCAST_MATCHING.md) | Current specification / guide |
| [docs/WORK_PACKAGE_BACKLOG.md](WORK_PACKAGE_BACKLOG.md) | Current specification / guide |
| [sportsliveinfo/CHANGELOG.md](../sportsliveinfo/CHANGELOG.md) | Release history + current review note |
| [sportsliveinfo/DOCS.md](../sportsliveinfo/DOCS.md) | Current specification / guide |
| [sportsliveinfo/README.md](../sportsliveinfo/README.md) | Current specification / guide |

## Update discipline

For a new source/code change, update current status and handover with SHA, commands/results, remaining gates and rollback. For a UI change, update the operator guide; for a wire change, update contract, schemas and golden fixtures together. Keep external supplier research dated and mark it unverified until rechecked. Preserve historical receipts with their original dates rather than rewriting them into present-tense success claims.
