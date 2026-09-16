"""Pytest wrapper around the historical manual prune regression runner."""

from telegram_agent.tests.test_prune import main as prune_main


def test_prune_regression_runner():
    """The manual runner keeps passing under pytest as well."""
    prune_main()
