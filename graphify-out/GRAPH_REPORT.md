# Graph Report - threadline  (2026-05-30)

## Corpus Check
- 142 files · ~39,722 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 788 nodes · 1624 edges · 105 communities (78 shown, 27 thin omitted)
- Extraction: 61% EXTRACTED · 39% INFERRED · 0% AMBIGUOUS · INFERRED: 627 edges (avg confidence: 0.62)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eeb28102`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]

## God Nodes (most connected - your core abstractions)
1. `Workspace` - 69 edges
2. `Organization` - 55 edges
3. `Contact` - 55 edges
4. `require_internal_workspace()` - 53 edges
5. `Ticket` - 48 edges
6. `require_support_workspace()` - 35 edges
7. `TicketComment` - 28 edges
8. `TimeEntry` - 28 edges
9. `record_event()` - 26 edges
10. `get_ai_settings()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `test_apply_selected_ticket_suggestions_are_human_approved()` --calls--> `apply_selected_ticket_suggestions()`  [INFERRED]
  tests/test_ai_foundation.py → ai/services.py
- `test_solution_memory_approval_indexes_internal_snippet()` --calls--> `approve_solution_snippet()`  [INFERRED]
  tests/test_ai_foundation.py → ai/services.py
- `require_internal_workspace()` --calls--> `first_workspace_for()`  [INFERRED]
  core/permissions.py → workspaces/models.py
- `EntityType` --uses--> `Workspace`  [INFERRED]
  search/models.py → workspaces/models.py
- `Meta` --uses--> `Workspace`  [INFERRED]
  search/models.py → workspaces/models.py

## Communities (105 total, 27 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (65): ActivityEvent, Meta, Visibility, AIProviderSettingsAdmin, AIRunAdmin, TicketAIAnalysisAdmin, Meta, AIProviderSettings (+57 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (82): build_request_payload(), _code_for_status(), crm_insight_schema(), _extract_json_object(), _message_content_preview(), OpenRouterError, parse_analysis_response(), _parse_message_payload() (+74 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (73): record_event(), activity_log(), approve_reply_draft(), approve_solution_snippet(), approve_time_suggestion(), ai_audit(), ai_panel_context(), organization_ai_briefing() (+65 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (41): AIProviderSettingsForm, threadline_theme(), _workspace_for_request(), build_settings_context(), _handle_ai_test(), handle_settings_post(), normalize_settings_section(), _scope_invitation_form() (+33 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (28): _queue_customer_reply_email(), _append_inbound_reply(), append_reply_from_inbound_email_stub(), _create_inbound_ticket(), create_ticket_from_inbound_email_stub(), _fetch_imap_messages(), _outbound_mailbox(), outbound_mailbox_for_workspace() (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (30): apply_selected_ticket_suggestions(), customer_profile_for(), dashboard(), apply_organization_row(), confirm_import_job(), create_import_job(), detect_duplicate(), import_row() (+22 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (6): ThreadlineMediaStorage, Storage, render_markdown(), test_business_hours_sla_skips_closed_time(), test_markdown_renderer_sanitizes_script_tags(), test_media_storage_uses_env_only_settings()

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (11): ActivityConfig, AiConfig, AppConfig, CommunicationsConfig, CoreConfig, CrmConfig, CustomerPortalConfig, SearchConfig (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (22): require_customer_profile(), portal_account(), portal_download_attachment(), portal_ticket_create(), portal_ticket_detail(), portal_ticket_list(), portal_ticket_reply(), _portal_tickets() (+14 more)

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (22): Architecture Notes, code:bash (uv sync), code:bash (uv run python manage.py test_ai_provider --workspace demo), code:bash (uv run python manage.py rebuild_search_index --clear), code:bash (uv run python manage.py migrate), code:bash (uv run pytest), code:bash (cp .env.example .env), code:bash (docker compose up --build) (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.16
Nodes (7): decrypt_secret(), encrypt_secret(), _fernet(), is_encrypted(), SecretDecryptionError, encrypt_existing_keys(), Migration

### Community 12 - "Community 12"
Cohesion: 0.23
Nodes (9): ContactForm, Meta, CRMImportJob, CRMImportRow, ImportType, Meta, Resolution, Status (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (6): prune_ai_generation_retention(), prune_ai_generation_retention_task(), BaseCommand, Command, Command, Command

### Community 15 - "Community 15"
Cohesion: 0.25
Nodes (6): Deployment Notes, graphify, Local Commands, Project Defaults, Security And Scoping Rules, Threadline Agent Notes

### Community 16 - "Community 16"
Cohesion: 0.25
Nodes (7): AI Operations, code:bash (uv run python manage.py check), Email, Private Media, Production Readiness, Required Configuration, Verification

## Knowledge Gaps
- **44 isolated node(s):** `Run administrative tasks.`, `Migration`, `Migration`, `Migration`, `URL configuration for config project.  The `urlpatterns` list routes URLs to v` (+39 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **27 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Workspace` connect `Community 0` to `Community 5`, `Community 3`, `Community 12`, `Community 13`?**
  _High betweenness centrality (0.110) - this node is a cross-community bridge._
- **Why does `require_internal_workspace()` connect `Community 2` to `Community 1`, `Community 5`, `Community 3`, `Community 21`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `ApplicationStorageSettings` connect `Community 3` to `Community 6`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Are the 67 inferred relationships involving `Workspace` (e.g. with `AIProviderSettings` and `Provider`) actually correct?**
  _`Workspace` has 67 INFERRED edges - model-reasoned connections that need verification._
- **Are the 50 inferred relationships involving `Organization` (e.g. with `AIProviderSettings` and `Provider`) actually correct?**
  _`Organization` has 50 INFERRED edges - model-reasoned connections that need verification._
- **Are the 50 inferred relationships involving `Contact` (e.g. with `AIProviderSettings` and `Provider`) actually correct?**
  _`Contact` has 50 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `require_internal_workspace()` (e.g. with `activity_log()` and `ticket_ai_panel()`) actually correct?**
  _`require_internal_workspace()` has 51 INFERRED edges - model-reasoned connections that need verification._