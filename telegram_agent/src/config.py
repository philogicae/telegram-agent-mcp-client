from os import getenv, path
from typing import Any

from dotenv import load_dotenv
from pyjson5 import load  # pylint: disable=no-name-in-module

load_dotenv()


class ThinkTag:
    start = getenv("THINK_TAG_START")
    end = getenv("THINK_TAG_END")


def get_config() -> Any:
    config_file = path.join(
        path.dirname(path.dirname(path.dirname(__file__))), "mcp_config.json"
    )
    if not path.exists(config_file):
        print("mcp_config.json file not found: creating a empty one")
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("{}")
    return load(open(config_file, "r", encoding="utf-8"))
