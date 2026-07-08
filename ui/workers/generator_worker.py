# ui/workers/generator_worker.py
"""Worker asincrono per la generazione procedurale dello stage."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.generator import StageGenerator, GeneratorConfig, GeneratorResult


class GeneratorSignals(QObject):
    started = Signal()
    finished = Signal(object)  # GeneratorResult come object (Qt queued connection)
    error = Signal(str)


class GeneratorWorker(QRunnable):
    """Esegue la generazione in un thread separato."""
    def __init__(self, config: GeneratorConfig):
        super().__init__()
        self.config = config
        self.signals = GeneratorSignals()

    def run(self):
        try:
            self.signals.started.emit()
            generator = StageGenerator(self.config)
            result = generator.generate()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
