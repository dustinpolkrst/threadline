---
type: community
members: 9
---

# Community 10

**Members:** 9 nodes

## Members
- [[demo()]] - code - tests/test_permissions.py
- [[test_agent_can_edit_ticket_time_entry()]] - code - tests/test_permissions.py
- [[test_agent_can_start_and_stop_billable_timer()]] - code - tests/test_permissions.py
- [[test_agent_cannot_edit_other_workspace_time_entry()]] - code - tests/test_permissions.py
- [[test_customer_cannot_access_internal_settings_or_ticket_detail()]] - code - tests/test_permissions.py
- [[test_customer_cannot_access_other_workspace_ticket()]] - code - tests/test_permissions.py
- [[test_customer_portal_hides_internal_notes_and_private_time()]] - code - tests/test_permissions.py
- [[test_permissions.py]] - code - tests/test_permissions.py
- [[test_ticket_detail_shows_all_time_entries_for_ticket()]] - code - tests/test_permissions.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_10
SORT file.name ASC
```
