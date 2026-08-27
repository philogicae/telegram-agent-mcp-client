## [unreleased]

### 🚀 Features

- Feat: implement langchain agent with MCP client integration
- Feat: create empty config file if not found and add test environment variables
- Feat: add mcp_config.json to Docker image and update dependencies
- Feat: add Ollama LLM support and improve agent output formatting
- Feat: add configurable think tags for agent message parsing
- Feat: add support for Gemini and Cerebras LLMs
- Feat: add Groq LLM support and refactor config/llm modules
- Feat: add support for list-type message content for gemini thinking and set temperature=0.5 for all LLM providers
- Feat: enhance agent output with rich panels and update dependencies
- Feat: add timing metrics for agent responses and display in usage panel
- Feat: add web-search and torrent-search tools to MCP config example
- Feat: add detailed usage tracking and improve console output formatting
- Feat: add rqbit to docker-compose
- Feat: Custom tool loader and format
- Feat: increase ollama context window to 8192 tokens and update dependencies
- Feat: enhance agent prompts with meta-procedures
- Feat: add deep-search plugin config and update Brave search description with news focus
- Feat: add pytelegrambotapi dependency and initial bot module structure
- Feat: rework agent
- Feat: add telegram bot module
- Feat: update main
- Feat: rework agent for telegram + add checkpoint/store
- Feat: major rework on telegram bot
- Feat: rework agent 2
- Feat: rework bot 2
- Feat: fix markdown bugs, add auto issue report, optimizations, add new_releases meta-procedure to prompt v2
- Feat: restructure docker setup with env configs and deployment scripts
- Feat: add support for Gemini thinking response format
- Feat: rework/improve docker setup
- Feat: add Emby media server integration with library refresh after downloads
- Feat: add CLI tool listing
- Feat: add progress bar utility function for displaying completion status
- Feat: improve tool execution feedback with detailed status and error reporting
- Feat: integrate rqbit client for torrent download management
- Feat: enhance torrent status display with live indicators and improved message formatting
- Feat: improve torrent UI with cleaner progress bars and optimized message updates
- Feat: add configurable delay parameter to TorrentManager polling loop
- Feat: set higher timeout and disable logging for sse/http connections
- Feat: auto-forget torrent after completion
- Feat: improve deployment configuration
- Feat: enhance torrent status display with peer stats, download speed, and time remaining info+ recreate newer pinned message
- Feat: add document handling support for telegram bot [1]
- Feat: add gpt-5
- Feat: add paginated message support with navigation controls
- Feat: mount config directory to docker container for external configuration
- Feat: add message trimming hook to prevent token overflow in agent conversations
- Feat: clarify routines vs tools distinction and improve media search workflow
- Feat: add error handling and graceful exit for tool fetching failures
- Feat: add telegram markdown v2 formatting support
- Feat: sequential-thinking via sse
- Feat: implement agent swarm 1
- Feat: implement agent swarm 2
- Feat: implement agent swarm 3
- Feat: implement agent swarm 4
- Feat: implement agent swarm 5
- Feat: implement agent swarm 6
- Feat: implement agent swarm 7
- Feat: add agent name to UI logs and improve message formatting
- Feat: add Neo4j container configuration and password environment variable
- Feat: integrate Neo4j graph database with Gemini embeddings
- Feat: create GraphRAG with singleton pattern and initialization flow
- Feat: integrate GraphRAG memory system with agent chat functionality
- Feat: re-add ollama provider
- Feat: skip memory creation for non-meaningful agent responses and add message removal option
- Feat: add checkpointing and message trimming utilities for agent state management
- Feat: add date formatting and edge sorting utilities for entity timeline display
- Feat: enhance memory retrieval with chat history context and filtering
- Feat: disable safety settings for Gemini LLM provider
- Feat: improve memory search and display with formatted nodes/edges and timing info
- Feat: add document management with RAG integration for uploaded files
- Feat: show hidden count in document and download progress messages
- Feat: add docs-ui service to Docker Compose configuration
- Feat: expose docs-ui service on port 4040
- Feat: add dark mode toggle with theme persistence to navbar
- Feat: implement file upload functionality with drag-and-drop UI and progress tracking
- Feat: add restricted component and enhance file upload UI with connection status
- Feat: add file size limit handling and docs UI redirect for large uploads
- Feat: add file upload error handling and filename sanitization in document manager
- Feat: add HTML to Markdown conversion for URLs and images in Telegram messages
- Feat: add audio file support and enhance document preview styling
- Feat: add retry limit and error message for repeated agent interruptions
- Feat: add zip file support and derive accepted extensions from ALLOWED_FILE_TYPES
- Feat: add PDF download button with html2pdf.js integration
- Feat: improve PDF download button UI and optimize handleDownload with useCallback
- Feat: add separate small model configuration and improve context management

- Add GEMINI_API_MODEL_SMALL environment variable for lighter tasks
- Implement PruneHistory middleware with ClearToolUsesEdit to manage context size
- Track tool execution timers across multiple calls in timers_by_tool dictionary
- Migrate from pre_model_hook to pre_agent_hook with improved message trimming
- Increase token limit from 5000 to 6000 and adjust temperature to 0.7
- Use gemini-small model for summarization and memory
- Feat: enhance agent configuration with improved prompts, tools, and UX refinements

- Refine markdown formatting guideline to explicitly prohibit styling elements and allow labeled URLs with emojis
- Add error recovery and clarification guidelines for better agent behavior
- Restructure agent prompts to be more specific about roles and capabilities
- Add common tools configuration (think, write_todos) shared across agents
- Implement TodoListMiddleware and adjust ClearToolUsesEdit trigger from 1 to 100
- Feat: restructure MCP configuration to individual tool files and simplify agent setup

- Migrate from single mcp_config.json to individual tool configuration files in config/tools/ directory
- Add .gitignore rules for config/tools/\* while preserving examples/ subdirectory
- Create example tool configurations organized by category (web, media, utils)
- Remove write_todos tool from common agent tools and related middleware (TodoListMiddleware, ContextEditingMiddleware)
- Simplify agent middleware
- Feat: update default Gemini models to gemini-3-flash-preview and refine thinking configuration

- Switch default GEMINI_API_MODEL from gemini-3-pro-preview to gemini-3-flash-preview
- Update GEMINI_API_MODEL_SMALL to gemini-3-flash-preview
- Update GraphRAG model from gemini-flash-latest to gemini-3-flash-preview
- Add thinking_level configuration for pro models and remove commented thinking_budget
- Bump version to 0.10.2
- Feat: reorganize tools configuration with README, templates, and environment variable support

- Add comprehensive README.md documenting native Python tools and MCP server configurations
- Create \_template.py for easy native tool creation
- Move example tools from examples/ to active config directories (local/, media/, web/, utils/)
- Implement environment variable substitution with {ENV:VAR_NAME} syntax across all tool configs
- Convert sequential_thinking from MCP server to native Python tool
- Feat: remove sequential-thinking-mcp service from Docker Compose configuration

