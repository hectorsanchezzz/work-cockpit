"""Test sources: which ones are on. Persisted in data/sources.json, changed from the page through serve.py.

A source that is off makes no calls and its section is not rendered at all.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "data" / "sources.json"

# key: (label shown in the panel, default)
SOURCES = {
    "github_prs": ("GitHub pull requests", True),
    "github_prs_bs": ("Include extra GitHub accounts (github_bs_accounts)", False),
    "rize": ("Rize tracked time", False),
    "claude_sessions": ("Claude sessions", False),
}


def load():
    on = {k: d for k, (_, d) in SOURCES.items()}
    try:
        saved = json.loads(FILE.read_text())
        on.update({k: v for k, v in saved.items() if k in SOURCES and isinstance(v, bool)})
    except (OSError, ValueError):
        pass
    return on


def save(changes):
    on = load()
    on.update({k: v for k, v in changes.items() if k in SOURCES and isinstance(v, bool)})
    FILE.parent.mkdir(exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(on, indent=2))
    tmp.replace(FILE)
    return on
