# Tools (verified against hound/mcp/server.py)

| Tool | Required params | Optional params | Notes |
|---|---|---|---|
| `browser_open` | `url` | `wait_until`, `max_tokens`, `profile` | Navigates and returns budgeted snapshot |
| `browser_snapshot` | - | `full_snapshot`, `max_tokens`, `profile` | Delta by default (only changes) |
| `browser_act` | `action`, `target` | `value`, `max_tokens`, `profile` | `action`: click/fill/press/select. `target` = ref (e.g. e3) or CSS selector. `value` for fill/press/select. |
| `browser_find` | `text` | `role`, `limit` | Find by accessible name substring; avoids full snapshot |
| `browser_extract` | `root`, `fields` | `max_tokens` | `fields` = {output_name: css_selector} per container |
| `browser_heal` | `selector`, `logical_key` | - | Repairs selector, verifies, remembers per site |
| `browser_budget_report` | - | - | Session token spend by tool |

- First snapshot has no baseline for delta.
- Budgeting may truncate; check `browser_budget_report`.
