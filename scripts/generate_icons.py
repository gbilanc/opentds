#!/usr/bin/env python3
"""Genera icone SVG per l'app OpenTDS."""
import os

ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "icons")

ICONS = {
    # ── Azioni ──────────────────────────────────────────────────────
    "delete": (
        '<path d="M5 8h14l-1.5 13a2 2 0 0 1-2 2H8.5a2 2 0 0 1-2-2L5 8z"/>'
        '<path d="M3 5h18M10 5V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M9 12v6M15 12v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "undo": (
        '<path d="M3 10h4l-3-3 3-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M7 17a5 5 0 1 0 0-10H3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "redo": (
        '<path d="M21 10h-4l3-3-3-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M17 17a5 5 0 0 0 0-10h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "save": (
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M17 21v-8H7v8M7 3v5h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "save_as": (
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M17 21v-8H7v8M7 3v5h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M17 3v5h-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="9" cy="16" r="2" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "open": (
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "edit": (
        '<path d="M17 2l5 5-14 14H3v-5L17 2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>'
        '<path d="M15 4l5 5" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "duplicate": (
        '<rect x="9" y="9" width="13" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "check": (
        '<path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "warning": (
        '<path d="M12 2L2 20h20L12 2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M12 9v4M12 17v0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="12" cy="17" r="1" fill="currentColor"/>'
    ),
    "color": (
        '<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<circle cx="12" cy="12" r="4" fill="currentColor"/>'
    ),
    "close": (
        '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="8" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M17 17l4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "library": (
        '<path d="M4 6h16M4 12h16M4 18h12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M4 6l2-3h12l2 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "theme": (
        '<circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 16v-4M12 8v0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="12" cy="8" r="1" fill="currentColor"/>'
    ),
    "generate": (
        '<circle cx="12" cy="18" r="4" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 2v4M12 10v2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M8 6l2 2M14 8l2-2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "plus": (
        '<path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "minus": (
        '<path d="M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),

    # ── Tipi bersaglio ──────────────────────────────────────────────
    "target_paper": (
        '<rect x="7" y="3" width="10" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<circle cx="12" cy="10" r="3" fill="none" stroke="currentColor" stroke-width="1.5"/>'
        '<path d="M12 7v6M9 10h6" fill="none" stroke="currentColor" stroke-width="1" opacity="0.5"/>'
    ),
    "target_steel": (
        '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M9 9l6 6M15 9l-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "target_popper": (
        '<rect x="9" y="4" width="6" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M6 18h12v2H6z" fill="currentColor"/>'
    ),
    "target_plate": (
        '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.5"/>'
    ),
    "target_swinger": (
        '<rect x="7" y="6" width="10" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 20v2M8 22h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M3 8a12 12 0 0 0 9 4 12 12 0 0 0 9-4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="2 2"/>'
    ),
    "target_drop": (
        '<rect x="7" y="6" width="10" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 6V2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M12 2l-3 3M12 2l3 3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    ),
    "target_mover": (
        '<rect x="7" y="8" width="10" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M5 14H2M22 14h-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M2 14l2-2M2 14l2 2M22 14l-2-2M22 14l-2 2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    ),
    "target_double": (
        '<rect x="5" y="4" width="7" height="16" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<rect x="12" y="4" width="7" height="16" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "target_double_hostage": (
        '<rect x="5" y="4" width="7" height="16" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<rect x="12" y="4" width="7" height="16" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M9.5 4v16" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="2 2"/>'
    ),
    "target_bobber": (
        '<circle cx="12" cy="14" r="7" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 7V4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "no_shoot": (
        '<rect x="7" y="3" width="10" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M9 7l6 10M15 7l-6 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),

    # ── Elementi stage ──────────────────────────────────────────────
    "wall": (
        '<rect x="3" y="6" width="18" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M3 10h18M3 14h18" fill="none" stroke="currentColor" stroke-width="1" opacity="0.5"/>'
    ),
    "barrier": (
        '<rect x="3" y="8" width="18" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="4 2"/>'
    ),
    "door": (
        '<rect x="3" y="4" width="18" height="16" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 4v16" fill="none" stroke="currentColor" stroke-width="1.5"/>'
        '<circle cx="14" cy="12" r="1.5" fill="currentColor"/>'
    ),
    "hard_cover": (
        '<rect x="3" y="6" width="18" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M6 9l12 12M18 9l-12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.6"/>'
    ),
    "soft_cover": (
        '<rect x="3" y="6" width="18" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="4 2"/>'
        '<path d="M6 9l12 12M18 9l-12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.3" stroke-dasharray="3 2"/>'
    ),
    "fault_line": (
        '<line x1="3" y1="12" x2="21" y2="12" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="6 4"/>'
    ),
    "shooting_position": (
        '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<circle cx="12" cy="12" r="3" fill="currentColor"/>'
    ),

    # ── File / Export ───────────────────────────────────────────────
    "file": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M14 2v6h6" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "export": (
        '<path d="M12 16V4M8 8l4-4 4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M4 18v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "import_icon": (
        '<path d="M12 4v12M8 12l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M4 18v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "pin": (
        '<path d="M12 2C8 2 5 5 5 9c0 4 7 13 7 13s7-9 7-13c0-4-3-7-7-7z" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<circle cx="12" cy="9" r="2" fill="currentColor"/>'
    ),
    "path_reset": (
        '<path d="M3 12a9 9 0 1 1 3 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M3 3v5h5M21 21v-5h-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "position_add": (
        '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<path d="M12 8v8M8 12h8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
    "path_waypoint": (
        '<circle cx="5" cy="12" r="2" fill="currentColor"/>'
        '<circle cx="12" cy="12" r="2" fill="currentColor"/>'
        '<circle cx="19" cy="12" r="2" fill="currentColor"/>'
        '<path d="M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="4 2"/>'
    ),
    "chart": (
        '<rect x="3" y="13" width="4" height="8" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>'
        '<rect x="10" y="9" width="4" height="12" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>'
        '<rect x="17" y="5" width="4" height="16" fill="none" stroke="currentColor" stroke-width="2" rx="1"/>'
    ),
}

SVG_TEMPLATE = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  {paths}
</svg>'''


def generate():
    os.makedirs(ICONS_DIR, exist_ok=True)
    for name, paths_str in sorted(ICONS.items()):
        content = SVG_TEMPLATE.format(paths=paths_str)
        filepath = os.path.join(ICONS_DIR, f"{name}.svg")
        with open(filepath, "w") as f:
            f.write(content)
        print(f"  ✅ {name}.svg")


if __name__ == "__main__":
    print("Generazione icone SVG...")
    generate()
    print(f"\nFatto! {len(ICONS)} icone in {ICONS_DIR}")
