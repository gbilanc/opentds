# ui/workers/generator_worker.py
"""Worker asincrono per la generazione procedurale dello stage (Fase 1 e 2)."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, QRunnable

from core.generator import StageGenerator, GeneratorConfig, Phase2Config, GeneratorResult
from core.models import Stage


class GeneratorSignals(QObject):
    started = Signal()
    finished = Signal(object)  # GeneratorResult come object (Qt queued connection)
    error = Signal(str)


class GeneratorWorker(QRunnable):
    """Esegue la generazione completa (Fase 1 + 2) in un thread separato."""
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


class Phase2Worker(QRunnable):
    """Esegue la Fase 2 (posizionamento bersagli/ostacoli) in un thread separato.

    Prende uno Stage con perimetro già definito (da Fase 1) e vi aggiunge
    bersagli, ostacoli, no-shoot, shooting positions.
    """
    def __init__(self, stage: Stage, phase2: Phase2Config, poly: list):
        super().__init__()
        self.stage = stage
        self.phase2 = phase2
        self.poly = poly
        self.signals = GeneratorSignals()

    def run(self):
        try:
            self.signals.started.emit()
            result = StageGenerator.place_targets_and_obstacles(
                self.stage, self.phase2, self.poly,
            )
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
