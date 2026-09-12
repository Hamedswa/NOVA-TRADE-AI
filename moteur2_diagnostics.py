"""
NOVA TRADE AI - ENGINE 2
Diagnostic Pipeline

Rôle
----
Observer le parcours complet d'une opportunité dans Engine 2.

IMPORTANT
---------
Ce module est 100 % NON DÉCISIONNEL.

Il :
    - enregistre les étapes du pipeline ;
    - compte les opportunités ;
    - conserve les raisons de rejet/attente ;
    - permet d'afficher un résumé lisible dans les logs.

Il NE DOIT JAMAIS :
    - valider un setup ;
    - invalider un setup ;
    - modifier une décision ;
    - modifier un score ;
    - modifier un Risk Plan ;
    - bloquer un signal.

Pipeline observé
----------------
DATA
    ↓
CARTOGRAPHIE
    ↓
ZONES
    ↓
CONFLUENCES
    ↓
SETUPS
    ↓
RISK
    ↓
CONFIRMATION
    ↓
VALIDATION
    ↓
DECISION
    ↓
ANTISPAM
    ↓
SIGNAL
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging


logger = logging.getLogger(__name__)


# ============================================================
# ÉTAPES DU PIPELINE
# ============================================================

PIPELINE_STAGES = (
    "DATA",
    "CARTOGRAPHIE",
    "ZONES",
    "CONFLUENCES",
    "SETUPS",
    "RISK",
    "CONFIRMATION",
    "VALIDATION",
    "DECISION",
    "ANTISPAM",
    "SIGNAL",
)


# ============================================================
# UTILITAIRES
# ============================================================

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_count(value: Any) -> int:
    """
    Essaie d'obtenir un nombre depuis plusieurs formats possibles.

    Accepte notamment :
        - int / float
        - list / tuple / set
        - dict avec count / total / length
        - None
    """

    if value is None:
        return 0

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return max(0, int(value))

    if isinstance(value, (list, tuple, set)):
        return len(value)

    if isinstance(value, dict):
        for key in (
            "count",
            "total",
            "length",
            "size",
            "number",
            "nb",
        ):
            if key in value:
                return _safe_int(value.get(key), 0)

    return 0


def _extract_reason(value: Any) -> Optional[str]:
    """
    Essaie d'extraire une raison lisible depuis différents formats.
    """

    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        return text or None

    if isinstance(value, dict):
        for key in (
            "reason",
            "rejection_reason",
            "reject_reason",
            "message",
            "error",
            "status_reason",
        ):
            candidate = value.get(key)
            if candidate:
                return str(candidate)

    return None


# ============================================================
# ÉTAT D'UNE ÉTAPE
# ============================================================

@dataclass
class DiagnosticStage:
    name: str

    reached: bool = False
    count: int = 0

    status: str = "NOT_REACHED"

    reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    timestamp: str = field(default_factory=_now_iso)

    def mark(
        self,
        *,
        reached: bool = True,
        count: Optional[int] = None,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:

        self.reached = reached

        if count is not None:
            self.count = max(0, _safe_int(count))

        if status is not None:
            self.status = str(status)

        if reason is not None:
            self.reason = str(reason)

        if details:
            self.details.update(details)

        self.timestamp = _now_iso()


# ============================================================
# DIAGNOSTIC D'UN ACTIF
# ============================================================

@dataclass
class SymbolDiagnostic:
    symbol: str

    started_at: str = field(default_factory=_now_iso)

    stages: Dict[str, DiagnosticStage] = field(
        default_factory=dict
    )

    final_status: str = "NOT_ANALYZED"

    final_reason: Optional[str] = None

    signals_sent: int = 0

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).upper().strip()

        for stage in PIPELINE_STAGES:
            self.stages[stage] = DiagnosticStage(name=stage)

    def stage(self, name: str) -> DiagnosticStage:
        normalized = str(name).upper().strip()

        if normalized not in self.stages:
            self.stages[normalized] = DiagnosticStage(
                name=normalized
            )

        return self.stages[normalized]

    def mark_stage(
        self,
        name: str,
        *,
        reached: bool = True,
        count: Optional[int] = None,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:

        self.stage(name).mark(
            reached=reached,
            count=count,
            status=status,
            reason=reason,
            details=details,
        )

    def fail(
        self,
        stage: str,
        reason: str,
        *,
        status: str = "REJECTED",
    ) -> None:

        self.mark_stage(
            stage,
            reached=True,
            status=status,
            reason=reason,
        )

        self.final_status = status
        self.final_reason = reason

    def complete(
        self,
        *,
        status: str,
        reason: Optional[str] = None,
        signals_sent: int = 0,
    ) -> None:

        self.final_status = str(status)
        self.final_reason = reason
        self.signals_sent = max(0, _safe_int(signals_sent))

    def summary(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_status": self.final_status,
            "final_reason": self.final_reason,
            "signals_sent": self.signals_sent,
            "stages": {
                name: {
                    "reached": stage.reached,
                    "count": stage.count,
                    "status": stage.status,
                    "reason": stage.reason,
                    "details": stage.details,
                }
                for name, stage in self.stages.items()
            },
            "metadata": self.metadata,
        }


# ============================================================
# DIAGNOSTIC PIPELINE PRINCIPAL
# ============================================================

class Moteur2Diagnostics:
    """
    Gestionnaire central des diagnostics Engine 2.

    Le module conserve les diagnostics du cycle courant
    et peut également conserver un historique limité.
    """

    def __init__(
        self,
        *,
        max_history: int = 100,
        logger_instance: Optional[logging.Logger] = None,
    ) -> None:

        self.max_history = max(1, int(max_history))

        self.logger = logger_instance or logger

        self.current_cycle: Optional[str] = None

        self.symbols: Dict[str, SymbolDiagnostic] = {}

        self.history: List[Dict[str, Any]] = []

    # ========================================================
    # CYCLE
    # ========================================================

    def start_cycle(
        self,
        *,
        cycle_id: Optional[str] = None,
        symbols: Optional[List[str]] = None,
    ) -> str:

        self.current_cycle = (
            cycle_id
            or datetime.now(timezone.utc).strftime(
                "%Y%m%d_%H%M%S_%f"
            )
        )

        self.symbols = {}

        for symbol in symbols or []:
            self.start_symbol(symbol)

        self.logger.info(
            "NOVA ENGINE 2 | DIAGNOSTICS | CYCLE %s",
            self.current_cycle,
        )

        return self.current_cycle

    def start_symbol(
        self,
        symbol: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SymbolDiagnostic:

        normalized = str(symbol).upper().strip()

        diagnostic = SymbolDiagnostic(
            symbol=normalized,
            metadata=dict(metadata or {}),
        )

        self.symbols[normalized] = diagnostic

        return diagnostic

    def get_symbol(
        self,
        symbol: str,
    ) -> SymbolDiagnostic:

        normalized = str(symbol).upper().strip()

        if normalized not in self.symbols:
            return self.start_symbol(normalized)

        return self.symbols[normalized]

    # ========================================================
    # ENREGISTREMENT D'ÉTAPE
    # ========================================================

    def record(
        self,
        symbol: str,
        stage: str,
        *,
        value: Any = None,
        count: Optional[int] = None,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> SymbolDiagnostic:

        diagnostic = self.get_symbol(symbol)

        if count is None:
            count = _extract_count(value)

        if reason is None:
            reason = _extract_reason(value)

        diagnostic.mark_stage(
            stage,
            reached=True,
            count=count,
            status=status or "OK",
            reason=reason,
            details=details,
        )

        return diagnostic

    # ========================================================
    # REJET
    # ========================================================

    def record_rejection(
        self,
        symbol: str,
        stage: str,
        reason: str,
        *,
        count: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:

        diagnostic = self.get_symbol(symbol)

        diagnostic.fail(
            stage,
            reason,
            status="REJECTED",
        )

        diagnostic.stage(stage).count = max(
            0,
            _safe_int(count),
        )

        if details:
            diagnostic.stage(stage).details.update(details)

    # ========================================================
    # ATTENTE
    # ========================================================

    def record_waiting(
        self,
        symbol: str,
        stage: str,
        reason: str,
        *,
        count: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:

        diagnostic = self.get_symbol(symbol)

        diagnostic.mark_stage(
            stage,
            reached=True,
            count=count,
            status="WAITING",
            reason=reason,
            details=details,
        )

        diagnostic.final_status = "WAITING"
        diagnostic.final_reason = reason

    # ========================================================
    # SUCCÈS / SIGNAL
    # ========================================================

    def record_signal(
        self,
        symbol: str,
        *,
        direction: Optional[str] = None,
        confidence: Optional[float] = None,
        quality: Optional[float] = None,
        rr: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:

        diagnostic = self.get_symbol(symbol)

        diagnostic.mark_stage(
            "SIGNAL",
            reached=True,
            count=1,
            status="SENT",
            details={
                "direction": direction,
                "confidence": _safe_float(confidence),
                "quality": _safe_float(quality),
                "rr": _safe_float(rr),
                **(details or {}),
            },
        )

        diagnostic.complete(
            status="SIGNAL_SENT",
            signals_sent=1,
        )

    # ========================================================
    # FIN D'ANALYSE
    # ========================================================

    def complete_symbol(
        self,
        symbol: str,
        *,
        status: str,
        reason: Optional[str] = None,
        signals_sent: int = 0,
    ) -> None:

        diagnostic = self.get_symbol(symbol)

        diagnostic.complete(
            status=status,
            reason=reason,
            signals_sent=signals_sent,
        )

    # ========================================================
    # RÉSUMÉ D'UN ACTIF
    # ========================================================

    def get_summary(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        return self.get_symbol(symbol).summary()

    # ========================================================
    # RÉSUMÉ GLOBAL
    # ========================================================

    def build_cycle_summary(self) -> Dict[str, Any]:

        symbols_summary = {
            symbol: diagnostic.summary()
            for symbol, diagnostic in self.symbols.items()
        }

        total_signals = sum(
            diagnostic.signals_sent
            for diagnostic in self.symbols.values()
        )

        total_setups = sum(
            diagnostic.stage("SETUPS").count
            for diagnostic in self.symbols.values()
        )

        total_risk = sum(
            diagnostic.stage("RISK").count
            for diagnostic in self.symbols.values()
        )

        total_validated = sum(
            diagnostic.stage("VALIDATION").count
            for diagnostic in self.symbols.values()
        )

        return {
            "cycle_id": self.current_cycle,
            "symbols": symbols_summary,
            "totals": {
                "symbols": len(self.symbols),
                "setups": total_setups,
                "risk_plans": total_risk,
                "validated": total_validated,
                "signals": total_signals,
            },
        }

    # ========================================================
    # FORMATAGE LOGS
    # ========================================================

    def format_symbol(self, symbol: str) -> str:

        diagnostic = self.get_symbol(symbol)

        lines = [
            "",
            f"===== NOVA ENGINE 2 | {diagnostic.symbol} =====",
        ]

        for stage_name in PIPELINE_STAGES:

            stage = diagnostic.stage(stage_name)

            if not stage.reached:
                marker = "·"
                text = "NON ATTEINT"

            elif stage.status in (
                "REJECTED",
                "ERROR",
            ):
                marker = "✗"
                text = stage.reason or stage.status

            elif stage.status in (
                "WAITING",
                "WAIT",
            ):
                marker = "…"
                text = stage.reason or stage.status

            elif stage.status == "SENT":
                marker = "✓"
                text = "SIGNAL ENVOYÉ"

            else:
                marker = "✓"
                text = stage.status

            count_text = ""

            if stage.count:
                count_text = f" [{stage.count}]"

            lines.append(
                f"{marker} {stage_name:<14} "
                f"{text}{count_text}"
            )

        lines.append(
            f"FINAL          : {diagnostic.final_status}"
        )

        if diagnostic.final_reason:
            lines.append(
                f"RAISON         : {diagnostic.final_reason}"
            )

        lines.append("=" * 45)

        return "\n".join(lines)

    def format_cycle(self) -> str:

        lines = [
            "",
            "╔════════════════════════════════════════════╗",
            "║     NOVA ENGINE 2 — DIAGNOSTIC PIPELINE  ║",
            "╚════════════════════════════════════════════╝",
            f"CYCLE : {self.current_cycle}",
        ]

        for symbol in self.symbols:
            lines.append(
                self.format_symbol(symbol)
            )

        summary = self.build_cycle_summary()

        totals = summary["totals"]

        lines.extend(
            [
                "",
                "----- TOTAL CYCLE -----",
                f"ACTIFS       : {totals['symbols']}",
                f"SETUPS       : {totals['setups']}",
                f"RISK PLANS   : {totals['risk_plans']}",
                f"VALIDÉS      : {totals['validated']}",
                f"SIGNAUX      : {totals['signals']}",
                "-----------------------",
            ]
        )

        return "\n".join(lines)

    def log_cycle(self) -> None:

        text = self.format_cycle()

        self.logger.info(text)

    # ========================================================
    # HISTORIQUE
    # ========================================================

    def save_cycle(self) -> Dict[str, Any]:

        summary = self.build_cycle_summary()

        self.history.append(summary)

        if len(self.history) > self.max_history:
            self.history = self.history[
                -self.max_history:
            ]

        return summary

    def finish_cycle(self) -> Dict[str, Any]:

        summary = self.save_cycle()

        self.log_cycle()

        return summary

    # ========================================================
    # STATISTIQUES
    # ========================================================

    def statistics(self) -> Dict[str, Any]:

        stats: Dict[str, Dict[str, int]] = {}

        for diagnostic in self.symbols.values():

            for stage_name in PIPELINE_STAGES:

                stage = diagnostic.stage(stage_name)

                if stage_name not in stats:
                    stats[stage_name] = {
                        "reached": 0,
                        "count": 0,
                        "rejected": 0,
                        "waiting": 0,
                    }

                if stage.reached:
                    stats[stage_name]["reached"] += 1

                stats[stage_name]["count"] += stage.count

                if stage.status in (
                    "REJECTED",
                    "ERROR",
                ):
                    stats[stage_name]["rejected"] += 1

                if stage.status in (
                    "WAITING",
                    "WAIT",
                ):
                    stats[stage_name]["waiting"] += 1

        return stats


# ============================================================
# INSTANCE GLOBALE
# ============================================================

diagnostics = Moteur2Diagnostics()


# ============================================================
# FONCTIONS RACCOURCIES
# ============================================================

def start_diagnostic_cycle(
    *,
    cycle_id: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> str:

    return diagnostics.start_cycle(
        cycle_id=cycle_id,
        symbols=symbols,
    )


def record_stage(
    symbol: str,
    stage: str,
    *,
    value: Any = None,
    count: Optional[int] = None,
    status: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:

    diagnostics.record(
        symbol,
        stage,
        value=value,
        count=count,
        status=status,
        reason=reason,
        details=details,
    )


def record_rejection(
    symbol: str,
    stage: str,
    reason: str,
    *,
    count: int = 0,
    details: Optional[Dict[str, Any]] = None,
) -> None:

    diagnostics.record_rejection(
        symbol,
        stage,
        reason,
        count=count,
        details=details,
    )


def record_waiting(
    symbol: str,
    stage: str,
    reason: str,
    *,
    count: int = 0,
    details: Optional[Dict[str, Any]] = None,
) -> None:

    diagnostics.record_waiting(
        symbol,
        stage,
        reason,
        count=count,
        details=details,
    )


def record_signal(
    symbol: str,
    *,
    direction: Optional[str] = None,
    confidence: Optional[float] = None,
    quality: Optional[float] = None,
    rr: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:

    diagnostics.record_signal(
        symbol,
        direction=direction,
        confidence=confidence,
        quality=quality,
        rr=rr,
        details=details,
    )


def finish_diagnostic_cycle() -> Dict[str, Any]:

    return diagnostics.finish_cycle()


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "PIPELINE_STAGES",
    "DiagnosticStage",
    "SymbolDiagnostic",
    "Moteur2Diagnostics",
    "diagnostics",
    "start_diagnostic_cycle",
    "record_stage",
    "record_rejection",
    "record_waiting",
    "record_signal",
    "finish_diagnostic_cycle",
]