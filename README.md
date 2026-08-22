# Telegram Agent MCP Client

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://docs.astral.sh/uv/getting-started/installation/)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Actions status](https://github.com/philogicae/telegram-agent-mcp-client/actions/workflows/ci-cd.yml/badge.svg?cache-control=no-cache)](https://github.com/philogicae/telegram-agent-mcp-client/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/philogicae/telegram-agent-mcp-client)

A multi-agent Telegram bot built on [LangGraph Swarm](https://github.com/langchain-ai/langgraph-swarm). A Friendly coordinator routes user requests to specialized agents — Search, Image Manager, Media, Home Assistant, Dev Agent — each backed by tools loaded from **MCP servers** and **native Python tools**. Handles multimodal input (text, voice, images), TTS voice replies, and ships with a Next.js docs UI.

## Features

- **Multi-agent swarm** — coordinator hands off to specialized agents via LangGraph handoff tools; agents and tools declared in `config/agent_config.json`
- **MCP + native tools** — discovered recursively from `config/tools/`: MCP servers as `.json` (stdio or HTTP/SSE), native Python tools as `.py` `@tool` functions — see [config/tools/README.md](config/tools/README.md)
- **Multimodal** — text, voice (transcribed or passed as audio to models with `stt`), images (inline for `vision`-capable models, or described on-the-fly by the first capable fallback provider and persisted to disk so context survives across sessions)
- **TTS replies** — per-user `/tts` toggle generates voice messages via OpenRouter TTS; an LLM-driven `tts_adapt` step rewrites text to be speakable, not summarized
- **Rate limiting & cancel** — concurrent runs in the same chat are rejected; `/cancel` aborts the active run; 429 flood-waits are respected and capped at 60s
- **Streaming edits** — tool logs and model reasoning stream into the message with live edits; final messages render as rich Telegram HTML via `sendRichMessage`, intermediate edits fall back to classic HTML with graceful failure handling
- **Docker-first** — `compose.yaml` runs the bot + docs UI; `extended.yaml` adds optional services (Transmission, torrent search, n8n)

## Requirements

Python 3.14+, [uv](https://docs.astral.sh/uv/), Node.js + npm (MCP servers + Playwright), a Telegram bot token, and at least one LLM provider in `.env` — Gemini, OpenRouter, OpenCode, Fireworks, or Ollama. ffmpeg is optional (TTS voice encoding).

## Quick start

```bash
cp .env.example .env
cp config/agent_config.example.json config/agent_config.json
cp config/user_config.example.json config/user_config.json
uv sync
uv run telegram-agent-mcp-client --telegram
```

Edit `.env` to set `TELEGRAM_BOT_ID`, `GEMINI_API_KEY`, and `LLM_ORDER` / `LLM_ORDER_FAST`. Drop `--telegram` for CLI mode, or add `--dev` to use `TELEGRAM_BOT_ID_DEV`.

### Docker

```bash
./scripts/deploy-agent.sh    # bot + docs-ui
./scripts/deploy-tools.sh    # extended services (Transmission, search, n8n)
```

## CLI

```
telegram-agent-mcp-client [--telegram] [--dev] [--tools] [--agents] [--png]
```

| Flag         | Action                                         |
| ------------ | ---------------------------------------------- |
| `--telegram` | Run as Telegram bot (default: interactive CLI) |
| `--dev`      | Use `TELEGRAM_BOT_ID_DEV`                      |
| `--tools`    | Print loaded tools and exit                    |
| `--agents`   | Print configured agents and exit               |
| `--png`      | Render the swarm graph to PNG and exit         |

## Configuration

### `.env`

See [`.env.example`](.env.example) for the full list.

| Variable                                      | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TELEGRAM_BOT_ID` / `TELEGRAM_BOT_ID_DEV`     | Bot tokens for prod/dev                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `LLM_ORDER` / `LLM_ORDER_FAST`                | Comma-separated provider run order (main + fast/utility tasks). First **configured** provider wins; when a capability is required, the first capable provider is selected. Runtime failures immediately fall over to the next candidate: each failure cools a provider down (`LLM_DEAD_COOLDOWN`, 300s) and 3 strikes jail it for 24h (`LLM_JAIL_STRIKES`/`LLM_JAIL_HOURS`). Values: `ollama`, `gemini`, `gemini-small`, `fireworks`, `opencode`, `opencode-alt` |
| Model capability suffixes                     | Append `                                                                                                                                                                                                                                                                                                                                                                                                                                                         | opt1+opt2`to any`*_API_MODEL`: `text`, `vision`(images in),`stt`(audio in),`video`, `pdf`, `image`(image gen),`tts`(speech out),`structured` (native JSON output). Lookup: [models.dev](https://models.dev) |
| `GEMINI_API_KEY`                              | Google Gemini (vision, image generation)                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `OPENROUTER_API_KEY` / `OPENROUTER_TTS_SPEED` | OpenRouter TTS; speed clamped to `[0.25, 4.0]` (default `1.15`)                                                                                                                                                                                                                                                                                                                                                                                                  |
| `DATA_DIR` / `CONFIG_DIR`                     | Persisted data and tool config paths                                                                                                                                                                                                                                                                                                                                                                                                                             |

### Agent & user config

- **`config/agent_config.json`** — declares agents (`prompt`, `tools`, `transfer`, optional `routines`) and shared `common` guidelines/handoff template. See [example](config/agent_config.example.json).
- **`config/user_config.json`** — admin users, allowed/restricted agents per user. See [example](config/user_config.example.json).

### Tools

`config/tools/` holds tool definitions organized by category:

- **`.json`** — MCP server config (stdio command or HTTP/SSE URL), with `{ENV:VAR}` substitution, `enable`/`disable` filters, and `edit` overrides
- **`.py`** — native LangChain `@tool` functions loaded into the agent process

See [config/tools/README.md](config/tools/README.md) for the full spec and [`_template.py`](config/tools/_template.py) for a scaffold.

## Project structure

```
telegram_agent/
  __main__.py              CLI entry point + Playwright install
  src/
    core/                  agent · config · llm · tools · utils
    bot/                   abstract · bots · instances · handlers · managers · utils
config/                    agent_config.json · user_config.json · tools/
docs_ui/                   Next.js docs UI (optional, served on :4040)
scripts/                   dev.sh · deploy-agent.sh · deploy-tools.sh
compose.yaml · extended.yaml
```

## Development

```bash
./scripts/dev.sh    # uv lock · ruff format · ruff check --fix · ty check · shellcheck
```

CI runs the same checks on every push — see [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml).

## License

[MIT](LICENSE)
