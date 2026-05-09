"""Patch pydantic."""

from warnings import filterwarnings

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

# Suppress Pydantic V1 compatibility warning on Python 3.14+
filterwarnings("ignore", category=UserWarning)
filterwarnings(
    "ignore",
    category=LangChainPendingDeprecationWarning,
)

_PYDANTIC_V1_ANCHOR = None
