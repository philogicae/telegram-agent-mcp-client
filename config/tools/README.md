# Tools Configuration

This directory contains the tool definitions for the Telegram Agent MCP Client. The system supports two primary ways to define tools: **Native Python Tools** and **MCP (Model Context Protocol) Servers**.

## 📂 Structure

Tools are organized by category folders (e.g., `acp`, `home`, `media`, `utils`, `web`). The system recursively scans `config/tools/` for configuration files.

```text
config/tools/
├── acp/
│   └── opencode.py              # Native Python tool (OpenCode dev sessions)
├── home/
│   ├── gree_ac.py               # Native Python tool (GREE AC control)
│   └── kaneo.json               # MCP Server config
├── media/
│   ├── torrent_client.json      # MCP Server config
│   └── ...
├── web/
│   └── ...
├── _template.py                 # Scaffold for native tools (never loaded)
└── README.md
```

Files starting with `_` (underscore) are skipped by the loader - use the prefix to park a configuration you don't want to load.

## 🐍 Native Python Tools (`.py`)

Native tools are Python files that define functions or classes decorated with `@tool` (from LangChain). These run directly within the agent's process.

### How to Create

1. Copy `config/tools/_template.py` to a new `.py` file in any subdirectory (without the leading underscore - underscore-prefixed files are not loaded).
2. Import `tool` from `langchain.tools`.
3. Decorate your function with `@tool`.
4. Add a docstring (this becomes the tool description for the LLM).
5. Type-hint inputs and outputs.

**Example (`config/tools/utils/my_tool.py`):**

```python
from langchain.tools import tool


@tool
def calculate_complexity(code: str) -> str:
    """
    Calculates the cyclomatic complexity of the given Python code.
    Use this when you need to assess code maintainability.
    """
    # Implementation...
    return "Complexity Score: 5"
```

The system automatically discovers and loads any `BaseTool` instances found in these files.

## 🔌 MCP Servers (`.json`)

MCP (Model Context Protocol) allows agents to connect to external tools running as separate processes or services. These are configured via JSON files.

### Configuration Format

Create a `.json` file in any subdirectory. Files are JSON5, so `//` comments are allowed (the loader also maintains a `/* all found tools */` comment listing what the server currently exposes). The configuration supports two transport modes: **Command** (stdio) and **URL** (SSE/HTTP).

The optional `description` field is metadata for humans only - it is not passed to the MCP server.

#### 1. Command-Based (Stdio)

Runs a local command (e.g., `npx`, `python`, `docker`) to start the MCP server.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/workspace"],
  "env": {
    "NODE_ENV": "production"
  }
}
```

_Note: You can also combine command and args into a single `"command"` string. Leading `VAR=value` prefixes in the command are hoisted into `env`._

#### 2. URL-Based (SSE/HTTP)

Connects to a running MCP server. The transport is inferred from the URL: `/sse` → SSE, otherwise streamable HTTP.

```json
{
  "url": "http://localhost:8000/sse",
  "headers": {
    "Authorization": "Bearer {ENV:MY_API_KEY}"
  }
}
```

### Advanced Features

#### Environment Variable Substitution

Use `{ENV:VAR_NAME}` to inject environment variables securely, and `{ENV:VAR_NAME:-default}` to fall back to a default when the variable is unset (or empty):

```json
"env": {
  "API_KEY": "{ENV:OPENAI_API_KEY}",
  "SEARXNG_URL": "{ENV:SEARXNG_BASE_URL}:{ENV:SEARXNG_PORT:-8080}"
}
```

If a referenced variable has no value and no default, the whole server is skipped (with a log line).

#### Tool Customization (`edit`)

You can rename tools or rewrite their descriptions without modifying the underlying server code. This is useful for tailoring generic tools to your specific agent's needs.

```json
"edit": {
  "original_tool_name": {
    "name": "better_tool_name",
    "description": "A more specific description for my agent..."
  }
}
```

#### Enabling Tools (Whitelist)

When a server provides many tools but you only want to use a few, you can use the `enable` field to specify a whitelist. Only tools listed in `enable` will be loaded.

```json
// Only enable specific tools (whitelist approach)
"enable": ["safe_tool", "useful_tool"]
```

#### Disabling Tools (Blacklist)

You can disable specific tools from a server, or disable the entire server.

```json
// Disable specific tools (blacklist approach)
"disable": ["dangerous_tool", "legacy_tool"]

// OR disable the whole server
"disable": true
```

**Note**: `enable` and `disable` can be combined - a tool is only loaded when it is in `enable` (if an `enable` list is present) and not in `disable`.

#### Unsupported Options

Options not recognized by the selected transport (or the client) are ignored with a log line instead of failing the whole server.

## 🚀 Adding a New Tool

### Option A: Python Tool

Use this for logic that requires direct access to the Python environment, or for lightweight utilities.

1. Copy `config/tools/_template.py` (if available) or create a new `.py` file.
2. Implement your function with `@tool`.

### Option B: MCP Server

Use this for external integrations (GitHub, Slack, Database) or to leverage the ecosystem of existing MCP servers.

1. Create a `.json` file.
2. Define the `command` or `url`.
3. (Optional) Use `edit` to refine the tool names/descriptions.

## 🔍 Troubleshooting

- **Ignored Files**: files starting with `_` (underscore) are skipped by the loader, including `_template.py`.
- **Missing Env Vars**: if a required `{ENV:VAR}` has no value and no `:-default`, the server config is skipped.
- **Logs**: the system logs loaded tools and any errors during startup. Check the console output.
