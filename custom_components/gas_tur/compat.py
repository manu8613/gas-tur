"""Compatibility helpers across Home Assistant versions."""

from __future__ import annotations

try:  # Home Assistant 2026.12+ replaced voluptuous with probatio.
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol

__all__ = ["vol"]
