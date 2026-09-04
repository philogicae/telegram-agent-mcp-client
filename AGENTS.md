# AGENTS.md

> **Audience.** AI agents working inside the telegram-agent-mcp-client repository.
>
> **Architectural backlog.** This file preserves the full architectural backlog (previously in a separate `ARCHI_TODO.md`, now merged in). Operational runbook / pending verifications live in [TRACKING.md](TRACKING.md).
> Use `- [ ]` checkboxes; cite `file:line`. Remove items once verified and shipped.

## Project overview

Telegram agent with MCP (Model Context Protocol) client capabilities. Python-based bot that connects Telegram users to LLM-powered agents with tool discovery and agent config verification.

## Setup commands

```bash
./scripts/dev.sh          # uv lock/sync · ruff format/lint · ty · shfmt/shellcheck · Prettier
uv run ruff format .      # format only
uv run ruff check .       # lint only
uv run ty check           # type check
uv run telegram-agent-mcp-client --tools    # verify tool discovery
uv run telegram-agent-mcp-client --agents   # verify agent config
```

- CI: `.github/workflows/ci-cd.yml` runs Ruff format/lint and `ty` on every push; tagged builds also publish distributions.
- Local tooling additionally formats/checks shell files and formats Markdown/JSON.
- Tooling: `ruff` (lint/format, see `ruff.toml`) + `ty` (types, `no-matching-overload` ignored in `pyproject.toml`).

## Testing instructions

- No automated test suite (lint/typecheck only) — manual QA via dev bot per TRACKING.md standing regression checks.

## Security considerations

- Allowlist audited 2026-08-28: keyed by Telegram user ID, all handler paths gated, groups handled (any group allowed, only allowlisted users handled), self-prompt/CLI preserved via the `"-1": "Developer"` sentinel. Closed.
- [ ] Relay `sender` is caller-controlled — the relay token is the only gate on spoofing (`bot/relay.py`).
- [ ] `{ENV:VAR}` substitution in MCP tool configs — confirm no secrets leak into logs or `--tools` output.
- [ ] Config writes (`/allow-user`, `/ban-user`) are last-write-wins vs manual edits of the bind-mounted `config/` volume; add a file lock if it ever matters.

## Architecture backlog

### Core (`telegram_agent/src/core/`)

- [ ] Review `core/stats.py` — ensure it doesn't block the agent loop or leak file handles.
- [ ] `core/llm.py` — provider fallback policy (cooldown + jail via `LLM_DEAD_COOLDOWN`/`LLM_JAIL_STRIKES`) keeps growing; extract to its own module if it continues.
- [ ] `core/llm.py` — add tests for model capability suffix parsing (missing `|`, unknown options, duplicates).

### Bot (`telegram_agent/src/bot/`)

- [ ] `instances/telegram.py` — evaluate Bot API rich drafts (private chats) as an opt-in; raw `_rich_request` wrapper may be removable on pytelegrambotapi ≥ 4.36.
- [ ] `handlers/telegram.py` — verify rate-limit/`/cancel` interplay still holds for concurrent runs (voice/image → chat handoff).

### Infra / Config & tooling

- [ ] Agent relay (`bot/relay.py`) — production rollout pending (see TRACKING.md).
- [ ] torrent-search-api service: confirm env drift `extended.yaml` vs `compose.yaml` (`torrent-search-api` is only in `extended.yaml`, not `compose.yaml`).
- [ ] Docs UI (`docs_ui/`) has no CI checks — add lint/build parity if it keeps evolving.

## Accepted trade-offs

- No automated test suite (lint/typecheck only) — manual QA via dev bot per TRACKING.md standing regression checks.
- GraphRAG/neo4j memory stack removed deliberately (commit `59acc66`); context persistence relies on SQLite checkpointer + persisted image descriptions.
