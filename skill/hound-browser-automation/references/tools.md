# Tools (verified against code)

All 7 tools registered in `hound/mcp/server.py`:

| Tool | Description | Params |
|---|---|---|
| `browser_open` | Navigate and get a budgeted snapshot | `url` (string) |
| `browser_snapshot` | Re-read page; returns delta when possible | - |
| `browser_act` | Click/fill/press/select by ref or selector | `action`, `selector` or `ref`, `value` (for fill) |
| `browser_find` | Locate elements by name/role without full snapshot | query/criteria |
| `browser_extract` | Structured extraction with confidence and verified flag | target/schema |
| `browser_heal` | Repair broken selector, verify, remember per site | `selector`, `logical_key` |
| `browser_budget_report` | Session token spend by tool | - |

Notes:
- First snapshot has no baseline for delta
- Budgeting may truncate; check budget report
- Healed selectors are remembered in the selector store