- Remove sequential-thinking-mcp container definition and port mapping (8007:8000)
- Follows migration of sequential_thinking from MCP server to native Python tool
- Feat: simplify routine guidelines by removing redundant summary instruction
- Feat: add list_torrents tool to torrent agent and update docs_ui dependencies

- Add list_torrents tool to torrent agent's available tools in agent config
- Update @biomejs/biome from 2.2.4 to 2.3.10 with CSS Tailwind directives support
- Upgrade Next.js from 15.5.4 to 16.0.10
- Update React from 19.1.1 to 19.2.3 and React DOM accordingly
- Feat: migrate from mypy to ty type checker and improve type safety

- Replace mypy with ty in CI workflow, dev dependencies, and development scripts
- Add ty configuration with no-matching-overload rule ignored
- Remove mypy.ini and pytest.ini configuration files
- Enable deep_search tool by disabling only linkup-fetch instead of entire tool
- Fix type safety issues: add explicit type casts for BaseMessage lists and structured LLM outputs
- Feat: change summary and episodic memory injection from AIMessage to HumanMessage

- Update agent configuration example to explicitly instruct against including chat history, summary, or episodic memory in responses
- Change message type from AIMessage to HumanMessage for both summary and episodic memory injections to prevent model from treating them as its own previous outputs
- Feat: refactor torrent search tools and add YGG API service with improved type safety

- Simplify torrent agent workflow by removing prepare_search_query step and renaming get_magnet_link_or_torrent_file to get_torrent
- Add ygg-api service (uwucode/ygege:develop) with health checks and conditional deployment via YGG_ENABLE
- Expand torrent_search.env with YGGTorrent and LaCale configuration options (credentials, domains, trackers)
- Remove get_torrent_info from disabled tools list in torrent_search
- Feat: rename YGG_BASE_URL to YGG_LOCAL_API and remove LA_CALE_TRACKER from torrent search configuration

- Rename YGG_BASE_URL environment variable to YGG_LOCAL_API for clearer naming
- Update ygg-api service environment variable in extended.yaml accordingly
- Remove LA_CALE_TRACKER configuration option from torrent_search.env.example
- Bump version to 0.10.4
- Feat: migrate from rqbit to Transmission torrent client with improved error handling and UI enhancements

- Replace rqbit with Transmission as the default torrent client across all configurations
- Add TRANSMISSION_ENABLE environment variable for conditional deployment
- Rename rqbit-mcp service to transmission-mcp and update image to philogicae/transmission-mcp:latest
- Update torrent_client.json with expanded disabled tools list for better control
- Replace docker-envs/rqbit.env.example with transmission
- Feat: add automatic media library refresh retry mechanism with 1-minute intervals

- Add recursive refresh_media_lib calls with counter parameter to retry 3 times total
- Implement 60-second delay between refresh attempts for better media indexing reliability
- Feat: upgrade html2pdf.js from 0.12.1 to 0.14.0 and remove deprecated @types/dompurify dependency

- Update html2pdf.js to 0.14.0 which now includes its own type definitions
- Remove @types/dompurify package as dompurify provides built-in types
- Update related dependencies: @babel/runtime, @emnapi/runtime, @swc/helpers, caniuse-lite, jspdf, motion-dom, and motion-utils
- Feat: add whitelist support for tools with `enable` field and rename `disabled` to `disable`

- Add `enable` field to support whitelisting specific tools from a server
- Rename `disabled` to `disable` for consistency across all tool configurations
- Update tool filtering logic to handle both enable (whitelist) and disable (blacklist) approaches
- Simplify torrent_client.json by using `enable` instead of long `disable` list
- Apply whitelist approach to deep_search, news_search, and wiki_search configurations
- Feat: add tool discovery comments to JSON configs and improve tool loading with server path tracking

- Add automatic comments to tool JSON configs listing all available tools with count
- Update tool loading to use full server paths (category/name) instead of just filenames
- Add \_update_tools_comment function to maintain tool lists in JSON files
- Extend ty type checking to include config/tools directory in dev.sh
- Remove disabled filesystem.json configuration file
- Improve error messages with
- Feat: fix Python tool loading to use server_path instead of filename for dictionary key
- Feat: upgrade GitHub Actions and Python to 3.13, replace web_search with searxng and fetch tools
- Feat: add BetaSeries planning integration for episode tracking and new releases
- Feat: enhance BetaSeries integration with episode download tracking and improved authentication
- Feat: upgrade searxng-mul-mcp and add Playwright driver auto-installation with stderr suppression
- Feat: update default Gemini model to gemini-3.1-pro-preview-customtools
- Feat: remove YGGTorrent support and switch LaCale to API key authentication
- Feat: upgrade docs-ui
- Feat: re-add YGGTorrent support with ygege API service and update torrent_search configuration
- Feat: update ygege API image source and bump version to 0.12.0
- Feat: neo4j activate jdk incubator vector
- Feat: update Gemini small model and pin Transmission version with configurable download directory
- Feat: add Transmission configuration management with auto-deployment scripts and DOCKER_HOST support
- Feat: add Fireworks AI provider support with Anthropic-compatible API integration
- Feat: update Transmission tracker list and switch ygg-api to develop-noupx image
- Feat: update Playwright installation to use uvx and add search_docs tool to RAG server
- Feat: add Opencode LLM provider support and improve structured output handling

- Add Opencode provider configuration in .env.example and llm.py
- Add LLM_UTILS environment variable for utility model selection
- Extend langchain dependencies to include openai package
- Implement fallback structured output parsing for providers without native support
- Update summarize_and_rephrase and filter_relevant_memories to use LLM_UTILS
- Add JSON schema appending for non-native structured output providers
- Feat: restrict default agent swarm to core agents and fix AIMessage attribute access

- Limit default agent configuration to Geppetto, Search Agent, and Media Manager
- Fix structured output parsing to use AIMessage.text instead of .content attribute
- Feat: clarify agent handoff terminology and improve transfer conditions

- Update handoff instruction to use "Call it to switch" instead of "You become"
- Replace "delegate" with "switch" in routine steps for consistency
- Remove series planning trigger from find_media routine
- Add series planning to Media Manager transfer condition
- Fix final result detection to check for absence of tool_calls
- Feat: migrate to Telegram HTML formatting, add GREE AC control

- Replace MarkdownV2 with HTML parse mode; add sendRichMessage for final messages
- Rewrite fixed_telegram as native Markdown→HTML converter; drop telegramify-markdown, mcite, html_to_markdown
- Simplify \_dynamic_length (drop quote tracking), pagination, and progress edit logic
- Add GREE/EWPE AC tools (native UDP + AES protocol, scan/bind/status/command)
- Add "Home Assistant" sub-agent with AC tools to agent config
- Add user_config.example.json, GREE_MCP_CONFIG env var, compose volume mount
- Remove unused WHITELIST from .env.example
- Feat: add voice and image message handling with multimodal support

