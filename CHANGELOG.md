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
- Add .gitignore rules for config/tools/* while preserving examples/ subdirectory
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
- Create _template.py for easy native tool creation
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
- Add _update_tools_comment function to maintain tool lists in JSON files
- Extend ty type checking to include config/tools directory in dev.sh
- Remove disabled filesystem.json configuration file
- Improve error messages with
- Feat: fix Python tool loading to use server_path instead of filename for dictionary key
- Feat: upgrade GitHub Actions and Python to 3.13, replace web_search with searxng and fetch tools
- Feat: add BetaSeries planning integration for episode tracking and new releases
- Feat: enhance BetaSeries integration with episode download tracking and improved authentication
- Feat: upgrade searxng-mul-mcp and add Playwright driver auto-installation with stderr suppression

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

### 💼 Changes

- Init
- Config: adjust ollama context and prediction limits for CPU-only mode
- Config: add LangSmith environment variables and enable n8n runners
- Merge branch 'graph-rag'
- Init docs ui

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
- Chore: add .env.* pattern to gitignore file
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
