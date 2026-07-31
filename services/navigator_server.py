"""
Server HTTP leggero per servire il navigatore 3D (navigator/dist/).

Avviato su richiesta, espone i file statici del navigator e lo stage
corrente esportato come JSON in modo che il visualizzatore Three.js
possa caricarlo via fetch.
"""

from __future__ import annotations

import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_NAVIGATOR_DIST = Path(__file__).resolve().parent.parent / "navigator" / "dist"


def _find_free_port(start: int = 8080, max_attempts: int = 20) -> int:
    """Trova la prima porta libera a partire da `start`."""
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"Nessuna porta libera trovata tra {start} e {start + max_attempts}"
    )


class NavigatorServer:
    """Server HTTP in thread separato per servire il navigator 3D."""

    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        if not self.is_running:
            raise RuntimeError("Server non avviato")
        return self._port

    @property
    def url(self) -> str:
        """URL alla root del navigator."""
        return f"http://localhost:{self.port}"

    def stage_url(self, stage_file: str = "current_stage.json") -> str:
        """URL per navigare uno stage specifico."""
        return f"{self.url}/?stage={stage_file}"

    def start(self, port: int | None = None) -> None:
        """Avvia il server su una porta libera."""
        if self.is_running:
            return

        self._port = port or _find_free_port()

        # Handler che serve dalla directory dist/
        dist_dir = str(_NAVIGATOR_DIST)

        class _Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=dist_dir, **kwargs)

            def log_message(self, format, *args):
                pass  # Silenzia i log delle richieste

        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), _Handler)
        self._server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="navigator-http",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Arresta il server."""
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        self._port = 0


# ── Singleton ──────────────────────────────────────────────────────────

_navigator_instance: NavigatorServer | None = None


def get_navigator_server() -> NavigatorServer:
    """Restituisce l'istanza singleton del server."""
    global _navigator_instance
    if _navigator_instance is None:
        _navigator_instance = NavigatorServer()
    return _navigator_instance


def export_stage_for_navigator(stage_json: str) -> Path:
    """Scrive lo stage JSON nella directory dist/ per il navigator.

    Args:
        stage_json: Stringa JSON dello stage.

    Returns:
        Path del file creato.
    """
    _NAVIGATOR_DIST.mkdir(parents=True, exist_ok=True)
    target = _NAVIGATOR_DIST / "current_stage.json"
    target.write_text(stage_json, encoding="utf-8")
    return target
