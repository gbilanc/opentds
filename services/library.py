"""
Stage Library service — manages saved stages, predefined classifiers, and catalog.

Storage:
  ~/.opentds/library/index.json  — metadata index
  ~/.opentds/library/stages/     — stage JSON files (.opentds)
  resources/stages/              — predefined/built-in stages

Thread safety: all file operations are synchronous (lightweight).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models import Stage
from services.serializer import load_stage, save_stage

# ── Paths ──────────────────────────────────────────────────────────────────

_HOME_DIR = Path.home() / ".opentds"
_LIBRARY_DIR = _HOME_DIR / "library"
_STAGES_DIR = _LIBRARY_DIR / "stages"
_INDEX_PATH = _LIBRARY_DIR / "index.json"
_PREDEFINED_DIR = Path(__file__).resolve().parent.parent / "resources" / "stages"


# ── Data model ─────────────────────────────────────────────────────────────


@dataclass
class LibraryEntry:
    """Metadata for a stage in the library."""

    id: str = ""  # unique slug (e.g. "classifier-01-02")
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    filename: str = ""  # relative to _STAGES_DIR or _PREDEFINED_DIR
    is_predefined: bool = False
    date_added: str = ""  # ISO 8601
    course_type: str = ""
    width: float = 20.0
    depth: float = 15.0
    target_count: int = 0
    round_count: int = 0
    source_url: str = ""  # for imported/online stages


# ── StageLibrary ───────────────────────────────────────────────────────────


class StageLibrary:
    """Manages the stage catalog: index, predefined, search, import/export."""

    def __init__(self):
        self._entries: list[LibraryEntry] = []
        self._dirty = False
        self._ensure_dirs()
        self._load_index()
        self._load_predefined()

    # ── Public API ──────────────────────────────────────────────────────

    def list_all(self) -> list[LibraryEntry]:
        """Return all library entries (predefined + user-saved)."""
        return list(self._entries)

    def search(self, query: str = "", tags: list[str] | None = None) -> list[LibraryEntry]:
        """Search entries by name, description, or tags."""
        query = query.strip().lower()
        results = self._entries
        if query:
            results = [
                e
                for e in results
                if query in e.name.lower()
                or query in e.description.lower()
                or any(query in t.lower() for t in e.tags)
            ]
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        return results

    def get(self, entry_id: str) -> Optional[LibraryEntry]:
        """Get entry by ID."""
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    def load_stage(self, entry: LibraryEntry) -> Optional[Stage]:
        """Load a stage from the library by its entry."""
        if entry.is_predefined:
            path = _PREDEFINED_DIR / entry.filename
        else:
            path = _STAGES_DIR / entry.filename
        if not path.exists():
            return None
        try:
            return load_stage(path)
        except Exception:
            return None

    def save_stage(
        self,
        stage: Stage,
        name: str = "",
        description: str = "",
        tags: list[str] | None = None,
    ) -> LibraryEntry:
        """Save a stage to the user library."""
        self._ensure_dirs()
        slug = _make_slug(name or stage.name)
        filename = f"{slug}.opentds"
        path = _STAGES_DIR / filename

        save_stage(stage, path)

        entry = LibraryEntry(
            id=slug,
            name=name or stage.name,
            description=description,
            tags=tags or [],
            filename=filename,
            is_predefined=False,
            date_added=datetime.now().isoformat(),
            course_type=stage.course_type.value if stage.course_type else "",
            width=stage.width,
            depth=stage.depth,
            target_count=len(stage.items),
            round_count=_count_rounds(stage),
        )

        # Replace existing or append
        existing = self.get(slug)
        if existing:
            self._entries.remove(existing)
        self._entries.append(entry)
        self._save_index()
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a user-saved stage from the library."""
        entry = self.get(entry_id)
        if not entry or entry.is_predefined:
            return False
        path = _STAGES_DIR / entry.filename
        if path.exists():
            path.unlink()
        self._entries.remove(entry)
        self._save_index()
        return True

    def import_from_file(self, file_path: Path) -> Optional[LibraryEntry]:
        """Import a .opentds or .json file into the library."""
        try:
            stage = load_stage(file_path)
            name = file_path.stem.replace("_", " ").replace("-", " ").title()
            return self.save_stage(stage, name=name, tags=["imported"])
        except Exception:
            return None

    def export_to_file(self, entry_id: str, export_path: Path) -> bool:
        """Export a library stage to the given path."""
        entry = self.get(entry_id)
        if not entry:
            return False
        stage = self.load_stage(entry)
        if not stage:
            return False
        try:
            save_stage(stage, export_path)
            return True
        except Exception:
            return False

    # ── Predefined stage management ────────────────────────────────────

    def reload_predefined(self):
        """Reload predefined stages from resources/stages/."""
        self._entries = [e for e in self._entries if not e.is_predefined]
        self._load_predefined()

    # ── Internal ────────────────────────────────────────────────────────

    def _ensure_dirs(self):
        _LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        _STAGES_DIR.mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        """Load the user library index."""
        if not _INDEX_PATH.exists():
            self._entries = []
            return
        try:
            data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
            self._entries = [LibraryEntry(**item) for item in data]
        except (json.JSONDecodeError, KeyError):
            self._entries = []

    def _save_index(self):
        """Save the user library index."""
        data = [asdict(e) for e in self._entries if not e.is_predefined]
        _INDEX_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_predefined(self):
        """Scan resources/stages/ for predefined .opentds files."""
        if not _PREDEFINED_DIR.exists():
            return
        for fpath in sorted(_PREDEFINED_DIR.glob("*.opentds")):
            # Skip if already loaded
            slug = fpath.stem
            if self.get(slug):
                continue
            try:
                stage = load_stage(fpath)
                entry = LibraryEntry(
                    id=slug,
                    name=stage.name or fpath.stem.replace("_", " ").title(),
                    description=stage.properties.get("description", ""),
                    tags=["predefinito"],
                    filename=fpath.name,
                    is_predefined=True,
                    date_added=datetime.fromtimestamp(fpath.stat().st_mtime).isoformat(),
                    course_type=stage.course_type.value if stage.course_type else "",
                    width=stage.width,
                    depth=stage.depth,
                    target_count=len([it for it in stage.items if _is_scoring_item(it)]),
                    round_count=_count_rounds(stage),
                )
                self._entries.append(entry)
            except Exception:
                pass  # Skip invalid files


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_slug(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    slug = name.lower().strip()
    for ch in "àáâäæãåā":
        slug = slug.replace(ch, "a")
    for ch in "èéêëēėę":
        slug = slug.replace(ch, "e")
    for ch in "ìíîïī":
        slug = slug.replace(ch, "i")
    for ch in "òóôöō":
        slug = slug.replace(ch, "o")
    for ch in "ùúûüū":
        slug = slug.replace(ch, "u")
    slug = "".join(c for c in slug if c.isalnum() or c in " _-")
    slug = slug.replace(" ", "-")
    # Collapse multiple hyphens
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:64] or "stage"


def _count_rounds(stage: Stage) -> int:
    """Count required rounds for a stage."""
    total = 0
    from core.models import ItemType

    paper_like = (
        ItemType.PAPER_TARGET,
        ItemType.MINI_TARGET,
        ItemType.MICRO_TARGET,
        ItemType.SWINGER,
        ItemType.DROP_TURNER,
        ItemType.MOVER,
    )
    steel_like = (ItemType.STEEL_TARGET, ItemType.POPPER, ItemType.METAL_PLATE)
    for it in stage.items:
        if it.item_type in paper_like:
            total += 2
        elif it.item_type in steel_like:
            total += 1
    return total


def _is_scoring_item(it) -> bool:
    from core.models import ItemType

    scoring = (
        ItemType.PAPER_TARGET,
        ItemType.STEEL_TARGET,
        ItemType.POPPER,
        ItemType.METAL_PLATE,
        ItemType.MINI_TARGET,
        ItemType.MICRO_TARGET,
        ItemType.SWINGER,
        ItemType.DROP_TURNER,
        ItemType.MOVER,
    )
    return it.item_type in scoring
