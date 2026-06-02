# Zendesk MCP Server

![ci](https://github.com/reminia/zendesk-mcp-server/actions/workflows/ci.yml/badge.svg)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A Model Context Protocol server for Zendesk.

This server provides a comprehensive integration with Zendesk. It offers:

- Tools for retrieving and managing Zendesk tickets and comments
- Specialized prompts for ticket analysis and response drafting
- Full access to the Zendesk Help Center articles as knowledge base

![demo](https://res.cloudinary.com/leecy-me/image/upload/v1736410626/open/zendesk_yunczu.gif)

## Setup

- build: `uv venv && uv pip install -e .` or `uv build` in short.
- setup zendesk credentials in `.env` file, refer to [.env.example](.env.example).
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

- configure in Claude desktop:

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

### Docker

You can containerize the server if you prefer an isolated runtime:

1. Copy `.env.example` to `.env` and fill in your Zendesk credentials. Keep this file outside version control.
2. Build the image:

   ```bash
   docker build -t zendesk-mcp-server .
   ```

3. Run the server, providing the environment file:

   ```bash
   docker run --rm --env-file /path/to/.env zendesk-mcp-server
   ```

   Add `-i` when wiring the container to MCP clients over STDIN/STDOUT (Claude Code uses this mode). For daemonized runs, add `-d --name zendesk-mcp`.

The image installs dependencies from `requirements.lock`, drops privileges to a non-root user, and expects configuration exclusively via environment variables.

#### Claude MCP Integration

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
        "zendesk-mcp-server"
      ]
    }
  }
}
```

Adjust the paths to match your environment. After saving the file, restart Claude for the new MCP server to be detected.

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
  - `assignee` (string): `me`/`self`/`current` (resolves to the configured account — see note below), an email, a numeric user id, a full name (e.g. `Jane Doe`), or `none` for unassigned.
  - `requester` (string): same accepted values as `assignee`.
  - `status` (string): one of `new`, `open`, `pending`, `hold`, `solved`, `closed`.
  - `created_after` / `created_before` (string): date bounds (`YYYY-MM-DD` or ISO8601).
  - `updated_after` / `updated_before` (string): date bounds (`YYYY-MM-DD` or ISO8601).
  - `sort_by` (string): `created_at`, `updated_at`, `priority`, `status`, or `ticket_type` (defaults to `created_at`).
  - `sort_order` (string): `asc` or `desc` (defaults to `desc`).
  - `page` (integer): page number, 1-based (defaults to 1).
  - `per_page` (integer): results per page, max 100 (defaults to 25).

- Output: Lightweight ticket summaries (id, subject, status, priority, description, timestamps, requester/assignee ids, url), plus `count` (total matches across all pages), `resolved_assignee` and `query` (so you can confirm which account/query was used), and pagination metadata. The Search API returns at most 100 results per page and 1000 results per query.

- Example — "my latest 100 tickets": `assignee="me", sort_by="created_at", sort_order="desc", per_page=100`.

> **Note on "my tickets":** `assignee="me"` (also `self`/`current`) is resolved server-side to the account configured in `.env` (`ZENDESK_EMAIL`), so you can simply ask for "my tickets" without supplying an email. To search another agent's tickets, pass their email, user id, or full name explicitly.

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

- Output: Images are returned as image content. PDFs are returned as extracted plain text — the embedded text layer when present, otherwise local OCR (tesseract) of the rendered pages. The text is prefixed with a short header noting page count, extraction method (`text`/`ocr`/`mixed`), and whether it was truncated. See [Setup](#setup) for OCR requirements. Only the account's own Zendesk host and Zendesk's CDN are allowed (SSRF guard); attachments are capped at 10 MB.

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
