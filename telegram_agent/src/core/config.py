from enum import Enum
from json import dump
from os import getenv, path
from typing import Any

from dotenv import load_dotenv
from pyjson5 import load  # pylint: disable=no-name-in-module

load_dotenv()


class ThinkTag:
    start = getenv("THINK_TAG_START")
    end = getenv("THINK_TAG_END")


class Flag(Enum):
    _ERROR = " error"
    ERROR_ = "error "
    _FAILED = " failed"
    FAILED_ = "failed "
    ERREUR = "erreur"


def get_config() -> tuple[dict[str, Any], dict[str, Any]]:
    config_file = getenv("MCP_CONFIG_FILE", "mcp_config.json")
    if not path.exists(config_file):
        print("mcp_config.json file not found: creating a empty one")
        with open(config_file, "w", encoding="utf-8") as f:
            dump({"mcpServers": {}}, f, indent=2)

    config = load(open(config_file, "r", encoding="utf-8"))
    mcp_servers = config.get("mcpServers", {})
    langchain_config, edit_config = {}, {}
    for server in mcp_servers:
        settings = mcp_servers[server]

        # Ignore disabled servers
        if settings.get("disabled"):
            continue
        del settings["disabled"]

        # stdio
        if settings.get("command"):
            command = settings.get("command").split(" ")
            if len(command) > 1 and not settings.get("args"):
                settings["command"], settings["args"] = command[0], command[1:]
            settings["transport"] = "stdio"

        # sse or streamable_http
        elif settings.get("serverUrl"):
            settings["url"] = settings["serverUrl"]
            del settings["serverUrl"]
            if settings.get("url").endswith("/"):
                settings["url"] = settings["url"][:-1]
            if settings["url"].endswith("/sse"):
                settings["transport"] = "sse"
            elif settings["url"].endswith("/mcp"):
                settings["transport"] = "streamable_http"

        # To rename or disable a tool
        if settings.get("edit"):
            edit_config.update(settings.get("edit"))
            del settings["edit"]
        langchain_config[server] = settings

    return langchain_config, edit_config
