# Zendesk MCP Server

![ci](https://github.com/reminia/zendesk-mcp-server/actions/workflows/ci.yml/badge.svg)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A Model Context Protocol server for Zendesk.

This server provides a comprehensive integration with Zendesk. It offers:

- Tools for retrieving and managing Zendesk tickets and comments
- Specialized prompts for ticket analysis and response drafting
- Full access to the Zendesk Help Center articles as knowledge base

![demo](https://res.cloudinary.com/leecy-me/image/upload/v1736410626/open/zendesk_yunczu.gif)

## Quick start

1. **Install:** `uv venv && uv pip install -e .` (or `uv sync`).
2. **Get an OAuth client ID** from a Zendesk admin — see
   [Register a public OAuth client](#1-register-a-public-oauth-client-zendesk-admin-once-per-account).
   One client serves the whole Zendesk account; every operator reuses it.
3. **Configure:** copy `.env.example` to `.env` and set `ZENDESK_SUBDOMAIN` and
   `ZENDESK_CLIENT_ID`.
4. **Authorize once:** `uv run zendesk-auth` — a browser opens, you sign in to
   Zendesk and approve access. Tokens are stored in
   `~/.config/zendesk-mcp/tokens.json` and renewed automatically from then on.
5. **Add the server to your MCP client**, e.g. Claude Desktop:

   ```json
   {
     "mcpServers": {
       "zendesk": {
         "command": "uv",
         "args": [
           "--directory",
           "/path/to/zendesk-mcp-server",
           "run",
           "zendesk"
         ]
       }
     }
   }
   ```

   or Claude Code:

   ```bash
   claude mcp add zendesk -- uv --directory /path/to/zendesk-mcp-server run zendesk
   ```

Already using an API token? See [Migrating from an API token](#migrating-from-an-api-token).

## Setup

- **OCR (optional, for scanned PDFs):** PDF attachments are returned as
  extracted text. When a PDF has a text layer it is used directly; otherwise the
  server falls back to OCR, which requires the `tesseract` binary and the
  relevant language data on the host. On macOS: `brew install tesseract
  tesseract-lang`; on Debian/Ubuntu: `apt-get install tesseract-ocr
  tesseract-ocr-pol tesseract-ocr-eng`. The Docker image installs these
  automatically. OCR behaviour is tunable via environment variables:

  | Variable | Default | Purpose |
  | --- | --- | --- |
  | `ZENDESK_OCR_LANGUAGES` | `pol+eng` | tesseract `-l` value (installed language packs) |
  | `ZENDESK_OCR_DPI` | `300` | Render resolution for OCR |
  | `ZENDESK_PDF_MAX_PAGES` | `50` | Max pages processed per PDF |
  | `ZENDESK_OCR_TIMEOUT` | `120` | Per-page OCR timeout (seconds) |
  | `ZENDESK_TESSERACT_CMD` | `tesseract` | Path to the tesseract binary |

## Authentication

This server authenticates with OAuth (authorization code flow with PKCE). Each
operator authorizes with their own Zendesk login, so API calls carry their
identity and Zendesk applies exactly the permissions it applies in the UI —
their role, their group restrictions, their ticket access. Comments they post
are authored by them.

API-token authentication (`ZENDESK_EMAIL` + `ZENDESK_API_KEY`) is **not
supported**: Zendesk blocked creating new API tokens on 2026-10-27 and stops
accepting all of them on 2027-04-30. If only those variables are set, the server
still starts, but every tool call returns an error explaining how to migrate.

In short, the flow is:

1. A Zendesk admin registers one **public** OAuth client for the account.
2. Each operator runs `zendesk-auth` once. It opens Zendesk's consent page in the
   browser, receives the authorization code on `http://localhost:4567/callback`,
   and exchanges it — together with the PKCE verifier — for an access token and a
   refresh token.
3. The MCP server reads the stored tokens, sends `Authorization: Bearer …` on
   every Zendesk request, and renews the token pair on its own.

### 1. Register a public OAuth client (Zendesk admin, once per account)

In Admin Center, go to **Apps and integrations > APIs > OAuth clients** and
create a client:

| Field | Value |
| --- | --- |
| Client kind | **Public** — this server runs on each operator's machine, so there is no secret it could keep. PKCE is used instead. |
| Redirect URLs | `http://localhost:4567/callback` |
| Allowed scopes | `tickets:read tickets:write ticket_attachments:read users:read hc:read` |

Setting **Allowed scopes** is optional but recommended: it caps what any token
from this client can ever request, even if the code changes.

Note the client's **Identifier** — that is the `ZENDESK_CLIENT_ID` below.

If Zendesk rejects `http://localhost:4567/callback`, register `https://localhost`
instead and use `zendesk-auth --manual` in step 3.

### 2. Configure the environment

Copy `.env.example` to `.env` and set:

```bash
ZENDESK_SUBDOMAIN=acme        # for https://acme.zendesk.com
ZENDESK_CLIENT_ID=your-client-identifier
```

Keep `.env` out of version control.

Optional settings:

| Variable | Default | When to change it |
| --- | --- | --- |
| `ZENDESK_OAUTH_REDIRECT_URI` | `http://localhost:4567/callback` | Port 4567 is in use, or the client is registered with a different redirect URL. Must match a redirect URL on the client exactly. |
| `ZENDESK_OAUTH_SCOPES` | all five scopes below | Narrowing access, e.g. read-only. |
| `ZENDESK_TOKEN_FILE` | `$XDG_CONFIG_HOME/zendesk-mcp/tokens.json` | Storing tokens elsewhere. |

### 3. Authorize this machine, once

```bash
uv run zendesk-auth
```

This opens a browser, asks you to approve access, and stores the resulting
tokens locally. It then prints where the tokens were stored, the scope Zendesk
granted, and how long the tokens are valid. From then on the server renews
access on its own. Each renewal starts a fresh 90-day refresh-token lifetime, so
you only repeat this if the tokens are revoked or the server goes unused for
90 days.

Run `zendesk-auth` from the project directory (or via `uv --directory …`): it
reads `.env` from the current working directory.

If the browser cannot reach this machine — a remote shell, or an OAuth client
registered with `https://localhost` — use the paste-based flow instead:

```bash
uv run zendesk-auth --manual
```

Tokens are written to `$XDG_CONFIG_HOME/zendesk-mcp/tokens.json`
(`~/.config/zendesk-mcp/tokens.json` by default), created `0600` inside a `0700`
directory. The file holds live credentials: treat it like a password and never
commit it.

### How token renewal works

Access tokens are requested with a 30-minute lifetime, so the server refreshes
them for you:

- **before expiry**, when the stored token is within 60 seconds of expiring, and
- **on rejection**, when Zendesk answers `401` with `{"error": "invalid_token"}`,
  in which case the request is retried once with a fresh token.

Only `invalid_token` triggers a retry. A `401` or `403` caused by insufficient
scope or by your own Zendesk permissions is passed through unchanged, so
permission problems stay visible instead of looking like auth flakiness.

Each refresh rotates the refresh token and invalidates the previous one
immediately, so the new pair is written to disk before it is used. Writes are
atomic and guarded by a lock file, which matters when the server runs from more
than one MCP client at the same time (e.g. Claude Desktop and Claude Code).

When the refresh token itself is expired or revoked, tools fail with a message
telling you to re-run `zendesk-auth`.

### Scopes

The default scopes cover every tool this server exposes:

| Scope | Needed for |
| --- | --- |
| `tickets:read` | `get_ticket`, `get_tickets`, `search_tickets`, `get_ticket_comments` |
| `tickets:write` | `create_ticket`, `update_ticket`, `create_ticket_comment` |
| `ticket_attachments:read` | `get_ticket_attachment` |
| `users:read` | requester email/name on `get_ticket`, resolving `me` in `search_tickets` |
| `hc:read` | the `zendesk://knowledge-base` resource |

Scopes are a ceiling, not a grant: a token can never do more than the
authorizing operator is allowed to do. Zendesk accepts unrecognised scope names
when issuing a token but then rejects every request with `403`, so
`zendesk-auth` prints the scope Zendesk actually granted for comparison.

### Re-authorizing, switching accounts, revoking

- **Re-authorize** (expired/revoked tokens, changed scopes, different Zendesk
  user): run `uv run zendesk-auth` again. It overwrites the stored tokens; no
  need to delete anything first. Restart the MCP server afterwards so it drops
  any token it had in memory.
- **Sign out of this machine:** delete `~/.config/zendesk-mcp/tokens.json`.
- **Revoke access server-side:** a Zendesk admin can revoke the operator's
  OAuth tokens in Admin Center; the server then fails with a message asking to
  re-run `zendesk-auth`.

### Migrating from an API token

1. Ask a Zendesk admin for the OAuth client identifier (or create the client —
   [step 1](#1-register-a-public-oauth-client-zendesk-admin-once-per-account)).
2. In `.env`, add `ZENDESK_CLIENT_ID=…` and remove `ZENDESK_EMAIL` and
   `ZENDESK_API_KEY` (leftovers are ignored once `ZENDESK_CLIENT_ID` is set).
3. Run `uv run zendesk-auth` and restart your MCP client.

What changes for you: requests are now made **as you**, with your own Zendesk
role and group permissions — no longer as whichever user owned the API token.
Comments and ticket updates are attributed to you, and `search_tickets` with
`assignee="me"` means the user who ran `zendesk-auth`.

### Security notes

- Tokens live only in the token file (`0600`, directory `0700`); they are never
  written to logs, printed by `zendesk-auth`, or shown in tracebacks.
- The bearer token is sent only to `https://{ZENDESK_SUBDOMAIN}.zendesk.com`.
  Attachments served from Zendesk's CDN (`*.zdusercontent.com`) are pre-signed
  and fetched without credentials, including after a redirect.
- `zendesk-auth` verifies the OAuth `state` value and uses PKCE (S256), so an
  intercepted authorization code cannot be redeemed by anyone else.
- There is no client secret anywhere: the OAuth client is public by design.

### Troubleshooting

| Message / symptom | Cause and fix |
| --- | --- |
| `ZENDESK_CLIENT_ID is not set` | Add the OAuth client identifier to `.env`. |
| `API-token authentication is no longer supported` | Only `ZENDESK_EMAIL`/`ZENDESK_API_KEY` are set — [migrate](#migrating-from-an-api-token). |
| `No Zendesk OAuth tokens found at …` | This machine was never authorized, or `ZENDESK_TOKEN_FILE` points elsewhere. Run `uv run zendesk-auth`. |
| `… refresh token is missing or expired …` / `invalid_grant` | Tokens were revoked or unused for 90 days. Run `uv run zendesk-auth`. |
| `invalid_scope` during `zendesk-auth` | `ZENDESK_OAUTH_SCOPES` asks for more than the client's **Allowed scopes**. Widen them in Admin Center or narrow the variable. |
| `Could not listen on localhost:4567` | The port is taken. Free it, or register another redirect URL and set `ZENDESK_OAUTH_REDIRECT_URI`, or use `zendesk-auth --manual`. |
| `No redirect received within 180s` | Approval wasn't completed in time (Zendesk codes expire after 120 s), or the browser can't reach this machine. Re-run, or use `--manual`. |
| Zendesk shows a redirect URI error | `ZENDESK_OAUTH_REDIRECT_URI` must exactly match a redirect URL registered on the client. |
| Warning: `Zendesk issued no refresh token` | The token cannot be renewed and you'll have to re-run `zendesk-auth` when it expires. Check the OAuth client configuration with your admin. |
| Warning: `Stored tokens belong to subdomain …` / `different OAuth client` | `.env` changed after authorizing. Run `uv run zendesk-auth` again. |
| `Timed out after 30s waiting for the token store lock` | Another server process is stuck holding the lock. If no other Zendesk MCP server is running, delete `tokens.json.lock` next to the token file. |
| Tool returns HTTP `403` | Your Zendesk role can't access that ticket/resource, or the scope is missing. This is reported as-is and never triggers a token refresh. |

## Docker

You can containerize the server if you prefer an isolated runtime:

1. Copy `.env.example` to `.env` and fill in your Zendesk configuration. Keep this file outside version control.
2. Build the image:

   ```bash
   docker build -t zendesk-mcp-server .
   ```

3. Authorize on the **host**, not in the container — `zendesk-auth` needs a
   browser and a local callback port:

   ```bash
   uv run zendesk-auth
   ```

4. Run the server, passing the environment file and mounting the token store:

   ```bash
   docker run --rm \
     --env-file /path/to/.env \
     --user "$(id -u):$(id -g)" \
     -e ZENDESK_TOKEN_FILE=/tokens/tokens.json \
     -v "$HOME/.config/zendesk-mcp:/tokens" \
     zendesk-mcp-server
   ```

   The mount must be writable: the server rewrites the file every time it
   rotates the refresh token. `--user` makes the container run as you, so it can
   read the `0600` token file created on the host. Add `-i` when wiring the
   container to MCP clients over STDIN/STDOUT (Claude Code uses this mode).

The image installs dependencies from `requirements.lock` and drops privileges to a non-root user.

### Claude MCP Integration

To use the Dockerized server from Claude Code/Desktop, add an entry to Claude Code's `settings.json` similar to:

```json
{
  "mcpServers": {
    "zendesk": {
      "command": "/usr/local/bin/docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/zendesk-mcp-server/.env",
        "--user",
        "501:20",
        "-e",
        "ZENDESK_TOKEN_FILE=/tokens/tokens.json",
        "-v",
        "/Users/you/.config/zendesk-mcp:/tokens",
        "zendesk-mcp-server"
      ]
    }
  }
}
```

Adjust the paths and `--user` (your `id -u`:`id -g`) to match your environment. After saving the file, restart Claude for the new MCP server to be detected.

## Resources

- zendesk://knowledge-base, get access to the whole help center articles.

## Prompts

### analyze-ticket

Analyze a Zendesk ticket and provide a detailed analysis of the ticket.

### draft-ticket-response

Draft a response to a Zendesk ticket.

## Tools

### get_tickets

Fetch the latest tickets with pagination support

- Input:
  - `page` (integer, optional): Page number (defaults to 1)
  - `per_page` (integer, optional): Number of tickets per page, max 100 (defaults to 25)
  - `sort_by` (string, optional): Field to sort by - created_at, updated_at, priority, or status (defaults to created_at)
  - `sort_order` (string, optional): Sort order - asc or desc (defaults to desc)

- Output: Returns a list of tickets with essential fields including id, subject, status, priority, description, timestamps, and assignee information, along with pagination metadata

### search_tickets

Search tickets and return lightweight summaries for triage. Use this to find tickets by assignee, requester, status, or date range, then fetch the full details for the ones you need with `get_ticket` / `get_ticket_comments`. Backed by the Zendesk Search API.

- Input (all optional):
  - `query` (string): Advanced — a raw Zendesk search query in native syntax (e.g. `type:ticket assignee:me status:open created>2026-01-01`). When provided, the structured filters below are ignored. `type:ticket` is added automatically if no type is given.
  - `assignee` (string): `me`/`self`/`current` (resolves to the user who ran `zendesk-auth` — see note below), an email, a numeric user id, a full name (e.g. `Jane Doe`), or `none` for unassigned.
  - `requester` (string): same accepted values as `assignee`.
  - `cc` (string): CC/collaborator — same accepted values as `assignee`.
  - `status` (string): one of `new`, `open`, `pending`, `hold`, `solved`, `closed`.
  - `exclude_closed` (boolean): drop `closed` tickets (defaults to true) — they need no further action. Ignored when an explicit `status` or a raw `query` is given.
  - `created_after` / `created_before` (string): creation-date bounds (`YYYY-MM-DD` or ISO8601).
  - `updated_after` / `updated_before` (string): last-activity bounds (`YYYY-MM-DD` or ISO8601).
  - `sort_by` (string): `created_at`, `updated_at`, `priority`, `status`, or `ticket_type` (defaults to `created_at`).
  - `sort_order` (string): `asc` or `desc` (defaults to `desc`).
  - `page` (integer): page number, 1-based (defaults to 1).
  - `per_page` (integer): results per page, max 100 (defaults to 25).
  - `include_description` (boolean): include each ticket's body in the summary (defaults to true).
  - `description_max_chars` (integer): cap each description to this many chars (defaults to 2000; `0` = no cap). Trimmed bodies end with `…[truncated]`.

- Output: Ticket summaries (id, subject, status, priority, timestamps, requester/assignee ids, url, and — unless disabled — a capped `description`), plus `count` (total matches across all pages), `resolved_assignee` and `query` (so you can confirm which account/query was used), and pagination metadata. The Search API returns at most 100 results per page and 1000 results per query.

- Examples:
  - My tickets active in the last 14 days: `assignee="me", updated_after="2026-05-20", sort_by="updated_at", sort_order="desc"`.
  - A pure id/subject list (no bodies): add `include_description=false`.

> **Note on "my tickets":** `assignee="me"` (also `self`/`current`) is resolved server-side to the Zendesk user who authorized this server via OAuth (looked up once per server process via `/api/v2/users/me.json`; if that lookup fails, Zendesk's native `me` keyword is used instead), so you can simply ask for "my tickets" without supplying an email. To search another agent's tickets, pass their email, user id, or full name explicitly.
>
> **Note on "assigned OR cc'd":** Zendesk search has no OR across fields, so "assigned to me **or** I'm in CC" is **two** searches (one with `assignee="me"`, one with `cc="me"`) whose results you merge — not a single call. Putting both in one call ANDs them (tickets where you are *both* assignee and CC).

### get_ticket

Retrieve a Zendesk ticket by its ID

- Input:
  - `ticket_id` (integer): The ID of the ticket to retrieve

### get_ticket_comments

Retrieve all comments for a Zendesk ticket by its ID

- Input:
  - `ticket_id` (integer): The ID of the ticket to get comments for

### get_ticket_attachment

Fetch a ticket attachment (image or PDF) by its `content_url` (as returned by `get_ticket_comments`).

- Input:
  - `content_url` (string): The `content_url` of the attachment

- Output: Images are returned as image content. PDFs are returned as extracted plain text — the embedded text layer when present, otherwise local OCR (tesseract) of the rendered pages. The text is prefixed with a short header noting page count, extraction method (`text`/`ocr`/`mixed`), and whether it was truncated. See [Setup](#setup) for OCR requirements. Only the account's own Zendesk host and Zendesk's CDN are allowed (SSRF guard), and the OAuth token is sent only to the account host — CDN URLs are fetched without credentials. Attachments are capped at 10 MB.

### create_ticket_comment

Create a new comment on an existing Zendesk ticket

- Input:
  - `ticket_id` (integer): The ID of the ticket to comment on
  - `comment` (string): The comment text/content to add
  - `public` (boolean, optional): Whether the comment should be public (defaults to true)

### create_ticket

Create a new Zendesk ticket

- Input:
  - `subject` (string): Ticket subject
  - `description` (string): Ticket description
  - `requester_id` (integer, optional)
  - `assignee_id` (integer, optional)
  - `priority` (string, optional): one of `low`, `normal`, `high`, `urgent`
  - `type` (string, optional): one of `problem`, `incident`, `question`, `task`
  - `tags` (array[string], optional)
  - `custom_fields` (array[object], optional)

### update_ticket

Update fields on an existing Zendesk ticket (e.g., status, priority, assignee)

- Input:
  - `ticket_id` (integer): The ID of the ticket to update
  - `subject` (string, optional)
  - `status` (string, optional): one of `new`, `open`, `pending`, `on-hold`, `solved`, `closed`
  - `priority` (string, optional): one of `low`, `normal`, `high`, `urgent`
  - `type` (string, optional)
  - `assignee_id` (integer, optional)
  - `requester_id` (integer, optional)
  - `tags` (array[string], optional)
  - `custom_fields` (array[object], optional)
  - `due_at` (string, optional): ISO8601 datetime

## Development

Run the test suite:

```bash
uv run pytest
```

The tests use mocked HTTP and never contact Zendesk. They cover PKCE
derivation, the `zendesk-auth` flow, token storage and rotation, and each way
this server calls Zendesk (zenpy reads/writes and direct session calls).
