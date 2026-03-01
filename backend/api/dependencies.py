"""Dependency injection for Navi API."""

from config import settings


def get_settings():
    """Return the application settings singleton."""
    return settings
