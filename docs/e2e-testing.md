# End-to-end testing

An E2E suite drives a real Bubble app in a real browser, as a real test user, and reports what
happened in a form an agent can read: which case failed, at which step, and where the
screenshot and video of that moment are.

Four tools cover the whole loop:

| Tool | What it does |
| --- | --- |
| `bubble_e2e_list` | Suites and cases for a profile, and whether they could run right now. |
| `bubble_e2e_run` | Runs a suite or named cases. Previews by default. |
| `bubble_e2e_report` | Reads a finished run by `run_id`, without re-running it. |
| `bubble_e2e_scaffold` | Creates or extends a suite and writes a case skeleton. |

## Prerequisites

1. **Playwright with Chromium.** It is an optional extra:

   ```bash
   pip install "befree-bubble-mcp[browser]"
   python -m playwright install chromium
   ```

2. **A captured test-user session.** Cases never log in with a password. `bubble_run_as`
   impersonates a user once and parks the resulting cookies as a Playwright storage state; the
   runner loads that file into the browser context.

   ```json
   {"tool": "bubble_run_as", "arguments": {"profile": "kaimia", "user_id": "1784116269914x334073322121781100"}}
   ```

   The session expires when the Bubble cookie does. `bubble_e2e_list` reports the expiry, and a
   run that finds it missing or stale fails before opening a browser, naming `bubble_run_as` as
   the fix.

## Where everything lives

```
$BUBBLE_MCP_CONFIG_DIR/e2e/<profile>/
  suites/<suite>.suite.json     the manifest
  cases/<case>.py               case modules (unless the suite points elsewhere)
  fixtures/                     files cases upload
  runs/<run_id>/
    result.json                 what bubble_e2e_report reads
    <case_id>/
      01-<step>.png             one screenshot per step
      video-trimmed.webm        the recording, if video was on
```

Run artifacts are deliberately outside any checkout: they are large, they are evidence of one
run, and a video of a logged-in app is not something to commit.

## The manifest

JSON, because the config directory already is - the project ships no YAML parser and this is
not worth a dependency.

```json
{
  "name": "kaimia-ks1",
  "profile": "kaimia",
  "app_id": "kaimia-app",
  "branch": "93k8b",
  "base_url": "https://app.kaimia.org.au",
  "cases_root": "C:/Users/me/dev/kaimia/e2e/cases",
  "run_as": { "user_id": "1784116269914x334073322121781100" },
  "viewport": { "width": 1440, "height": 900 },
  "defaults": {
    "headless": false,
    "video": true,
    "cursor": true,
    "slow_mo": 650,
    "timeout_ms": 60000
  },
  "cases": [
    {
      "id": "ks1-t23",
      "description": "Note card shows Subject on top and meta in the footer",
      "module": "ks1_t23_notes.py",
      "tags": ["notes", "layout"],
      "params": { "client_id": null }
    }
  ]
}
```

| Key | Meaning |
| --- | --- |
| `branch` | Bubble app version under test. A `bubble_e2e_run` call can override it. |
| `base_url` | App origin **without** `/version-<branch>`. Set it whenever the app serves from its own domain: otherwise the host is derived from the export's `app_topdomain`, which records the domain but not the subdomain, so the result is a flagged guess. |
| `cases_root` | Where the case modules live. Defaults to the profile's own `cases/`. Point it at a checkout to keep an app's tests in the app's repository instead of copying them here. |
| `run_as.user_id` | Bubble unique id of the impersonated user, as passed to `bubble_run_as`. |
| `defaults.video` / `.cursor` | Recording and the demo pointer. Both off by default - a scheduled regression run wants neither. |
| `defaults.timeout_ms` | Playwright's default timeout per action and assertion. |

The manifest never contains steps. Steps are Python, for a reason explained under *Why cases
are Python* below.

## Writing a case

A case module exposes exactly one entry point:

```python
def run(ctx):
    with ctx.step("open-notes"):
        ctx.goto("/admin/clients", clients=ctx.params["client_id"], section="notes")
        ctx.mark_ready()

    with ctx.step("create-note"):
        ctx.data["subject"] = ctx.unique("E2E subject")
        ctx.type("#e2e-note-subject input", ctx.data["subject"])
        ctx.click("#e2e-note-save")

    with ctx.step("card-created"):
        ctx.expect("#e2e-notes-list > div").to_contain_text(ctx.data["subject"])
```

Each `with ctx.step(...)` block is timed, screenshotted on the way out, and named in the
report. That is what turns "the case failed" into "the case failed at `create-note`, here is
the screenshot".

### The context API

**Addressing**

