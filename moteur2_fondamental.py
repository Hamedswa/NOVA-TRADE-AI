"""
NOVA TRADE AI - MOTEUR 2
Analyse fondamentale / macro-économique.
RÔLE
----
Ce module enrichit l'analyse technique avec un contexte fondamental.
IMPORTANT
---------
- Ce module ne décide jamais BUY / SELL / WAIT.
- Ce module ne bloque jamais une opportunité technique.
- Aucun RR minimum.
- Aucun Risk Management financier.
- Aucun calcul de lot, capital ou risque par trade.
- Il ne dépend pas de BiQuote pour les données de marché.
- Il ne remplace pas economic_calendar.py.
- Il ne remplace pas economic_news_supervisor.py.
- Il peut consommer leurs informations lorsqu'elles sont disponibles.
- Les informations fondamentales restent descriptives/contributives.
ACTIFS PRINCIPAUX
-----------------
XAUUSD
BTCUSD
EURUSD
GBPUSD
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
# ---------------------------------------------------------------------------
# Mots-clés fondamentaux
# ---------------------------------------------------------------------------
ASSET_FACTORS: Dict[str, List[str]] = {
    "XAUUSD": [
        "USD",
        "taux_directeurs",
        "taux_reels",
        "rendements_obligataires",
        "inflation",
        "emploi",
        "croissance",
        "banques_centrales",
        "geopolitique",
        "aversion_au_risque",
        "demande_refuge",
    ],
    "BTCUSD": [
        "USD",
        "liquidite",
        "taux_directeurs",
        "taux_reels",
        "rendements_obligataires",
        "inflation",
        "regulation_crypto",
        "flux_crypto",
        "ETF",
        "adoption",
        "sentiment_risque",
        "evenements_reseau",
    ],
    "EURUSD": [
        "USD",
        "EUR",
        "BCE",
        "FED",
        "taux_directeurs",
        "inflation",
        "emploi",
        "PIB",
        "PMI",
        "rendements_obligataires",
        "politique_monetaire",
    ],
    "GBPUSD": [
        "USD",
        "GBP",
        "BOE",
        "FED",
        "taux_directeurs",
        "inflation",
        "emploi",
        "PIB",
        "PMI",
        "rendements_obligataires",
        "politique_monetaire",
    ],
}
# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class FundamentalFactor:
    """
    Un facteur fondamental individuel.
    bias :
        - bullish
        - bearish
        - neutral
        - mixed
        - unknown
    importance :
        0 à 100, uniquement descriptive.
    """
    name: str
    bias: str = "unknown"
    importance: float = 0.0
    description: str = ""
    source: str = "internal"
    timestamp: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "bias": self.bias,
            "importance": round(float(self.importance), 2),
            "description": self.description,
            "source": self.source,
            "timestamp": self.timestamp,
        }
@dataclass
class FundamentalEvent:
    """
    Événement macro ou fondamental.
    Cet événement ne bloque jamais directement un signal.
    """
    name: str
    currency: Optional[str] = None
    importance: str = "unknown"
    event_time: Optional[str] = None
    actual: Any = None
    forecast: Any = None
    previous: Any = None
    description: str = ""
    source: str = "calendar"
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "currency": self.currency,
            "importance": self.importance,
            "event_time": self.event_time,
            "actual": self.actual,
            "forecast": self.forecast,
            "previous": self.previous,
            "description": self.description,
            "source": self.source,
        }
@dataclass
class FundamentalContext:
    """
    Résultat global de l'analyse fondamentale d'un actif.
    """
    symbol: str
    state: str = "NEUTRAL"
    bullish_factors: List[str] = field(default_factory=list)
    bearish_factors: List[str] = field(default_factory=list)
    neutral_factors: List[str] = field(default_factory=list)
    mixed_factors: List[str] = field(default_factory=list)
    factors: List[FundamentalFactor] = field(default_factory=list)
    events: List[FundamentalEvent] = field(default_factory=list)
    macro_pressure: str = "NEUTRAL"
    event_risk: str = "LOW"
    technical_convergence: str = "UNKNOWN"
    summary: str = ""
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    informational_only: bool = True
    blocking: bool = False
    decision_owner: str = "moteur2_decision.py"
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state,
            "bullish_factors": list(self.bullish_factors),
            "bearish_factors": list(self.bearish_factors),
            "neutral_factors": list(self.neutral_factors),
            "mixed_factors": list(self.mixed_factors),
            "factors": [x.to_dict() for x in self.factors],
            "events": [x.to_dict() for x in self.events],
            "macro_pressure": self.macro_pressure,
            "event_risk": self.event_risk,
            "technical_convergence": self.technical_convergence,
            "summary": self.summary,
            "analyzed_at": self.analyzed_at,
            "informational_only": True,
            "blocking": False,
            "decision_owner": self.decision_owner,
        }
# ---------------------------------------------------------------------------
# Moteur fondamental
# ---------------------------------------------------------------------------
class Moteur2Fondamental:
    """
    Analyseur fondamental autonome mais non décisionnel.
    L'objectif est de répondre à :
        "Quel est le contexte macro autour de cet actif maintenant ?"
    et non :
        "Faut-il acheter ou vendre ?"
    """
    def __init__(
        self,
        supported_symbols: Optional[Sequence[str]] = None,
    ) -> None:
        symbols = supported_symbols or SUPPORTED_SYMBOLS
        self.supported_symbols = tuple(
            str(symbol).upper().replace("/", "")
            for symbol in symbols
        )
    # ------------------------------------------------------------------
    # API principale
    # ------------------------------------------------------------------
    def analyser(
        self,
        symbol: str,
        *,
        events: Optional[Iterable[Any]] = None,
        news: Optional[Iterable[Any]] = None,
        macro_context: Optional[Dict[str, Any]] = None,
        technical_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse le contexte fondamental.
        Tous les paramètres externes sont optionnels.
        Cela permet d'intégrer progressivement :
            economic_calendar.py
            economic_news_supervisor.py
            ai_session_supervisor.py
            futures sources macro
            news sources
            etc.
        sans toucher à BiQuote.
        """
        normalized_symbol = self._normalize_symbol(symbol)
        context = FundamentalContext(symbol=normalized_symbol)
        raw_events = self._normalize_events(events)
        raw_news = self._normalize_news(news)
        context.events.extend(raw_events)
        self._analyse_macro_context(
            context,
            macro_context,
        )
        self._analyse_events(
            context,
            raw_events,
        )
        self._analyse_news(
            context,
            raw_news,
        )
        self._analyse_technical_convergence(
            context,
            technical_context,
        )
        self._finalize_state(context)
        return context.to_dict()
    # ------------------------------------------------------------------
    # Compatibilité
    # ------------------------------------------------------------------
    def analyze(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Alias anglais.
        """
        return self.analyser(symbol, **kwargs)
    # ------------------------------------------------------------------
    # Normalisation symbole
    # ------------------------------------------------------------------
    def _normalize_symbol(self, symbol: str) -> str:
        value = str(symbol or "").upper().replace("/", "").replace("-", "")
        aliases = {
            "GOLD": "XAUUSD",
            "XAU": "XAUUSD",
            "BTC": "BTCUSD",
            "BITCOIN": "BTCUSD",
            "EUR": "EURUSD",
            "GBP": "GBPUSD",
        }
        return aliases.get(value, value)
    # ------------------------------------------------------------------
    # Événements
    # ------------------------------------------------------------------
    def _normalize_events(
        self,
        events: Optional[Iterable[Any]],
    ) -> List[FundamentalEvent]:
        if events is None:
            return []
        result: List[FundamentalEvent] = []
        if isinstance(events, dict):
            events = [events]
        for item in events:
            if isinstance(item, FundamentalEvent):
                result.append(item)
                continue
            if isinstance(item, str):
                result.append(
                    FundamentalEvent(
                        name=item,
                        description=item,
                        source="external",
                    )
                )
                continue
            if not isinstance(item, dict):
                continue
            result.append(
                FundamentalEvent(
                    name=str(
                        item.get("name")
                        or item.get("event")
                        or item.get("title")
                        or "event_unknown"
                    ),
                    currency=item.get("currency"),
                    importance=str(
                        item.get("importance")
                        or item.get("impact")
                        or "unknown"
                    ),
                    event_time=item.get(
                        "event_time",
                        item.get("time"),
                    ),
                    actual=item.get("actual"),
                    forecast=item.get("forecast"),
                    previous=item.get("previous"),
                    description=str(
                        item.get("description")
                        or item.get("summary")
                        or ""
                    ),
                    source=str(
                        item.get("source")
                        or "external"
                    ),
                )
            )
        return result
    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------
    def _normalize_news(
        self,
        news: Optional[Iterable[Any]],
    ) -> List[Dict[str, Any]]:
        if news is None:
            return []
        if isinstance(news, dict):
            news = [news]
        result: List[Dict[str, Any]] = []
        for item in news:
            if isinstance(item, str):
                result.append(
                    {
                        "title": item,
                        "description": item,
                    }
                )
                continue
            if isinstance(item, dict):
                result.append(dict(item))
        return result
    # ------------------------------------------------------------------
    # Contexte macro
    # ------------------------------------------------------------------
    def _analyse_macro_context(
        self,
        context: FundamentalContext,
        macro_context: Optional[Dict[str, Any]],
    ) -> None:
        if not macro_context:
            context.neutral_factors.append(
                "Aucune donnée macro structurée fournie"
            )
            return
        for key, raw_value in macro_context.items():
            name = str(key)
            bias = self._infer_bias(raw_value)
            importance = self._infer_importance(
                name,
                raw_value,
            )
            description = self._describe_value(
                name,
                raw_value,
            )
            factor = FundamentalFactor(
                name=name,
                bias=bias,
                importance=importance,
                description=description,
                source="macro_context",
            )
            context.factors.append(factor)
            self._register_factor(
                context,
                factor,
            )
    # ------------------------------------------------------------------
    # Analyse événements
    # ------------------------------------------------------------------
    def _analyse_events(
        self,
        context: FundamentalContext,
        events: List[FundamentalEvent],
    ) -> None:
        if not events:
            return
        high_count = 0
        medium_count = 0
        for event in events:
            importance = event.importance.lower()
            if any(
                word in importance
                for word in (
                    "high",
                    "fort",
                    "important",
                    "red",
                )
            ):
                high_count += 1
            elif any(
                word in importance
                for word in (
                    "medium",
                    "moyen",
                    "moderate",
                    "orange",
                )
            ):
                medium_count += 1
        if high_count > 0:
            context.event_risk = "HIGH"
        elif medium_count > 0:
            context.event_risk = "MEDIUM"
        else:
            context.event_risk = "LOW"
    # ------------------------------------------------------------------
    # Analyse news
    # ------------------------------------------------------------------
    def _analyse_news(
        self,
        context: FundamentalContext,
        news: List[Dict[str, Any]],
    ) -> None:
        for item in news:
            title = str(
                item.get("title")
                or item.get("headline")
                or ""
            )
            description = str(
                item.get("description")
                or item.get("summary")
                or ""
            )
            text = f"{title} {description}".lower()
            bullish_words = (
                "bullish",
                "positive",
                "hausse",
                "fort",
                "strong",
                "support",
                "stimulus",
            )
            bearish_words = (
                "bearish",
                "negative",
                "baisse",
                "faible",
                "weak",
                "pressure",
                "stress",
            )
            bullish = sum(
                1 for word in bullish_words
                if word in text
            )
            bearish = sum(
                1 for word in bearish_words
                if word in text
            )
            if bullish > bearish:
                context.bullish_factors.append(
                    f"News: {title or 'information positive'}"
                )
            elif bearish > bullish:
                context.bearish_factors.append(
                    f"News: {title or 'information négative'}"
                )
            else:
                context.neutral_factors.append(
                    f"News: {title or 'information neutre'}"
                )
    # ------------------------------------------------------------------
    # Convergence technique / fondamentale
    # ------------------------------------------------------------------
    def _analyse_technical_convergence(
        self,
        context: FundamentalContext,
        technical_context: Optional[Dict[str, Any]],
    ) -> None:
        if not technical_context:
            context.technical_convergence = "UNKNOWN"
            return
        technical_direction = str(
            technical_context.get("direction")
            or technical_context.get("bias")
            or technical_context.get("tendance")
            or ""
        ).upper()
        fundamental_direction = self._fundamental_direction(
            context
        )
        if not technical_direction:
            context.technical_convergence = "UNKNOWN"
            return
        if fundamental_direction == "NEUTRAL":
            context.technical_convergence = "NEUTRAL"
        elif technical_direction in (
            "BUY",
            "BULLISH",
            "HAUSSIER",
            "LONG",
        ):
            if fundamental_direction == "BULLISH":
                context.technical_convergence = "CONVERGENCE_BULLISH"
            elif fundamental_direction == "BEARISH":
                context.technical_convergence = "DIVERGENCE"
            else:
                context.technical_convergence = "MIXED"
        elif technical_direction in (
            "SELL",
            "BEARISH",
            "BAISSIER",
            "SHORT",
        ):
            if fundamental_direction == "BEARISH":
                context.technical_convergence = "CONVERGENCE_BEARISH"
            elif fundamental_direction == "BULLISH":
                context.technical_convergence = "DIVERGENCE"
            else:
                context.technical_convergence = "MIXED"
        else:
            context.technical_convergence = "UNKNOWN"
    # ------------------------------------------------------------------
    # État final
    # ------------------------------------------------------------------
    def _finalize_state(
        self,
        context: FundamentalContext,
    ) -> None:
        bullish = len(context.bullish_factors)
        bearish = len(context.bearish_factors)
        mixed = len(context.mixed_factors)
        if bullish > bearish and bullish > mixed:
            context.state = "BULLISH"
        elif bearish > bullish and bearish > mixed:
            context.state = "BEARISH"
        elif bullish > 0 and bearish > 0:
            context.state = "MIXED"
        else:
            context.state = "NEUTRAL"
        context.macro_pressure = context.state
        context.summary = self._build_summary(context)
        # Garantie architecturale.
        context.informational_only = True
        context.blocking = False
        context.decision_owner = "moteur2_decision.py"
    # ------------------------------------------------------------------
    # Facteurs
    # ------------------------------------------------------------------
    def _register_factor(
        self,
        context: FundamentalContext,
        factor: FundamentalFactor,
    ) -> None:
        bias = factor.bias.lower()
        if bias == "bullish":
            context.bullish_factors.append(
                factor.name
            )
        elif bias == "bearish":
            context.bearish_factors.append(
                factor.name
            )
        elif bias == "mixed":
            context.mixed_factors.append(
                factor.name
            )
        else:
            context.neutral_factors.append(
                factor.name
            )
    # ------------------------------------------------------------------
    # Inférence simple
    # ------------------------------------------------------------------
    def _infer_bias(self, value: Any) -> str:
        if isinstance(value, dict):
            explicit = (
                value.get("bias")
                or value.get("direction")
                or value.get("impact")
            )
            if explicit:
                return self._normalize_bias(
                    explicit
                )
            bullish = value.get("bullish")
            bearish = value.get("bearish")
            if bullish is True and bearish is not True:
                return "bullish"
            if bearish is True and bullish is not True:
                return "bearish"
            return "neutral"
        if isinstance(value, bool):
            return "bullish" if value else "bearish"
        if isinstance(value, (int, float)):
            if value > 0:
                return "bullish"
            if value < 0:
                return "bearish"
            return "neutral"
        return self._normalize_bias(value)
    def _normalize_bias(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in (
            "bullish",
            "buy",
            "long",
            "positive",
            "hausse",
            "haussier",
        ):
            return "bullish"
        if text in (
            "bearish",
            "sell",
            "short",
            "negative",
            "baisse",
            "baissier",
        ):
            return "bearish"
        if text in (
            "mixed",
            "mix",
            "divergent",
            "divergence",
        ):
            return "mixed"
        if text in (
            "neutral",
            "neutre",
            "flat",
        ):
            return "neutral"
        return "unknown"
    # ------------------------------------------------------------------
    # Importance
    # ------------------------------------------------------------------
    def _infer_importance(
        self,
        name: str,
        value: Any,
    ) -> float:
        if isinstance(value, dict):
            raw = value.get(
                "importance",
                value.get("impact"),
            )
            if isinstance(raw, (int, float)):
                return max(
                    0.0,
                    min(100.0, float(raw)),
                )
            text = str(raw or "").lower()
            if any(
                x in text
                for x in (
                    "high",
                    "fort",
                    "important",
                    "red",
                )
            ):
                return 90.0
            if any(
                x in text
                for x in (
                    "medium",
                    "moyen",
                    "moderate",
                )
            ):
                return 60.0
        important_keywords = (
            "rate",
            "taux",
            "fed",
            "ecb",
            "bce",
            "boe",
            "inflation",
            "cpi",
            "nfp",
            "employment",
            "emploi",
            "gdp",
            "pib",
            "pmi",
            "geopolit",
        )
        lowered = name.lower()
        if any(
            keyword in lowered
            for keyword in important_keywords
        ):
            return 80.0
        return 50.0
    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------
    def _describe_value(
        self,
        name: str,
        value: Any,
    ) -> str:
        if isinstance(value, dict):
            description = value.get(
                "description"
            )
            if description:
                return str(description)
            return str(value)
        return f"{name}: {value}"
    # ------------------------------------------------------------------
    # Direction fondamentale
    # ------------------------------------------------------------------
    def _fundamental_direction(
        self,
        context: FundamentalContext,
    ) -> str:
        bullish = len(context.bullish_factors)
        bearish = len(context.bearish_factors)
        if bullish > bearish:
            return "BULLISH"
        if bearish > bullish:
            return "BEARISH"
        return "NEUTRAL"
    # ------------------------------------------------------------------
    # Résumé
    # ------------------------------------------------------------------
    def _build_summary(
        self,
        context: FundamentalContext,
    ) -> str:
        parts: List[str] = []
        parts.append(
            f"Contexte fondamental {context.state.lower()}"
        )
        if context.event_risk != "LOW":
            parts.append(
                f"risque événementiel {context.event_risk.lower()}"
            )
        if context.technical_convergence != "UNKNOWN":
            parts.append(
                f"relation technique/fondamentale: "
                f"{context.technical_convergence.lower()}"
            )
        return " | ".join(parts)
    # ------------------------------------------------------------------
    # Facteurs attendus par actif
    # ------------------------------------------------------------------
    def facteurs_attendus(
        self,
        symbol: str,
    ) -> List[str]:
        normalized = self._normalize_symbol(symbol)
        return list(
            ASSET_FACTORS.get(
                normalized,
                [],
            )
        )
    # ------------------------------------------------------------------
    # Validation douce
    # ------------------------------------------------------------------
    def est_compatible(
        self,
        symbol: str,
    ) -> bool:
        """
        Vérifie uniquement si le symbole est connu.
        Cette méthode n'est jamais utilisée comme filtre
        de décision de trading.
        """
        return (
            self._normalize_symbol(symbol)
            in self.supported_symbols
        )
# ---------------------------------------------------------------------------
# Fonction pratique
# ---------------------------------------------------------------------------
def analyser_fondamental(
    symbol: str,
    *,
    events: Optional[Iterable[Any]] = None,
    news: Optional[Iterable[Any]] = None,
    macro_context: Optional[Dict[str, Any]] = None,
    technical_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fonction simple pour utiliser le module sans instancier
    directement Moteur2Fondamental.
    """
    moteur = Moteur2Fondamental()
    return moteur.analyser(
        symbol,
        events=events,
        news=news,
        macro_context=macro_context,
        technical_context=technical_context,
    )
__all__ = [
    "SUPPORTED_SYMBOLS",
    "ASSET_FACTORS",
    "FundamentalFactor",
    "FundamentalEvent",
    "FundamentalContext",
    "Moteur2Fondamental",
    "analyser_fondamental",
]