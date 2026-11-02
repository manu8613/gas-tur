"""Shared data for Gas TUR tests."""

from __future__ import annotations

from pathlib import Path

PAGE = (Path(__file__).parent / "fixtures" / "tur_2.html").read_text(encoding="utf-8")
TUR2_URL = "https://www.comercializadoraregulada.es/regulada/gas/tur_2"