- `ctx.base_url` - the app origin including `/version-<branch>`.
- `ctx.url(path, **query)` / `ctx.goto(path, **query)` - build and open an app URL. Never
  hardcode a host in a case.
- `ctx.wait_for_url(pattern)` - wait for the address bar to match a regular expression.
- `ctx.url_param(name)` - read a Bubble unique id out of the current URL.

**Locating**

- `ctx.locator(target)` - accepts a CSS selector or an existing Playwright locator, so a case
  can mix both styles.
- `ctx.expect(target)` - Playwright's `expect`, already pointed at the locator.
- `ctx.page` - the raw Playwright page, for anything the helpers do not cover.

**Acting**

- `ctx.click(target)`, `ctx.type(target, text)`, `ctx.fill(target, text)` - move the pointer
  onto the element first, so a recording shows where the click lands.
- `ctx.upload(target, "fixture.pdf")` - set a file input from the suite's fixtures directory.
- `ctx.wait(ms)` - wait while nudging the pointer, so a recorded pause is not a frozen frame.
- `ctx.mark_ready()` - mark the end of app boot; the video is trimmed to this point.

**State and evidence**

- `ctx.params` - the case's `params` from the manifest.
- `ctx.data` - a plain dict to carry values between steps.
- `ctx.unique(prefix)` - a timestamped value, so an assertion can name exactly what this run
  typed instead of something an earlier run left behind.
- `ctx.shot(name, target=...)` - an extra screenshot, of the page or of one element.
- `ctx.zoom_on(target)` / `ctx.zoom_off()` - enlarge an element on a dimmed backdrop. For demo
  recordings, not for assertions.

A case can import a sibling case module by name (`from ks1_t23_notes import open_client`); the
cases directory is on the import path while a case loads. Shared navigation belongs in one
file, not copied into each.

## Running

```json
{"tool": "bubble_e2e_run", "arguments": {"profile": "kaimia", "suite": "kaimia-ks1"}}
```

`execute` defaults to **false**. A preview resolves the branch and base URL, checks the
session, checks that every case module exists, and reports what would run - without opening a
browser or creating a single record. Anything that would stop the run comes back in
`blockers`, each with the tool or command that fixes it.

`execute: true` drives the browser. Passing cases create real data in the app under test, which
is why it is opt-in.

Narrow a run with `cases` (explicit ids) or `tags`. Override `branch`, `headless`, `video`,
`cursor`, `slow_mo` and `timeout_ms` per call; anything left out falls back to the manifest.

Each case gets its own browser, so a case that hangs the page or leaves a modal open costs
only itself. `stop_on_failure` marks the rest skipped instead.

## Reading a run

```json
{"tool": "bubble_e2e_report", "arguments": {"profile": "kaimia", "run_id": "20260920135042_ed91c5"}}
```

The result carries, per case: status, duration, the step list with per-step timings and
screenshots, `failed_step`, the message, and the artifact paths. Add `include_details: true`
for the Python traceback of a failure. `bubble_e2e_list` shows recent `run_id`s.

## Creating the next suite

```json
{
  "tool": "bubble_e2e_scaffold",
  "arguments": {
    "profile": "kaimia",
    "suite": "uat-bookings",
    "case_id": "uat-01",
    "description": "A coordinator can book a service for a client",
    "start_path": "admin/bookings",
    "base_url": "https://app.kaimia.org.au",
    "branch": "93k8b",
    "user_id": "1784116269914x334073322121781100",
    "execute": true
  }
}
```

It lays out the directories, writes the manifest and drops a case module already written
against the context API. What is left to fill in is the selectors and the assertions.

The scaffold deliberately does **not** guess selectors. An element's exposed id lives in the
app export for the version under test, so refresh the context for that branch
(`bubble_context_detect` with the right `app_version`) and look each element up with
`bubble_context_find`. A guessed `#some-id` fails in a way that looks like a broken app rather
than a broken test.

This is the intended path for a tester who does not write Python: describe the test to the
agent, let it resolve the element ids from the export and fill the skeleton in.

## Security

Case modules are executed. They are resolved inside the suite's cases root - an absolute path,
a `..` segment, or a symlink pointing out of the tree is refused rather than normalized - but
anything placed *inside* that directory runs with the privileges of whoever runs the MCP. The
default root sits beside `settings.json` and the session files, so it carries the same trust as
the rest of the config directory. A `cases_root` pointing at a checkout extends that trust to
the checkout; point it only at a repository you would run `make test` in.

Session cookies never appear in a tool result, a log line or a committed artifact. Only the
storage-state path, the reason a session was rejected and its expiry travel.
