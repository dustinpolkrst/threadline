# Graph Report - threadline  (2026-05-09)

## Corpus Check
- 131 files · ~33,673 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 609 nodes · 1278 edges · 79 communities (56 shown, 23 thin omitted)
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 523 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7448c6d0`
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
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]

## God Nodes (most connected - your core abstractions)
1. `Workspace` - 67 edges
2. `Organization` - 53 edges
3. `Contact` - 53 edges
4. `require_internal_workspace()` - 52 edges
5. `Ticket` - 45 edges
6. `TimeEntry` - 27 edges
7. `record_event()` - 23 edges
8. `TicketComment` - 23 edges
9. `get_ai_settings()` - 22 edges
10. `AIProviderSettings` - 15 edges

## Surprising Connections (you probably didn't know these)
- `test_apply_selected_ticket_suggestions_are_human_approved()` --calls--> `apply_selected_ticket_suggestions()`  [INFERRED]
  tests/test_ai_foundation.py → ai/services.py
- `require_internal_workspace()` --calls--> `first_workspace_for()`  [INFERRED]
  core/permissions.py → workspaces/models.py
- `organization_detail()` --calls--> `require_internal_workspace()`  [INFERRED]
  crm/views.py → core/permissions.py
- `contact_detail()` --calls--> `require_internal_workspace()`  [INFERRED]
  crm/views.py → core/permissions.py
- `ticket_download_attachment()` --calls--> `require_internal_workspace()`  [INFERRED]
  tickets/views.py → core/permissions.py

## Communities (79 total, 23 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (57): ActivityEvent, Meta, Visibility, AIProviderSettingsAdmin, AIRunAdmin, TicketAIAnalysisAdmin, Meta, AIProviderSettings (+49 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (52): record_event(), require_customer_profile(), portal_account(), portal_download_attachment(), portal_ticket_create(), portal_ticket_detail(), portal_ticket_list(), portal_ticket_reply() (+44 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (59): find_unlogged_work(), apply_analysis(), apply_selected_ticket_suggestions(), approve_reply_draft(), approve_solution_snippet(), approve_time_suggestion(), build_queue_intelligence(), create_queued_analysis() (+51 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (47): build_request_payload(), _code_for_status(), crm_insight_schema(), _extract_json_object(), _message_content_preview(), OpenRouterError, parse_analysis_response(), _parse_message_payload() (+39 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (47): activity_log(), paginate(), customer_profile_for(), OrganizationForm, apply_organization_row(), confirm_import_job(), create_import_job(), detect_duplicate() (+39 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (27): AIProviderSettingsForm, build_settings_context(), _handle_ai_test(), handle_settings_post(), normalize_settings_section(), _scope_invitation_form(), settings_redirect(), team_settings() (+19 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (11): ActivityConfig, AiConfig, AppConfig, CommunicationsConfig, CoreConfig, CrmConfig, CustomerPortalConfig, SearchConfig (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (22): Architecture Notes, code:bash (uv sync), code:bash (uv run python manage.py test_ai_provider --workspace demo), code:bash (uv run python manage.py rebuild_search_index --clear), code:bash (uv run python manage.py migrate), code:bash (uv run pytest), code:bash (cp .env.example .env), code:bash (docker compose up --build) (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (7): append_reply_from_inbound_email_stub(), create_ticket_from_inbound_email_stub(), queue_outbound_ticket_reply_stub(), record_email_delivery_attempt(), send_email_message_stub(), test_stub_inbound_email_creates_ticket_and_deduplicates(), test_stub_inbound_reply_and_outbound_queue_records()

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (3): render_markdown(), test_business_hours_sla_skips_closed_time(), test_markdown_renderer_sanitizes_script_tags()

### Community 11 - "Community 11"
Cohesion: 0.24
Nodes (7): decrypt_secret(), encrypt_secret(), _fernet(), is_encrypted(), SecretDecryptionError, encrypt_existing_keys(), Migration

### Community 14 - "Community 14"
Cohesion: 0.25
Nodes (3): EntityType, Meta, SearchDocument

### Community 15 - "Community 15"
Cohesion: 0.25
Nodes (6): Deployment Notes, graphify, Local Commands, Project Defaults, Security And Scoping Rules, Threadline Agent Notes

## Knowledge Gaps
- **48 isolated node(s):** `Run administrative tasks.`, `Migration`, `Migration`, `Migration`, `Migration` (+43 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Workspace` connect `Community 0` to `Community 1`, `Community 3`, `Community 5`, `Community 14`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `require_internal_workspace()` connect `Community 2` to `Community 17`, `Community 4`, `Community 5`, `Community 1`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Why does `record_event()` connect `Community 1` to `Community 0`, `Community 8`, `Community 2`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `Workspace` (e.g. with `ActivityEvent` and `Visibility`) actually correct?**
  _`Workspace` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 49 inferred relationships involving `Organization` (e.g. with `ActivityEvent` and `Visibility`) actually correct?**
  _`Organization` has 49 INFERRED edges - model-reasoned connections that need verification._
- **Are the 49 inferred relationships involving `Contact` (e.g. with `ActivityEvent` and `Visibility`) actually correct?**
  _`Contact` has 49 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `require_internal_workspace()` (e.g. with `activity_log()` and `ticket_ai_analyze()`) actually correct?**
  _`require_internal_workspace()` has 51 INFERRED edges - model-reasoned connections that need verification._