# Changelog

All notable changes to this project will be documented in this file.

## [unreleased]

### 🚀 Features

- Implement langchain agent with MCP client integration
- Create empty config file if not found and add test environment variables
- Add mcp_config.json to Docker image and update dependencies
- Add Ollama LLM support and improve agent output formatting
- Add configurable think tags for agent message parsing
- Add support for Gemini and Cerebras LLMs
- Add Groq LLM support and refactor config/llm modules
- Add support for list-type message content for gemini thinking and set temperature=0.5 for all LLM providers
- Enhance agent output with rich panels and update dependencies
- Add timing metrics for agent responses and display in usage panel
- Add web-search and torrent-search tools to MCP config example
- Add detailed usage tracking and improve console output formatting
- Add rqbit to docker-compose
- Custom tool loader and format
- Increase ollama context window to 8192 tokens and update dependencies
- Enhance agent prompts with meta-procedures
- Add deep-search plugin config and update Brave search description with news focus
- Add pytelegrambotapi dependency and initial bot module structure
- Rework agent
- Add telegram bot module
- Update main
- Rework agent for telegram + add checkpoint/store
- Major rework on telegram bot
- Rework agent 2
- Rework bot 2
- Fix markdown bugs, add auto issue report, optimizations, add new_releases meta-procedure to prompt v2
- Restructure docker setup with env configs and deployment scripts
- Add support for Gemini thinking response format
- Rework/improve docker setup
- Add Emby media server integration with library refresh after downloads
- Add CLI tool listing
- Add progress bar utility function for displaying completion status
- Improve tool execution feedback with detailed status and error reporting
- Integrate rqbit client for torrent download management
- Enhance torrent status display with live indicators and improved message formatting
- Improve torrent UI with cleaner progress bars and optimized message updates
- Add configurable delay parameter to TorrentManager polling loop
- Set higher timeout and disable logging for sse/http connections
- Auto-forget torrent after completion
- Improve deployment configuration
- Enhance torrent status display with peer stats, download speed, and time remaining info+ recreate newer pinned message
- Add document handling support for telegram bot [1]
- Add gpt-5
- Add paginated message support with navigation controls
- Mount config directory to docker container for external configuration
- Add message trimming hook to prevent token overflow in agent conversations
- Clarify routines vs tools distinction and improve media search workflow
- Add error handling and graceful exit for tool fetching failures
- Add telegram markdown v2 formatting support
- Sequential-thinking via sse
- Implement agent swarm 1
- Implement agent swarm 2
- Implement agent swarm 3
- Implement agent swarm 4
- Implement agent swarm 5
- Implement agent swarm 6
- Implement agent swarm 7

### 🐛 Bug Fixes

- Add null check for usage_metadata and update dependencies
- Docker compose setup
- Better mcp config example
- Bug hunting
- Handle empty text when step is a completion emoji
- Various bugs and ajustments
- Update file paths in deploy script and gitignore to match new docker-envs directory
- Delete disabled flag from server settings before processing
- Update new_releases meta-procedure in prompts
- Disable forget_torrent and enable delete_torrent in config
- Prevent duplicate error notifications when error occurs in dev chat and update torrent priority rules
- Handle empty config case in get_tools by returning empty list
- Remove unnecessary config file copies from Dockerfile
- Remove unnecessary quotes around command in compose.yaml
- Many bug / edge case fixes
- Disable_web_page_preview is deprecated
- Remove openai base url parameter from ChatOpenAI initialization
- Gracefully handle keyboard interrupt in CLI
- Adjust message length calculation
- Increase HTTP client timeout from 10s to 30s and update markdown-it-py to 4.0.0
- Add type ignore comment for timeout assignment in client connections
- Reduce max token limit to 5000 and remove allow_partial flag in message trimming
- Update data volume path and use in-memory checkpointer for dev mode
- 10000 tokens context
- Gemini bug + fallback gemini-openai provider
- Pagination not required on extended text
- Improve tool result edit detection
- Handle case when agent message has no name attribute

### 💼 Other

- Adjust ollama context and prediction limits for CPU-only mode
- Add LangSmith environment variables and enable n8n runners

### 🚜 Refactor

- Rename mcp_config.json.example.json to mcp_config.example.json
- Simplify Docker build and improve container configuration
- Update agent prompt to be more precise and direct in tool usage
- Reorder docker-compose service properties and add restart policy for rqbit
- Update docker compose files
- Move agent module into core package
- Improve logging and datetime handling across bot and agent components
- Various improvements
- Improve tool execution feedback with progress bar and pinned downloads
- Move rate limiting and abstract methods to Bot base class
- Update telegram file handler to process document metadata from Message object
- Split deploy scripts and update network configuration for IPv6 support
- Enable pre-model hook and checkpointing in Agent initialization
- Switch container networking from bridge to host mode
- Remove unused text escaping functions from utils.py and update dependencies

### 📚 Documentation

- Add CHANGELOG.md to track project changes and features
- Update CHANGELOG with timing metrics, Docker improvements and dependencies
- Update changelog with telegram bot integration and major agent rework features
- Update changelog with Gemini support, Docker improvements and bug fixes
- Update changelog with new features, bug fixes, and dependency updates
- Update changelog with agent swarm features and performance improvements

### ⚡ Performance

- Optimize flag check by limiting text sample to first 50 chars

### ⚙️ Miscellaneous Tasks

- Add --fix flag to ruff check command in dev script
- Add langchain dependency with version 0.3.25
- Update docker compose with metatool services
- Update dependencies
- Update dependencies and add torrent-client config example
- Upgrade rqbit to 9.0.0-beta.1 and update langgraph/langsmith dependencies
- Cleanup
- Upgrade groq to 0.29.0 and grpcio to 1.73.1
- Update rqbit image to version 9.0.0-beta.1
- Update dependencies and modify torrent list comment in agent.py
- Update dependencies
- Add aiohttp
- Update deps
- Upgrade langgraph to 0.5.1 and remove version specifiers from dependencies
- Optimize GitHub Actions workflow with uv cache and tagged releases
- Update dependencies including mypy 1.17.0 and jsonschema 4.24.1
- Update dependencies including authlib, fastmcp, mcp and ruff
- Update rqbit-mcp dependency from 0.6.1 to 0.7.0
- Update deps
- Bump anyio to 4.10.0 and rqbit-mcp to 0.7.1
- Update deps
- Update dependencies and switch to using published Docker images
- Update deps
- Bump langchain-openai to 0.3.29 and openai to 1.99.4
- Update charset-normalizer dependency from 3.4.2 to 3.4.3
- Bump openai to 1.99.6 and telegram-agent-mcp-client to 0.8.0
- Optimize Docker build
- Bump uv.lock revision from 2 to 3
- Update orjson to 3.11.2 and langchain dependencies
- Update base image from bookworm to trixie in Dockerfile
- Add type ignore comment to checkpointer function return type
- Update deps

<!-- generated by git-cliff -->
