"""Process-wide warning filters and pydantic v1."""

from warnings import filterwarnings

# Suppress Pydantic V1 compatibility warning on Python 3.14+
# suppress by base class instead of private import
filterwarnings("ignore", category=UserWarning)
filterwarnings("ignore", category=PendingDeprecationWarning)

# `langchain_core` re-arms `default` filters for its own warning categories on
# import (`LangChainBetaWarning` subclasses DeprecationWarning), inserted ahead
# of ours; import it and re-apply so they stay silenced - e.g. the
# `langchain.mcp` beta warning raised by core/tools.py
import langchain_core

langchain_core  # noqa: B018
filterwarnings("ignore", category=PendingDeprecationWarning)
filterwarnings("ignore", category=DeprecationWarning)

_PATCH_ANCHOR = None
