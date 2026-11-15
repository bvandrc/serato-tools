"""Deprecated, to be removed in version 6: the old name of `serato_tools.utils.cli`, which it imports from."""

import warnings

from serato_tools.utils.cli import get_hex_editor, get_text_editor, parse_cli_keys_and_values, ui_ask

__all__ = ["get_hex_editor", "get_text_editor", "parse_cli_keys_and_values", "ui_ask"]

warnings.warn(
    "serato_tools.utils.ui is deprecated and will be removed in version 6, use serato_tools.utils.cli instead",
    DeprecationWarning,
    stacklevel=2,
)
