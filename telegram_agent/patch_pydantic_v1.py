"""Patch pydantic."""

from warnings import filterwarnings

# Suppress Pydantic V1 compatibility warning on Python 3.14+
filterwarnings("ignore", category=UserWarning)

_PYDANTIC_V1_ANCHOR = None
