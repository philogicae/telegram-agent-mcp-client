# AGENTS.md

> **Audience.** AI agents working inside the telegram-agent-mcp-client repository.
>
> Use `- [ ]` checkboxes; cite `file:line`. Remove items once verified and shipped.

## Project overview

Telegram agent with MCP (Model Context Protocol) client capabilities. Python-based bot that connects Telegram users to LLM-powered agents with tool discovery and agent config verification.

## Setup commands

```bash
./scripts/dev.sh          # uv lock/sync · ruff format/lint · ty · pytest · shfmt/shellcheck · Prettier
uv run ruff format .      # format only
uv run ruff check .       # lint only
uv run ty check           # type check
uv run pytest             # test suite (add --cov=telegram_agent for a coverage report)
uv run python -m telegram_agent.tests.test_prune   # manual regression checks
uv run telegram-agent-mcp-client --tools    # verify tool discovery
uv run telegram-agent-mcp-client --agents   # verify agent config
```

- CI: `.github/workflows/ci-cd.yml` runs Ruff format/lint, `ty` and `pytest` (coverage appended to the job summary) on every push; tagged builds only publish when the lint and test jobs pass.
- Local tooling additionally formats/checks shell files and formats Markdown/JSON.
- Tooling: `ruff` (lint/format, see `ruff.toml`) + `ty` (types, `no-matching-overload` ignored and `telegram_agent/tests` excluded in `pyproject.toml`) + `pytest`/`pytest-asyncio`/`pytest-xdist`/`pytest-cov` (config in `pyproject.toml`).

## Testing instructions

- pytest suite: `uv run pytest` (or `-n auto --dist worksteal --cov=telegram_agent` for CI parity). Tests live in `telegram_agent/tests/`; ~440 tests at ~95% line coverage. No network/Telegram/LLM calls: external boundaries are faked via `telegram_agent/tests/fakes.py`, and `conftest.py` disables `.env` loading and redirects `CONFIG_DIR`/`DATA_DIR` to a throwaway directory.
- `uv run python -m telegram_agent.tests.test_prune` remains the manual regression runner (also exercised by `pytest` via `test_prune_pytest.py`).
- Everything else (bot behavior end-to-end): manual QA via dev bot.

## Security considerations

- Allowlist audited 2026-08-28: keyed by Telegram user ID, all handler paths gated, groups handled (any group allowed, only allowlisted users handled), self-prompt/CLI preserved via the `"-1": "Developer"` sentinel. Closed.
- [ ] Relay `sender` is caller-controlled - the relay token is the only gate on spoofing (`bot/relay.py`).
- [ ] `{ENV:VAR}` substitution in MCP tool configs - tool-loading errors print the raw exception (`core/tools.py`), which may echo URLs/headers containing secrets; confirm no secrets leak into logs or `--tools` output.
- [ ] Config writes (`/allow-user`, `/ban-user`) are last-write-wins vs manual edits of the bind-mounted `config/` volume; add a file lock if it ever matters.

## Architecture backlog

### Core (`telegram_agent/src/core/`)

- [ ] `core/llm.py` - provider fallback policy (cooldown + jail via `LLM_DEAD_COOLDOWN`/`LLM_JAIL_STRIKES`) keeps growing; extract to its own module if it continues.
- [ ] `core/llm.py` - add tests for model capability suffix parsing (missing `|`, unknown options, duplicates) to `telegram_agent/tests/`.

### Bot (`telegram_agent/src/bot/`)

- [ ] `instances/telegram.py` - `_rich_request` is still used for `sendRichMessage`; pytelegrambotapi 4.36.1 exposes `send_rich_message`/`send_rich_message_draft`/`send_message_draft`, so the raw wrapper may be removable.
- [ ] `handlers/telegram.py` - verify the per-chat FIFO queue + cancel-event supersede path for concurrent runs (voice/image → chat handoff); no automated coverage yet.

### Infra / Config & tooling

- [ ] Agent relay (`bot/relay.py`) - production rollout pending.

## Accepted trade-offs

- No pytest suite (lint/typecheck + one manual regression runner only) - manual QA via dev bot.
- GraphRAG/neo4j memory stack removed deliberately (commit `59acc66`); context persistence relies on SQLite checkpointer + persisted image descriptions.
