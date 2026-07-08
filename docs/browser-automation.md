# Browser Automation

Browser automation is used only for workflows that Bubble does not expose
through the editor write API. Scheduled deploy uses a persistent local Chromium
profile and the same deploy flow observed in Aria: open the editor on the test
version, click deploy to live, fill the deploy message, and confirm the modal.

## Scheduled Deploy

Scheduled deploy is preview-first. The first call always returns a preview and
`preview_id`; the caller must show the user the resolved profile, scheduled
time, local timezone, fixed app version, and deploy message. The deploy is only
scheduled after a second call with `execute=true`, `confirm=true`, and the
matching `preview_id`.

Required inputs:

- `profile`
- `scheduled_at`
- `message`

The app version is fixed to Bubble's development branch: `test`. Callers must
not ask for or pass a deploy branch. If `scheduled_at` has no timezone offset,
the MCP interprets it in the local machine timezone and returns the timezone in
the preview for confirmation.

The scheduler stores profile-local state under:

```text
<BUBBLE_MCP_CONFIG_DIR>/profiles/<profile>/deploys/
```

Key files:

- `previews/<preview_id>.json`: pending confirmation previews.
- `scheduled/<deploy_id>.json`: armed scheduled deploys.
- `history.jsonl`: scheduled, cancelled, executed, and failed deploy records.
- `evidence/<deploy_id>/`: deploy screenshots and redacted execution result.

When a scheduled deploy runs, it launches/reuses the persistent Chromium profile
for that Bubble MCP profile, performs the deploy from `version=test`, captures
before/after screenshots, and refreshes the stored Bubble session cookies from
the same browser context.

The timer is in-process. In normal MCP usage, the confirmation call arms the
timer in the running MCP server. If that process restarts before the scheduled
time, call any scheduled-deploy tool, such as `bubble_list_scheduled_deploys`,
to rearm pending records.

## MCP Tools

- `bubble_schedule_deploy`: preview or confirm a scheduled deploy.
- `bubble_list_scheduled_deploys`: list currently scheduled deploys for a
  profile.
- `bubble_cancel_scheduled_deploy`: cancel a scheduled deploy and record the
  cancellation in history.
- `bubble_deploy_history`: list deploy history recorded by this tool.

## CLI Commands

Preview:

```bash
bubble-mcp browser schedule-deploy \
  --profile my-app \
  --scheduled-at 2026-07-09T10:30:00 \
  --message "Release checkout fixes"
```

Confirm the returned preview:

```bash
bubble-mcp browser schedule-deploy \
  --profile my-app \
  --scheduled-at 2026-07-09T10:30:00Z \
  --message "Release checkout fixes" \
  --execute \
  --confirm \
  --preview-id deploy_preview_...
```

Manage scheduled deploys:

```bash
bubble-mcp browser list-deploys --profile my-app
bubble-mcp browser cancel-deploy --profile my-app --deploy-id deploy_...
bubble-mcp browser deploy-history --profile my-app
```

Install the browser extra before relying on execution:

```bash
python -m pip install "befree-bubble-mcp[browser]"
python -m playwright install chromium
```