- Add telegram_voice and telegram_image handlers with Gemini multimodal support
- Implement media group accumulation and debouncing for photo albums
- Add pending_media storage for captionless images awaiting text context
- Add \_media_to_text fallback for non-multimodal LLMs (transcription/description)
- Add \_is_multimodal check based on LLM_CHOICE and LLM_UTILS providers
- Conditionally register voice/image handlers when GEMINI_API
- Feat: add AC telemetry logging and graphing with multi-threaded background collection

- Add graph_home_ac tool to Home Assistant agent for temperature/humidity visualization
- Implement background telemetry thread with configurable interval (default 5min)
- Add SQLite-based time-series storage with automatic schema migration
- Add matplotlib-based graphing with dual y-axis (temp/humidity) and color-coded segments
- Refactor GREE AC client into class-based architecture with proper locking
- Add graceful shutdown handling via signal handlers and atexit registration
- Feat: add multi-image support and enhance markdown formatting with task lists and marked text

- Add support for multiple images in tool results with batched media group sending (max 10 per batch)
- Change extra["image"] to extra["images"] list accumulation with pending_images tracking
- Add markdown image syntax support with optional captions using HTML figure/figcaption
- Add task list support with checkbox rendering for `- [ ]` and `- [x]` items
- Add ==marked== text support with HTML mark tag
- Feat: add timezone helper and improve file permissions handling in GREE AC module
- Feat: refactor GREE AC config to per-device file structure and improve telemetry isolation

- Replace single GREE_MCP_CONFIG file with per-device config.json files in data/gree_ac/{mac}/
- Remove GREE_MCP_CONFIG environment variable and compose volume mount
- Add \_device_dir helper to create mac-based subdirectories (config, telemetry, graphs)
- Update \_persist to write individual device configs instead of merged JSON
- Add mac parameter to \_record_event, \_telemetry_fetch, \_query_readings, and \_generate_graph
- Feat: optimize AC telemetry graphing with deduplication and downsampling

- Add \_dedup_unchanged to collapse consecutive identical readings while preserving run boundaries
- Add \_downsample for uniform thinning to max points (1000 graph, 200 series)
- Add room_temp_min/max/avg and series array to \_summarize_readings output
- Update \_generate_graph to use \_downsample instead of fixed step sampling
- Add status parameter to \_sync_device_time to reuse already-fetched status
- Add tzdata package to Dockerfile
- Feat: replace host timezone mounts with TZ environment variable

- Remove /etc/localtime and /etc/timezone volume mounts from compose.yaml
- Add TZ environment variable with UTC default fallback
- Add commented TZ example to .env.example
- Feat: add image generation tool and improve graph smoothing

- Add generate_image tool using Gemini Nano Banana with image modality support
- Add GEMINI_API_IMAGE_MODEL environment variable to .env.example
- Fix graph smoothing to use linear x-interpolation instead of cubic to prevent time reversal
- Update agent to collect both graph_path and image_path from tool results for display
- Feat: improve image generation prompting and add rich message fallback handling

- Add "Image Creator" sub-agent with generate_image tool to agent config
- Rewrite generate_image prompt parameter description with domain-specific style guidance (artistic, technical, diagram, photographic, logo) and structured JSON schema examples
- Add negative_prompt requirement to always exclude default Gemini aesthetic
- Remove \_smooth Catmull-Rom interpolation from AC graphing (use raw linear plot)
- Feat: add Image Creator to allowed agents in user config example
- Feat: update Transmission tracker lists and improve deployment scripts
- Feat: add moving averages, AC run shading, and enhanced graph legend to GREE AC telemetry
- Feat: consolidate GREE AC tools into unified set_home_ac interface and add schedule management
- Feat: add independent vertical and horizontal swing control to GREE AC

- Add swing_vertical and swing_horizontal parameters to set_home_ac tool
- Support granular louver positioning (fixed positions, partial swings, full swing)
- Maintain backward compatibility with existing oscillation parameter
- Add validation and error messages for invalid swing values
- Feat: add local schedule cache fallback for GREE AC devices that don't support queryT
- Feat: replace hardware timers with software scheduler and add clock offset tracking to GREE AC
- Feat: improve AC graph readability and add image cleanup

