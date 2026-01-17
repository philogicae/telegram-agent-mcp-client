# Tools Configuration

This directory contains the tool definitions for the Fractal Agents system. The system supports two primary ways to define tools: **Native Python Tools** and **MCP (Model Context Protocol) Servers**.

## 📂 Structure

Tools are organized by category folders (e.g., `local`, `web`, `media`, `utils`). The system recursively scans `config/tools/` for configuration files.

```text
config/tools/
├── local/
│   ├── filesystem.json   # MCP Server config
│   └── ...
├── web/
│   ├── web_search.json   # MCP Server config
│   └── ...
├── utils/
│   ├── sequential_thinking.py  # Native Python tool
│   └── ...
└── README.md
```

## 🐍 Native Python Tools (`.py`)

Native tools are Python files that define functions or classes decorated with `@tool` (from LangChain). These run directly within the agent's process.

### How to Create

1. Create a `.py` file in any subdirectory of `config/tools/`.
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

Create a `.json` file in any subdirectory. The configuration supports two transport modes: **Command** (stdio) and **URL** (SSE/HTTP).

#### 1. Command-Based (Stdio)

Runs a local command (e.g., `npx`, `python`, `docker`) to start the MCP server.

```json
{
  "command": "npx",
  "args": [
    "-y",
    "@modelcontextprotocol/server-filesystem",
    "/home/user/workspace"
  ],
  "env": {
    "NODE_ENV": "production"
  }
}
```

_Note: You can also combine command and args into a single `"command"` string._

#### 2. URL-Based (SSE/HTTP)

Connects to a running MCP server over HTTP/SSE.

```json
{
  "url": "http://localhost:8000/sse",
  "env": {
    "API_KEY": "{ENV:MY_API_KEY}"
  }
}
```

### Advanced Features

#### Environment Variable Substitution

Use `{ENV:VAR_NAME}` to inject environment variables securely.

```json
"env": {
  "API_KEY": "{ENV:OPENAI_API_KEY}"
}
```

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

**Note**: You cannot use both `enable` and `disable` for the same server. If both are provided, `disable` will take precedence for tools that appear in either list.

## 🚀 Adding a New Tool

### Option A: Python Tool

Use this for logic that requires direct access to the agent's memory or Python environment, or for lightweight utilities.

1. Copy `config/tools/_template.py` (if available) or create a new `.py` file.
2. Implement your function with `@tool`.

### Option B: MCP Server

Use this for external integrations (GitHub, Slack, Database) or to leverage the ecosystem of existing MCP servers.

1. Create a `.json` file.
2. Define the `command` or `url`.
3. (Optional) Use `edit` to refine the tool names/descriptions.

## 🔍 Troubleshooting

- **Ignored Files**: Files starting with `_` (underscore) are ignored by the loader (except `_template.py`).
- **Missing Env Vars**: If a required `{ENV:VAR}` is missing, the server config will be skipped.
- **Logs**: The system logs loaded tools and any errors during startup. Check the console output.