- Replace EMA with SMA (adaptive window: max(3, min(10, n//20)))
- Add absolute temp diff line on right y-axis (scale 0-20, integer ticks)
- Simplify legend: Room, Target, Diff, SMA, User Action, Scheduled
- Move event dots under target line; scheduled in violet, user in white
- Brighter grey grid (#555555, alpha 0.3)
- Remove info text box overlay, move legend to upper left
- Delete generated PNGs after sending via Telegram
- Feat: disable think tool and add anti-text safeguards to image generation

- Comment out think tool from default agent config and new_releases routine
- Rename sequential_thinking.py to \_sequential_thinking.py (disabled)
- Add explicit anti-text instructions to image generation prompt description
- Require natural-language color names instead of hex codes in prompts
- Add text/labels/watermarks to default negative_prompt list
- Clarify that text in images requires explicit specification
- Feat: harden agent completion detection and telegram result routing

- agent.py: replace step-prefix heuristic with the done flag to detect
  genuine final replies, since LLM answers can legitimately start with
  a checkmark/cross emoji, which previously caused valid replies to be
  discarded and retried up to 3 times before falling back to a fake
  internal-error message
- handlers/telegram.py: gate tool-notify/error-report branches on
  not done to avoid misclassifying a final answer starting with an
  emoji as a tool result, which could trigger bogus error reports
- graphiti.py: stop mutating the shared global SearchConfig default
  (COMBINED_HYBRID_SEARCH_RRF) on every search call; copy it instead
- instances/telegram.py: drop dead duplicate branch in edit()
- uv.lock: refresh after uv sync
- Feat: bump to Python 3.14, v0.15.0; remove ygg-api, update Transmission, fix syntax

- Bump `requires-python` to `>=3.14` and version to `0.15.0`
- Remove `ygg-api` service and `ygg-config` volume from compose
- Update Transmission image to `4.1.3`
- Make `torrent_search.env` optional; drop `YGG_LOCAL_API` env
- Adopt PEP 760 bare except syntax (`except ValueError, TypeError:`)
- Drop forward-reference strings from type hints
- Regenerate `uv.lock` for Python 3.14 (cp314 wheels, dep bumps)
- Misc CI, Dockerfile, README, config updates
- Feat: Python 3.14, ruff config overhaul, lint fixes, shell tooling

- Bump target to Python 3.14 (ruff target-version, requires-python)
- Replace ruff `select = ["ALL"]` with explicit rule sets + categorized ignores + per-file-ignores for tests
- Remove stale `# noqa:` comments across all files (SLF001, ARG001, etc.)
- Add explicit `strict=False` to all `zip()` calls; fix bare excepts with logging in gree_ac.py
- Switch telegram handler file ops to async (`aiofiles.os.path.exists`, `aiofiles.os.unlink`)
- Sort `__all__` lists alphabetically in telegram_agent package
- Add bash formatting (`shfmt`) and linting (`shellcheck`) to `dev.sh`
- Replace unsafe `.env` sourcing (`cat | xargs`) with `set -a; source .env` in deploy scripts
- Alphabetically sort dependencies in pyproject.toml (no additions/removals)
- Feat: TTS via OpenRouter, Dev Agent via Opencode ACP, infra polish

- TTS: /tts toggle, LLM.tts() via OpenRouter audio API, ffmpeg OGG conversion for Telegram voice messages, "listening→thinking" flow for voice inputs
- Dev Agent: config/tools/acp/opencode.py — async client for opencode acp HTTP API (list_sessions, init_session, resume_session), Dev Agent config with routines
- Infra: Dockerfile ffmpeg, .dockerignore, .env.example new vars (OpenRouter, SEARXNG, OPENCODE_ACP)
- Deps: pyTelegramBotAPI 7.31.0, fastapi 0.140.7, fastmcp 3.4.5, graphiti-core 0.29.3, langchain-mcp-adapters 0.3.1
- Chore: rstrip→removesuffix in tool loader, singleton init guard in LLM, BotCommand registration
- Feat: overhaul web search stack, add abort/edit tools, LLM-based TTS adaptation, Docker app user

- Web tools: Add _web_search (DDG), multi_search (searxng-mul-mcp), scrapling (anti-bot), web_fetch (fetcher-mcp), wiki_search.py (intelligent wiki). Rename deep_search/wiki_search → _ disabled. Remove old fetch.json, searxng.json. Switch news_search to @brave/brave-search-mcp-server, use brave_news_search.
- ACP: Add abort_session/delete_session. URL-encode session IDs. Validate URL/password on parse. Clean up orphaned sessions on init_session failure.
- Image gen: Add edit_image tool (Gemini). Rewrite prompt instructions with cohesion/language rules. Add \_load_image_data_url helper.
- Agent config: Parallel tool call guidance. Search agent: 3-phase pipeline (EXPAND→SEARCH→SYNTHESIZE), restructured routines (research/fact_check/crawl/news_briefing/scrape_page). Image Creator: edit_image tool. Coder: cancel_task routine + abort_session.
- TTS: Replace regex sanitization with LLM.tts_adapt() — rewrites markdown/emoji/URLs for natural speech via utils LLM. Emotion-matching instructions in TTS API call. Recording status + logging in Telegram handler.
- Playwright install: Rewrite to use patchright + @playwright/cli, colored output, npm/sys dep checks, dry-run flag.
- Tools config: {ENV:VAR:-default} syntax, strip server descriptions, unwrap ExceptionGroup in error display.
- Dockerfile: Add app user (uid 1000) for shared volume permissions, switch to non-root.
- Trackers: Prune dead entries, keep verified trackers.
- Env: SEARXNG_BASE_URL/PORT/CONFIG/SECRET, SCRAPLING_BASE_URL, updated OPENCODE_ACP_URL.
- Feat: migrate HeroUI v2→v3, drop framer-motion, bump deps

- `@heroui/react` 2→3: CardBody→Card.Content, Progress→ProgressBar, disabled→isDisabled, flex-shrink-0→shrink-0
- Replace HeroUI tailwind plugin with `@import "@heroui/styles"`, remove HeroUIProvider wrapper
- Drop framer-motion (bundled in HeroUI v3)
- Dep bumps: next 16.1→16.2, react 19.2.4→19.2.8, TS 5.9→6.0, Biome 2.4→2.5, Tailwind 4.2→4.3, PostCSS 8.5→8.24, and others
- Biome config: recommended→preset
- Feat: stream model reasoning text alongside tool calls in Telegram

- Agent.chat yields model_text events for `msg`-type messages (text alongside tool calls); extra dict typed as Any
- TelegramBot.edit gains model_text flag: caches and displays inline reasoning (marked with \x00 sentinel, excluded from tool logs)
- Suppress tool notifications/error reporting when emitting model_text
- logify strips \x00 sentinel from rendered output
- Feat: image inspection tools, per-chat cancel/rate-limit, TTS speed, telemetry pruning, README rewrite

## New features

- image_processing.py: new `list_images` (paginated) and `read_images` tools
  for browsing/describing images on disk via Gemini vision; descriptions
  cached to `*_desc.txt`, per-image errors never fail the batch
- agent_config/user_config: rename "Image Creator" → "Image Manager" with
  `list_images`/`read_images` tools and updated transfer prompt
- telegram handlers: `/cancel` command + per-chat `cancel_events` rate
  limiting (TOCTOU-safe claim before any await); voice/image handlers
  reject early before expensive work
- telegram handlers: persist received images to `image_received/`, pass
  file paths to the agent (multimodal) or per-image descriptions to disk
  (non-multimodal) so context survives across sessions
- telegram handlers: `upload_photo`/`upload_voice` chat actions, caption
  above media, user-facing TTS failure notice
- llm.py: `OPENROUTER_TTS_SPEED` env var (default 1.15) with range clamp
  to [0.25, 4.0]; rewritten TTS instructions for expressive delivery
- llm.py: `tts_adapt` now preserves full content (speakable rewrite, not
  a summary) and reads code/commands naturally
- gree_ac.py: `all` range + `1m` unit (up to 24m), `_dedup_events` to
  collapse repeated telemetry events, default range → "all"; `limit=None`
  in `_query_readings` with pre-computed start/end strings
- graphiti.py: wrap genai.Client to inject BLOCK_NONE safety settings on
  every generate_content call (covers GeminiClient + reranker)
- image_generation.py: add BLOCK_NONE safety settings

## Bug fixes

- image_processing.py: `_describe_image` wrapped in try/except so an LLM
  failure returns a per-image error string instead of crashing the batch;
  returns explicit error string (not None) when no API key configured
- telegram_image: check `cancel_events` before storing `pending_media` to
  prevent orphaned images leaking into the next successful message
- abstract.py: cap 429 flood-wait `retry_after` to 60s with warning log
- abstract.py: abort retries immediately on "message to edit not found"
- gree_ac.py: make event markers timezone-aware (`.replace(tzinfo=_local_tz())`)
  and remove now-unnecessary tz-stripping logic in range comparison

## Refactors

- utils.py: lift nested markdown→HTML helpers to module level; add `classic`
  flag to `fixed_telegram` (rich tags for sendRichMessage, sanitized for
  classic API); innermost-first list sanitization loop
- instances/telegram.py: extract `_is_private_or_reply` and `_render_logify`
  to module level; final messages use `classic=False` (rich), intermediate
  edits use `classic=True` with try/except to swallow edit failures
- image_generation.py / gree_ac.py / utils.py: replace `parents[3]` path
  hack with `DATA_DIR` env var (matches compose `DATA_DIR=/app/data`)
- agent.py: `datetime.now(UTC)` → `datetime.now().astimezone()` for local TZ

## Chores

- README.md: full rewrite (features, quick start, CLI, configuration,
  project structure, development); drop PyPI badge, remove Graphiti refs
- pyproject.toml: bump version 0.15.0 → 2.0.0
- .env.example: document `OPENROUTER_TTS_SPEED`
- .gitignore: ignore `TODO.md`
- compose.yaml: shfmt YAML anchor spacing
- uv.lock: langsmith 0.10.14, posthog 7.35.4
- Feat: persist opencode sessions to JSONL, rework ACP dev agent persona

- opencode.py: new persistence layer — per-server dir (host_port) under DATA_DIR/opencode, upserts sessions into opencode_sessions.jsonl keyed by id, sorted newest-first by time.created, 0777 chmod; best-effort (suppress) persist calls in list_sessions, init_session, resume_session
- agent_config.example.json: rename "Dev Agent" → "Opencode Dev"; rewrite prompt — casual teammate tone, no verbatim tool dumps (except list_sessions results, which must be reported truthfully), no sycophancy, TTS-friendly output; new_task no longer pre-checks list_sessions, resume_task now looks up session_id via list_sessions when unknown; drop \n\n escapes from prompts
- Feat: rename opencode tools to `*_dev_session` for clarity

- opencode.py: `list_sessions` → `list_dev_sessions`, `init_session` → `init_dev_session`, `resume_session` → `resume_dev_session`, `abort_session` → `abort_dev_session`
- agent_config.example.json: update Opencode Dev prompt, routines, and tools list to reference renamed tools
- Feat: add optional prompt param to read_images tool
- Feat: live progress streaming, timeout re-attach, and instant image acknowledgment

- Add `progress.py`: ContextVar-based progress sink + ProgressTracker (rolling
  status/session-link/logs panel, dedup-on-emit, in-place line updates, HTML-escaped)
- Add `watch_dev_session` tool: re-attach to a timed-out run, poll until idle,
  return the final result without sending a new message
- Stream live progress (tool/reasoning/text/patch parts) to Telegram chat via a
  parallel watcher polling `/message` every OPENCODE_SERVER_PROGRESS_POLL seconds
- Treat timeouts as non-error markers (`timeout: true`), not failures; lower the
  default timeout from 1200 s to 600 s
- Add `session_url` (base64url-encoded web link) to all session/run result shapes
- Accumulate per-turn `tool_block` live status across multiple tool calls; switch
  the handler from `step[0]` emoji sniffing to the `extra["tool_ok"]` flag
- Fold the live tool block into the tool-logs code block, separate from model text
- Rework `telegram_image`: send "🔍 I'm analyzing..." immediately on photo/album
  receipt, then edit in place through waiting → final result; albums send the ack
  once from the first callback before debounce
- Refactor opencode config: single `_CONFIG_ERROR` at startup + `@_require_config`
  decorator, removing repeated `if not _BASE_URL` checks
- Trim `_persist_sessions` JSONL cache to `_MAX_CACHED_SESSIONS` (default 100)
- Update Opencode Dev persona and routines: `wait_task` routine, session-link
  reporting, `watch_dev_session` in the tools list
- Add env vars: OPENCODE_WEB_URL, OPENCODE_SERVER_PROGRESS_POLL/LINES, OPENCODE_SERVER_MAX_CACHED_SESSIONS
- Feat: add Documentalist agent and refresh torrent tracker list
- Feat: add Opencode Zen free tier support with separate model config

- .env.example: add OPENCODE_FREE_API_MODEL (x-preview-f-free), update default OPENCODE_API_MODEL to deepseek-v4-flash, switch LLM_CHOICE/LLM_UTILS to opencode-free
- llm: register opencode-free provider pointing to opencode.ai/zen/v1 endpoint with reasoning_effort=low when OPENCODE_FREE_API_MODEL is set
- Feat: add opencode-alt provider with ox-alpha-free model, switch default LLM from opencode-free

- .env.example: add OPENCODE_API_MODEL_ALT (ox-alpha-free), update LLM_CHOICE/LLM_UTILS from opencode-free to opencode-alt
- Feat: unify LLM response parsing with reasoning extraction

- add extract_response(): handles <think> tags, Anthropic thinking blocks,
  DeepSeek reasoning_content kwargs; reuse in agent, tts_adapt,
  parse_structured_output and media transcription instead of hand-rolled joins
- show model reasoning as its own console panel, never leak it into replies
- parse_structured_output: try fenced block then braces fallback
- agent: guard IndexError on state with fewer than 2 messages in retry loop
- tools: quote MCP stdio commands via shlex.join, regex-safe config comment update
- add langchain deepseek extra, drop OPENCODE_FREE_API_MODEL from env example
- Feat: env-driven model capability system and persistent progress panel

- declare per-model capabilities via '<model>|<opt1>+<opt2>' suffixes in
  \*\_API_MODEL env vars (text, vision, stt, video, pdf, image, tts,
  structured); parsed once into SPECS/CAPABILITIES, exposed through
  supports() and semantic helpers can_read/can_see/can_listen/can_watch/
  can_docs/can_speak/can_draw/can_struct
- replace LLM_CHOICE/LLM_UTILS with comma-separated LLM_ORDER/LLM_ORDER_FAST:
  first configured provider wins, first capable provider selected when a
  capability is required (fast list falls back to main order, then any aux
  endpoint) via new LLM.pick(); delete \_is_multimodal() — call sites check
  can_see/can_listen on the resolved main model; media fallback transcribes
  via first capable provider instead of hardcoded gemini-small;
  OPENROUTER_TTS_MODEL unified as the 'openrouter-tts' aux endpoint,
  selectable via pick('tts') and gated in the /tts flow; image tools split
  suffixes locally with current models as defaults
- add runtime failover across providers: failures immediately fall back to
  the next candidate in utils.run_schema() (shared runner for schema calls,
  dedupes resolve+branch code); each failure counts a strike with a 300s
  cooldown (LLM_DEAD_COOLDOWN) and 3 consecutive strikes jail a provider
  for 24h (LLM_JAIL_STRIKES/LLM_JAIL_HOURS) until auto-release;
  mark_alive() clears history on success
- fix inline media crashing OpenAI-compatible APIs with raw bytes dicts:
  convert internal media at the single HumanMessage choke point into proper
  multimodal blocks — images as image_url data URLs (spoken by openai and
  google integrations), audio as input_audio base64; unmasked by vision-
  capable non-Gemini models now going inline instead of transcription
- replace hardcoded SUPPORT_STRUCTURED_OUTPUT set with capability lookups;
  restore native structured output branch gated on 'structured' (JSON-prompt
  fallback otherwise); strip suffixes before API calls in all model reads
- fix progress logs disappearing on consecutive tool runs: share one
  ProgressTracker per turn via ContextVar instead of a fresh tracker per call;
  move OPENCODE_SERVER_PROGRESS_LINES parsing to tolerant default_max_lines()
- document capability suffixes, provider run orders and failover knobs in
  README.md and .env.example
- Feat: drop GraphRAG/neo4j memory stack, parse .env safely in deploy scripts

- remove graphiti-core integration entirely: GraphRAG singleton, episodic
  memory recall/write blocks in agent loop, --clear CLI flag, memory
  helpers (filter_relevant_memories, sort_edges, format_date) and exports
- drop deps: graphiti-core[google-genai], nest-asyncio; evicts now-orphaned
  transitives (neo4j, backoff, posthog, pytz)
- remove NEO4J\_\* vars from env files and commented neo4j service from compose
- scripts/load-env.sh: docker-style dotenv parser; deploy-agent.sh and
  deploy-tools.sh no longer `source .env` (values may contain shell
  metacharacters like `|` in model capability strings)
- keep ReContext summarization (run_schema/summarize_and_rephrase) untouched
- parenthesize except tuple in **main**.py for explicitness (py3.14 accepts
  both forms with identical semantics)
- chore: bump version to 2.2.0, add init:true to torrent-search-mcp
- Feat: remove opencode-alt provider, add torrent-search-api service, enforce user allowlist

- .env.example: drop opencode-alt from LLM_ORDER/LLM_ORDER_FAST (opencode now first)
- README.md: fix table formatting, clarify user_config rejects unlisted users
- agent_config.example.json: add scrapling request session tools (make_request, open_request_session, session_fetch, session_make_request), remove deprecated 'get', update Torrent Agent routine to use popular_torrents instead of Search Agent transfer
- Feat: rework torrent manager, add tracker maintenance scripts

- rework DownloadManager: Torrent/Message models with lifecycle states
  (done/gone/nearly-done), poll failure cutoff (\_MAX_FAILURES=3), vanished
  torrent at >=95% counts as completed; single-flight Emby refresh spawns
  (files-created / 50% / completion milestones) guarded by \_refresh_task.done();
  per-chat pinned status panel rebuilt via create_message() — top-3 torrents
  by active download, others collapsed into '+N more in queue'
- fix message.prev never stored after send/edit: every monitoring cycle
  re-edited identical text, hitting "message is not modified" and falling
  into the resend+repin path forever
- docker-envs: add ping_trackers.py (UDP connect-ping + DNS check, prunes
  dead trackers from transmission.trackers.txt) and update_trackers.py;
  refresh tracker list
- transmission.config.json: fixed peer port 52317, enable DHT/PEX/LPD/uTP,
  64MB cache, explicit bind addresses, replace dead default trackers
- Feat: add HTTP relay, user stats, and torrent-search webapp pairing

- Add token-authed /relay HTTP endpoint (AGENT_RELAY_TOKEN/PORT) so services
  can inject prompts into the agent pipeline; runs alongside the bot
- Add persistent per-bot/per-chat interaction stats (users.json) with
  debounced atomic writes; register every incoming message
- Prefix agent memory with [chat_id:...] for multi-chat context isolation
- Rename TELEGRAM_BOT_ID(\_DEV) to TELEGRAM_BOT_TOKEN(\_DEV) everywhere
- Add torrent_webapp + authorize_webapp tools, webapp pairing and relay
  forwarding env vars, PRUNE_MAGNET_LINKS; persist torrent-search data via
  docker volumes; switch to --mode api
- Bump to 2.3.0, update deps (anthropic, langchain, uv.lock), refresh
  transmission default trackers, tidy tool loading in agent config

### 🐛 Bug Fixes

- Fix: add null check for usage_metadata and update dependencies
- Fix: docker compose setup
- Fix: better mcp config example
- Fix: bug hunting
- Fix: handle empty text when step is a completion emoji
- Fix: various bugs and ajustments
- Fix: update file paths in deploy script and gitignore to match new docker-envs directory
- Fix: delete disabled flag from server settings before processing
- Fix: update new_releases meta-procedure in prompts
- Fix: disable forget_torrent and enable delete_torrent in config
- Fix: prevent duplicate error notifications when error occurs in dev chat and update torrent priority rules
- Fix: handle empty config case in get_tools by returning empty list
- Fix: remove unnecessary config file copies from Dockerfile
- Fix: remove unnecessary quotes around command in compose.yaml
- Fix: many bug / edge case fixes
- Fix: disable_web_page_preview is deprecated
- Fix: remove openai base url parameter from ChatOpenAI initialization
- Fix: gracefully handle keyboard interrupt in CLI
- Fix: adjust message length calculation
- Fix: increase HTTP client timeout from 10s to 30s and update markdown-it-py to 4.0.0
- Fix: add type ignore comment for timeout assignment in client connections
- Fix: reduce max token limit to 5000 and remove allow_partial flag in message trimming
- Fix: update data volume path and use in-memory checkpointer for dev mode
- Fix: 10000 tokens context
- Fix: gemini bug + fallback gemini-openai provider
- Fix: pagination not required on extended text
- Fix: improve tool result edit detection
- Fix: handle case when agent message has no name attribute
- Fix: simplify handoff message template in agent config
- Fix: update handoff message template with clearer agent transition instructions
- Fix: only send error message to dev chat when not originating from dev chat
- Fix: exclude duplicate edges from graph by filtering IS_DUPLICATE_OF relationships
- Fix: improve document upload timeout detection by checking both time and progress
- Fix: download manager
- Fix: cleanup docs_ui
- Fix: properly initialize theme from localStorage and apply dark mode on page load
- Fix: improve error logging for oversized file uploads in Telegram bot
- Fix: improve filename sanitization and error logging in telegram bot
- Fix: clean up extra whitespace and newlines in Telegram message formatting
- Fix: add agent interruption recovery, improve context handling and summarization/rephrasing
- Fix: add error handling and logging for document status updates in telegram bot
- Fix: handle case when result has no memories attribute in filter_relevant_memories
- Fix: add error handling for Telegram message operations and update language guideline
- Fix: improve error message to indicate users can retry after failure
- Fix: pin langchain dependencies to v0 and improve error logging in telegram handler
- Fix: improve MCP transport detection and add explicit network configuration

- Change MCP transport detection from endswith to contains check for more flexible URL matching
- Add explicit IPAM configuration with IPv4 and IPv6 subnets to ai-agent network
- Fix: migrate deep-search MCP to serverUrl transport and reduce memory search limit

- Change deep-search MCP from command to serverUrl transport with API key in URL
- Rename search-web tool to linkup-search and disable linkup-fetch
- Reduce memory search limit from 50 to 25 for better performance
- Fix: upgrade to langchain v1.0 and improve agent messaging and memory handling

- Upgrade langchain dependencies from v0 to v1.0 and update langgraph-swarm to langchain_v1.0 branch
- Update Gemini model reference from gemini-pro-latest to gemini-3-pro-preview
- Migrate from langchain_core to langchain for messages and tools imports
- Replace create_react_agent with create_agent and update middleware configuration
- Add tool execution timer display in status messages
- Improve tool error handling
- Fix: reduce context
- Fix: clarify markdown styling restrictions and add explicit warning about blocked characters
- Fix: rename grokipedia MCP tools to wiki_search and fetch_wiki_page

- Rename grokipedia_search to wiki_search and fetch_grokipedia_page to fetch_wiki_page
- Update research_topic workflow steps to use new tool names
- Add explicit description for wiki_search tool
- Remove disabled tool configurations (get_page, get_page_citations, etc.)
- Rename MCP server key from "grokipedia" to "wiki-search"
- Fix: handle message editing errors in download manager by sending new pinned message

- Add try-except block around message edit operation in download progress updates
- On edit failure, send new message and pin it instead of failing silently
- Log ignored editing errors for debugging purposes
- Fix: mapped volumes
- Fix: update deps + markdownify
- Fix: remove standalone output mode from docs-ui Next.js config
- Fix: add ruff linting config and resolve code quality issues
- Fix: handle 504 errors gracefully — timeout, retry backoff, broader exception handling

- \_rich_request: add 30s timeout and raise_for_status() to prevent hangs
  and crash on non-JSON 504 responses
- \_send_rich: catch Exception broadly instead of specific types —
  json.JSONDecodeError from 504 HTML body was slipping through
- \_exec: add delay between retry attempts to avoid request bursts on
  transient failures
- DownloadManager.start(): wrap loop in try/except so unhandled
  exceptions don't kill the manager task and stop the bot
- Fix: replace SMA with EMA smoothing and ensure float temperature sensor values in GREE AC
- Fix: add explicit mcp dependency with version constraint >=1.28.0,<2.0.0
- Fix: network-aware retry backoff, structured JSON image descriptions, tz-aware AC graphs, docker network cleanup, openai bump

- bot/abstract.py: detect network errors (RequestTimeout, aiohttp ClientConnectionError)
  in \_exec retry loop; exponential backoff 1s→10s cap instead of flat 0.2s delay,
  so DNS/connection blips don't burn the retry budget
- bot/instances/telegram.py: rich-message send no longer forces retries=0 —
  inherits backoff so transient network errors retry before falling back to stripped content
- bot/handlers/telegram.py: \_media_to_text now returns a structured JSON description
  (same schema as generate_image) with uncensored content coverage; media cache
  sidecar renamed \_desc.txt → \_desc.json
- tools/media/image_processing.py: description prompt reworked to emit structured
  JSON matching the generate_image schema (subject, composition, environment,
  lighting, colors, style, prompt synthesis) for reuse in edits/regeneration;
  markdown-fence stripping; results cached as pretty-printed .json sidecars via
  \_parse_desc/\_desc_path_for; all content described factually including nudity/
  sexual/violent elements
- tools/media/image*generation.py: drop invalid HARM_CATEGORY_IMAGE*\* entries from
  \_SAFETY_SETTINGS (rejected by Gemini image models); add CONTENT POLICY to
  generate/edit prompts; document disk-path editing without multimodal vision
- tools/home/gree_ac.py: temperature graph timestamps made tz-aware (local tz)
- agent_config.example.json: add "Untrammelled Autonomous Agent" root prompt
  (no refusals, no safety framing) and rewrite Image Manager prompt for
  unrestricted image generation
- compose.yaml: move services off network_mode: host onto shared ai-agent bridge
  network (IPv4+IPv6) with quad9 DNS (x-dns/x-networks anchors); define the
  network here as the source of truth
- extended.yaml: declare ai-agent network external (defined in compose.yaml) —
  deduplicates the network definition
- Fix: switch torrent-search-mcp from SSE to HTTP mode, refresh tracker list

- config/tools/media/torrent_search.json: change endpoint from `/sse` to `/mcp`
- extended.yaml: update torrent-search-mcp command from `--mode sse` to `--mode http`
- docker-envs/transmission.trackers.txt: refresh tracker list (add archive.torrentonline.cc, obey.torrentonline.cc, whybother.torrentonline.cc, tracker.breizh.pm, tracker.nyaa.net, lucke.fenesisu.moe; remove zer0day.ch, tracker.wildkat.net, tracker.dler.org, tracker.0
- Fix: keep waiting marker in tool logs when panel is absent (model_text or tool_block)

- \_render_logify: replace `if model_text` condition with `has_panel = bool(model_text or tool_block)` to strip waiting marker when either panel component exists, not just model_text
- Fix: skip swarm creation when no agents match filter, prevent restricted graph crash

- config: return None from get_agent_config when only_agents filter yields zero matches instead of raising ValueError
- agent: guard restricted swarm creation with `if restricted.config` check to skip when Documentalist is unavailable
- agent: check config existence before creating user group swarms, continue loop when None

### 💼 Changes

- Init
- Config: adjust ollama context and prediction limits for CPU-only mode
- Config: add LangSmith environment variables and enable n8n runners
- Merge branch 'graph-rag'
- Init docs ui
- Fix concurrent user request handling and event-loop blocking

The bot could not handle multiple users simultaneously due to several
event-loop blockers and a global rate-limit gate that serialized all
Telegram API calls across chats.

- utils: convert summarize_and_rephrase and filter_relevant_memories
  from sync .invoke() to async .ainvoke() — these blocked the entire
  event loop during ReContext and memory filtering (2-10s freezes)
- abstract: replace last_call/\_is_free busy-wait with asyncio.Lock +
  monotonic throttle that yields during the gap, so cross-chat API
  calls run concurrently instead of serializing on a shared timestamp
- agent: raise max_concurrency 1→4 so multiple tools in one turn run
  in parallel; await the now-async utils functions at their call sites
- agent: fix ReContext thread_id accumulation — derive new thread_id
  from base_thread_id instead of the resolved one, preventing suffix
  stacking on repeated compressions
- handlers: reduce per-step sleep 0.5s→0.1s for faster UI updates;
  make \_save_received_image async with aiofiles instead of sync
  write_bytes that blocked the event loop
- instances: use edit_cache.pop(id, None) instead of check-then-del
  to avoid KeyError on concurrent access
- opencode: make \_persist_sessions async with aiofiles and protect
  the full read-modify-write cycle with asyncio.Lock to prevent
  lost-update races on the sessions JSONL file

### 🚜 Refactor

- Refactor: rename mcp_config.json.example.json to mcp_config.example.json
- Refactor: simplify Docker build and improve container configuration
- Refactor: update agent prompt to be more precise and direct in tool usage
- Refactor: reorder docker-compose service properties and add restart policy for rqbit
- Refactor: update docker compose files
- Refactor: move agent module into core package
- Refactor: improve logging and datetime handling across bot and agent components
- Refactor: various improvements
- Refactor: improve tool execution feedback with progress bar and pinned downloads
- Refactor: move rate limiting and abstract methods to Bot base class
- Refactor: update telegram file handler to process document metadata from Message object
- Refactor: split deploy scripts and update network configuration for IPv6 support
- Refactor: enable pre-model hook and checkpointing in Agent initialization
- Refactor: switch container networking from bridge to host mode
- Refactor: remove unused text escaping functions from utils.py and update dependencies
- Refactor: implement LLM singleton and improve memory search context handling
- Refactor: reorganize LLM providers and utils with thread-safe singleton
- Refactor: reorganize telegram bot handlers/managers and add required chat handler validation
- Refactor: utils methods
- Refactor: disable memory debug output and comment out unused memory stats
- Refactor: migrate file upload handling to external RAG service and add preview functionality
- Refactor: replace Loading component with Generating and update upload icon
- Refactor: update UI components with consistent styling and rename Generating to Previewing
- Refactor: improve HTML to Markdown conversion with proper image alt text and report ID quoting
- Refactor: simplify agent handoff prompt template to be more direct
- Refactor: clarify agent handoff message to prevent delegation behavior
- Refactor: update CHANGELOG.md format and git-cliff configuration
- Refactor: consolidate langchain dependencies using extras syntax and add error handling to dev.sh
- Refactor: extract idle/message polling into reusable helpers, unify timeout handling

- Extract `_wait_for_idle` and `_wait_for_message` from `watch_dev_session` into standalone async helpers
- `_run_with_watcher`: wrap `_client.prompt` in `asyncio.wait_for` with deadline-based timeout, then poll for idle + newest assistant message to ensure we capture the final result even if the prompt call returns early
- `watch_dev_session`: replace inline polling loops with `_wait_for_idle` + `_wait_for_message`

### 📚 Documentation

- Docs: add CHANGELOG.md to track project changes and features
- Docs: update CHANGELOG with timing metrics, Docker improvements and dependencies
- Docs: update changelog with telegram bot integration and major agent rework features
- Docs: update changelog with Gemini support, Docker improvements and bug fixes
- Docs: update changelog with new features, bug fixes, and dependency updates
- Docs: update changelog with agent swarm features and performance improvements
- Docs: update changelog with agent name handling and dependency updates
- Docs: add agent name to UI logs and update changelog entries
- Docs: update changelog with Neo4j integration, memory system and agent improvements
- Docs: clarify handoff prompt to ensure agents continue task execution
- Docs: clarify handoff message to prevent transfer acknowledgements
- Docs: clarify markdown formatting guidelines in agent config

### ⚡ Performance

- Perf: optimize flag check by limiting text sample to first 50 chars

### 🎨 Styling

- Style: update memory headings and fix URL capitalization in config example
- Style: hide report ID elements in preview mode
- Style: update preview container layout to use flex-col and center alignment

### ⚙️ Miscellaneous Tasks

- Chore: add --fix flag to ruff check command in dev script
- Chore: add langchain dependency with version 0.3.25
- Chore: update docker compose with metatool services
- Chore: update dependencies
- Chore: update dependencies and add torrent-client config example
- Chore: upgrade rqbit to 9.0.0-beta.1 and update langgraph/langsmith dependencies
- Chore: cleanup
- Chore: upgrade groq to 0.29.0 and grpcio to 1.73.1
- Chore: update rqbit image to version 9.0.0-beta.1
- Chore: update dependencies and modify torrent list comment in agent.py
- Chore: update dependencies
- Chore: add aiohttp
- Chore: update deps
- Chore: upgrade langgraph to 0.5.1 and remove version specifiers from dependencies
- Ci: optimize GitHub Actions workflow with uv cache and tagged releases
- Chore: update dependencies including mypy 1.17.0 and jsonschema 4.24.1
- Chore: update dependencies including authlib, fastmcp, mcp and ruff
- Chore: update rqbit-mcp dependency from 0.6.1 to 0.7.0
- Chore: update deps
- Chore: bump anyio to 4.10.0 and rqbit-mcp to 0.7.1
- Chore: update deps
- Chore: update dependencies and switch to using published Docker images
- Chore: update deps
- Chore: bump langchain-openai to 0.3.29 and openai to 1.99.4
- Chore: update charset-normalizer dependency from 3.4.2 to 3.4.3
- Chore: bump openai to 1.99.6 and telegram-agent-mcp-client to 0.8.0
- Chore: optimize Docker build
- Chore: bump uv.lock revision from 2 to 3
- Chore: update orjson to 3.11.2 and langchain dependencies
- Chore: update base image from bookworm to trixie in Dockerfile
- Chore: add type ignore comment to checkpointer function return type
- Chore: update deps
- Chore: update deps
- Chore: bump rqbit-mcp dependency from 0.8.2 to 0.9.0 and update version to 0.10.0
- Chore: update dependencies
- Chore: update dependencies including openai, langsmith, and posthog packages
- Chore: update deps
- Chore: update deps
- Chore: update deps
- Chore: add whitelist env var and restricted agent access for public tests
- Chore: add NEXT_PUBLIC_API_URL to environment variables example
- Chore: migrate next.config from mjs to ts and update output mode to export
- Chore: remove static export config from Next.js settings
- Chore: add .env.\* pattern to gitignore file
- Chore: update Gemini model names and disable thinking budget in GraphRAG
- Chore: switch default Gemini model to flash-preview in example config
- Chore: update deps
- Chore: update Gemini model names to use latest versions
- Chore: add GRPC_VERBOSITY env var and LangSmith config settings
- Chore: upgrade deps
- Chore: deps
- Chore: deps again
- Chore: deps
- Chore: deps
- Chore: update deps
- Chore: update
- Chore: update CHANGELOG.md with recent commit history
- Chore: update deps
- Chore: update deps
- Chore: update deps
- Chore: update deps
- Chore: update changelog
- Chore: disable Neo4j service and graph database integration
- Chore: update deps
- Chore: update changelog
- Chore: update deps
- Chore: update Fireworks model to kimi-k2p6-turbo and suppress LangChain deprecation warnings
- Chore: update deps
- Chore: update Transmission default trackers list
- Chore: update deps and Transmission default trackers list
- Chore: update Gemini default models to gemini-3.5-flash and gemini-3.1-flash-lite
- Chore: update Transmission default trackers list
- Chore: update tracker lists
- Chore: update GitHub Actions versions and switch to gemini-3.1-flash-lite-image model
- Chore: update deps
- Chore: update deps
- Chore: update changelog
- Chore: rename CI workflow file and improve lint job configuration

- Rename python-package-ci.yml to ci-cd.yml
- Add concurrency control to cancel in-progress runs on same ref
- Rename test job to lint for clarity
- Switch to --frozen flag for uv sync (stricter than --locked)
- Add --check flag to ruff format to verify formatting without modifying
- Remove redundant telegram_agent path arguments (check entire project)
- Bump version to 0.14.0
- Chore: update deps
- Chore: fix workflow references after CI/CD rename

- Update build job dependency from test to lint
- Update README badge URL from python-package-ci.yml to ci-cd.yml
- Chore: update default Gemini models to 3.6-flash and 3.5-flash-lite
- Chore: update Transmission trackers and pin to v4.0.6 until latest is fixed
- Chore: update deps
- Chore: update deps
- Chore: update CHANGELOG with recent commits, refresh Transmission trackers

- CHANGELOG.md: append summaries from commits 7c01b4c through d0bd308 (network-aware retry backoff, image inspection tools, TTS features, web search overhaul, HeroUI v3 migration, Python 3.14 bump, etc.)
- transmission.config.json: refresh default-trackers list (add zer0day.ch, tracker2.dler.org, tracker.0x7c0.com; remove dead/duplicate entries)
- Chore: update changelog
- Chore: update changelog
- Chore: update deps + changelog
- Chore: update default Gemini model from 3.6-flash to 3.7-flash
- Chore: update deps
- Chore: bump version to 2.1.0 and improve MCP transport config handling
- Chore: update changelog
- Chore: update changelog
