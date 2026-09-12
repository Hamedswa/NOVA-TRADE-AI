"""
NOVA TRADE AI - ENGINE 2
moteur2_setups.py

Couche de génération d'opportunités.

Rôle :
    zones + contexte + confluences + comportement du prix
        -> plusieurs scénarios de setup
        -> classement des opportunités

Cette couche reste contributive :
    - aucun Entry / SL / TP / RR
    - aucune validation finale
    - aucune décision d'envoi Telegram
    - aucune dépendance aux timeframes M5/M1 pour valider un setup

Les scénarios sont adaptatifs. Le moteur cherche la meilleure lecture
présente autour d'une zone importante au lieu d'imposer une checklist unique.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


SUPPORTED_SYMBOLS = ("XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
PRIMARY_TIMEFRAMES = ("H4", "H1", "M15")

# Seuils volontairement souples : ils servent à éviter les scénarios
# totalement dépourvus d'information, pas à fabriquer un filtre dur.
MIN_DIRECTIONAL_STRENGTH = 10.0
MIN_SCENARIO_CONFIDENCE = 42.0
MAX_SETUPS_PER_ZONE = 4

ZONE_DISTANCE_RANGE_MULTIPLIER = 1.35
BREAKOUT_BUFFER_RANGE_MULTIPLIER = 0.30

SETUP_TYPES = (
    "CONTINUATION",
    "REJET",
    "CASSURE_REPRISE",
    "RETOURNEMENT",
    "IMPULSION",
    "REACTION_RANGE",
)


@dataclass
class Setup:
    setup_id: str
    zone_id: str
    setup_type: str
    direction: str
    zone_price: float
    timeframe: str
    confidence: float
    context: str
    reason: str
    entry_ready: bool
    waiting_for_confirmation: bool
    supporting_confluences: List[Dict[str, Any]]
    opposing_confluences: List[Dict[str, Any]]
    confluence_groups: List[Dict[str, Any]]
    evidence: Dict[str, Any]


class Moteur2Setups:
    """Génère et classe des scénarios naturels sans décider du signal final."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # ANALYSE PRINCIPALE
    # ------------------------------------------------------------------
    def analyser(
        self,
        zones_result: Dict[str, Any],
        confluences_result: Dict[str, Any],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        zones = zones_result.get("zones", []) if isinstance(zones_result, dict) else []
        confluence_zones = (
            confluences_result.get("zones", [])
            if isinstance(confluences_result, dict)
            else []
        )
        if not isinstance(zones, list):
            zones = []
        if not isinstance(confluence_zones, list):
            confluence_zones = []

        resolved_symbol = self._resolve_symbol(
            symbol,
            zones_result,
            confluences_result,
            context_result,
        )

        if not zones or not confluence_zones:
            return self._empty_result(resolved_symbol)

        setups: List[Setup] = []
        for confluence_zone in confluence_zones:
            if not isinstance(confluence_zone, dict):
                continue
            zone = self._find_matching_zone(
                confluence_zone,
                zones,
                candles_by_timeframe,
            )
            if zone is None:
                continue
            setups.extend(
                self._detect_setups_for_zone(
                    zone,
                    confluence_zone,
                    context_result,
                    candles_by_timeframe,
                )
            )

        # Déduplication : plusieurs familles peuvent décrire exactement
        # le même scénario. On garde la meilleure lecture.
        setups = self._deduplicate_setups(setups)
        setups.sort(key=self._ranking_key, reverse=True)

        return {
            "symbol": resolved_symbol,
            "setups": [asdict(item) for item in setups],
            "best_setup": asdict(setups[0]) if setups else None,
            "opportunity_count": len(setups),
            "setup_types_found": list(dict.fromkeys(item.setup_type for item in setups)),
            "ranking": [
                {
                    "setup_id": item.setup_id,
                    "setup_type": item.setup_type,
                    "direction": item.direction,
                    "confidence": item.confidence,
                }
                for item in setups
            ],
            "descriptive_only": True,
            "blocking": False,
        }

    # ------------------------------------------------------------------
    # DÉTECTION PAR ZONE
    # ------------------------------------------------------------------
    def _detect_setups_for_zone(
        self,
        zone: Dict[str, Any],
        confluence_zone: Dict[str, Any],
        context_result: Dict[str, Any],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> List[Setup]:
        zone_id = str(
            confluence_zone.get("zone_id")
            or zone.get("id")
            or "ZONE"
        )
        zone_price = self._extract_zone_price(zone)
        if zone_price <= 0:
            return []

        timeframe = str(zone.get("timeframe", "M15")).upper()
        if timeframe not in PRIMARY_TIMEFRAMES:
            timeframe = "M15"

        direction = self._normalize_direction(confluence_zone.get("direction"))
        if direction not in ("HAUSSIER", "BAISSIER"):
            direction = self._infer_direction(zone, context_result)
        if direction not in ("HAUSSIER", "BAISSIER"):
            return []

        confluences = confluence_zone.get("confluences", [])
        if not isinstance(confluences, list):
            confluences = []
        supporting, opposing = self._split_confluences(confluences, direction)

        groups = confluence_zone.get("confluence_groups", [])
        if not isinstance(groups, list):
            groups = []

        evidence_summary = confluence_zone.get("evidence_summary", {})
        if not isinstance(evidence_summary, dict):
            evidence_summary = {}

        directional_strength = max(
            self._safe_float(confluence_zone.get("bullish_strength")) or 0.0,
            self._safe_float(confluence_zone.get("bearish_strength")) or 0.0,
        )

        market_state = self._market_state(context_result)
        global_direction = self._get_context_direction(context_result, "global")
        h4_direction = self._get_context_direction(context_result, "H4")
        h1_direction = self._get_context_direction(context_result, "H1")
        m15_direction = self._get_context_direction(context_result, "M15")

        reaction = self._recent_primary_reaction(
            candles_by_timeframe, zone, zone_price
        )
        correction = self._has_correction_before_zone(
            candles_by_timeframe, zone_price, direction
        )
        rejection_shape = self._has_rejection_shape(
            candles_by_timeframe, zone_price, direction
        )
        transition = self._has_directional_transition(
            candles_by_timeframe, direction
        )
        impulse = self._has_recent_impulse(
            candles_by_timeframe, direction
        )
        breakout_retake = self._has_breakout_retake(
            candles_by_timeframe, zone, zone_price, direction
        )
        near_zone = self._is_price_near_zone(
            candles_by_timeframe, zone_price
        )

        base_confidence = self._base_confidence(
            supporting,
            opposing,
            directional_strength,
            evidence_summary,
            groups,
        )

        candidates: List[Setup] = []

        # 1) CONTINUATION : contexte directionnel + correction/reaction.
        if (
            near_zone
            and correction
            and reaction == direction
            and self._direction_compatible(global_direction, direction)
            and self._direction_compatible(h1_direction, direction)
        ):
            confidence = base_confidence + 10.0
            if m15_direction == direction:
                confidence += 4.0
            if impulse:
                confidence += 3.0
            candidates.append(
                self._make_setup(
                    zone_id,
                    zone_price,
                    timeframe,
                    "CONTINUATION",
                    direction,
                    confidence,
                    "Correction vers une zone importante dans un contexte directionnel cohérent.",
                    "Le prix corrige vers la zone puis montre une réaction compatible avec le contexte dominant.",
                    supporting,
                    opposing,
                    groups,
                    reaction=reaction,
                    market_state=market_state,
                    evidence_summary=evidence_summary,
                )
            )

        # 2) REJET : réaction locale nette, même si le contexte n'est pas parfait.
        if near_zone and reaction == direction and rejection_shape:
            confidence = base_confidence + 7.0
            if self._zone_direction_matches(str(zone.get("type", "")), direction):
                confidence += 3.0
            candidates.append(
                self._make_setup(
                    zone_id,
                    zone_price,
                    timeframe,
                    "REJET",
                    direction,
                    confidence,
                    "Test d'une zone importante avec réaction locale nette.",
                    "La réaction du prix et la forme récente des bougies favorisent le scénario autour de la zone.",
                    supporting,
                    opposing,
                    groups,
                    reaction=reaction,
                    market_state=market_state,
                    evidence_summary=evidence_summary,
                )
            )

        # 3) CASSURE_REPRISE : dépassement puis retour contrôlé.
        if breakout_retake:
            confidence = base_confidence + 9.0
            if global_direction == direction:
                confidence += 3.0
            candidates.append(
                self._make_setup(
                    zone_id,
                    zone_price,
                    timeframe,
                    "CASSURE_REPRISE",
                    direction,
                    confidence,
                    "Le prix dépasse une référence puis revient tester la zone avant de conserver sa direction.",
                    "Dépassement, retour contrôlé et maintien du prix du côté cohérent avec le scénario.",
                    supporting,
                    opposing,
                    groups,
                    reaction=reaction,
                    market_state=market_state,
                    evidence_summary=evidence_summary,
                )
            )

        # 4) RETOURNEMENT : transition H1/M15 + réaction sur zone.
        if (
            near_zone
            and transition
            and reaction == direction
            and m15_direction == direction
            and h1_direction in ("HAUSSIER", "BAISSIER")
            and h1_direction != direction
        ):
            confidence = base_confidence + 8.0
            if h4_direction not in ("HAUSSIER", "BAISSIER") or h4_direction != h1_direction:
                confidence += 3.0
            candidates.append(
                self._make_setup(
                    zone_id,
                    zone_price,
                    timeframe,
                    "RETOURNEMENT",
                    direction,
                    confidence,
                    "Transition directionnelle entre H1 et M15 autour d'une zone importante.",
                    "Le contexte intermédiaire évolue tandis que le M15 imprime une réaction directionnelle.",
                    supporting,
                    opposing,
                    groups,
                    reaction=reaction,
                    market_state=market_state,
                    evidence_summary=evidence_summary,
                )
            )

        # 5) IMPULSION : opportunité de continuation basée sur une pression récente.
        if (
            near_zone
            and impulse
            and reaction == direction
            and self._direction_compatible(m15_direction, direction)
        ):
            confidence = base_confidence + 6.0
            if global_direction == direction:
                confidence += 3.0
            candidates.append(
                self._make_setup(
                    zone_id,
                    zone_price,
                    timeframe,
                    "IMPULSION",
                    direction,
                    confidence,
                    "Pression directionnelle récente et réaction du prix autour d'une zone importante.",
                    "L'amplitude et la progression récente du prix soutiennent une poursuite potentielle.",
                    supporting,
                    opposing,
                    groups,
                    reaction=reaction,
                    market_state=market_state,
                    evidence_summary=evidence_summary,
                )
            )

        # 6) REACTION_RANGE : exploite un bord de range sans exiger une tendance.
        if (
            near_zone
            and market_state == "RANGE"
            and reaction == direction
            and rejection_shape
        ):
            confidence = base_confidence + 8.0
            candidates.append(
                self._make_setup(
                    zone_id,
                    zone_price,
                    timeframe,
                    "REACTION_RANGE",
                    direction,
                    confidence,
                    "Réaction sur une zone située dans un environnement de range.",
                    "Le marché est en compression/range et le prix réagit depuis une zone importante.",
                    supporting,
                    opposing,
                    groups,
                    reaction=reaction,
                    market_state=market_state,
                    evidence_summary=evidence_summary,
                )
            )

        # Une zone peut produire plusieurs lectures : on garde les meilleures
        # sans imposer un seul modèle au marché.
        candidates = [
            item
            for item in candidates
            if item.confidence >= MIN_SCENARIO_CONFIDENCE
        ]
        candidates.sort(key=self._ranking_key, reverse=True)
        return candidates[:MAX_SETUPS_PER_ZONE]

    # ------------------------------------------------------------------
    # CONSTRUCTION / RANKING
    # ------------------------------------------------------------------
    def _make_setup(
        self,
        zone_id: str,
        zone_price: float,
        timeframe: str,
        setup_type: str,
        direction: str,
        confidence: float,
        context: str,
        reason: str,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        groups: List[Dict[str, Any]],
        **evidence: Any,
    ) -> Setup:
        confidence = max(0.0, min(100.0, confidence))
        setup_id = f"{zone_id}_{setup_type}"
        return Setup(
            setup_id=setup_id,
            zone_id=zone_id,
            setup_type=setup_type,
            direction=direction,
            zone_price=zone_price,
            timeframe=timeframe,
            confidence=round(confidence, 2),
            context=context,
            reason=reason,
            entry_ready=False,
            waiting_for_confirmation=True,
            supporting_confluences=supporting,
            opposing_confluences=opposing,
            confluence_groups=groups,
            evidence=evidence,
        )

    @staticmethod
    def _ranking_key(item: Setup) -> Tuple[float, float, float, int]:
        diverse = 1.0 if item.evidence.get("evidence_summary", {}).get("diverse_evidence") else 0.0
        multi_tf = 1.0 if item.evidence.get("evidence_summary", {}).get("multi_timeframe_evidence") else 0.0
        contradiction = 1.0 if item.evidence.get("evidence_summary", {}).get("contradiction") else 0.0
        # La diversité et la cohérence multi-timeframe départagent les setups
        # proches sans transformer le nombre de preuves en score artificiel.
        return (
            item.confidence,
            diverse,
            multi_tf,
            -int(contradiction),
        )

    @staticmethod
    def _deduplicate_setups(setups: List[Setup]) -> List[Setup]:
        best: Dict[Tuple[str, str, str], Setup] = {}
        for setup in setups:
            key = (setup.zone_id, setup.setup_type, setup.direction)
            previous = best.get(key)
            if previous is None or setup.confidence > previous.confidence:
                best[key] = setup
        return list(best.values())

    @staticmethod
    def _empty_result(symbol: Optional[str]) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "setups": [],
            "best_setup": None,
            "opportunity_count": 0,
            "setup_types_found": [],
            "ranking": [],
            "descriptive_only": True,
            "blocking": False,
        }

    # ------------------------------------------------------------------
    # CONFLUENCES / CONTEXTE
    # ------------------------------------------------------------------
    @staticmethod
    def _split_confluences(
        confluences: List[Dict[str, Any]],
        direction: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        supporting: List[Dict[str, Any]] = []
        opposing: List[Dict[str, Any]] = []
        for item in confluences:
            if not isinstance(item, dict):
                continue
            item_direction = Moteur2Setups._normalize_direction(item.get("direction"))
            if item_direction == direction:
                supporting.append(item)
            elif item_direction in ("HAUSSIER", "BAISSIER"):
                opposing.append(item)
        return supporting, opposing

    def _base_confidence(
        self,
        supporting: List[Dict[str, Any]],
        opposing: List[Dict[str, Any]],
        directional_strength: float,
        evidence_summary: Dict[str, Any],
        groups: List[Dict[str, Any]],
    ) -> float:
        score = 44.0
        score += min(16.0, max(0.0, directional_strength) * 0.16)
        score += min(12.0, len(supporting) * 2.0)
        score -= min(10.0, len(opposing) * 2.0)
        if evidence_summary.get("diverse_evidence"):
            score += 5.0
        if evidence_summary.get("multi_timeframe_evidence"):
            score += 4.0
        if groups:
            score += min(4.0, len(groups) * 0.8)
        # Une contradiction est une information à conserver, pas une
        # interdiction automatique. Elle réduit simplement la confiance.
        if evidence_summary.get("contradiction"):
            score -= 5.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _market_state(context_result: Dict[str, Any]) -> str:
        candidates = [
            context_result.get("market_context", {}).get("market_state")
            if isinstance(context_result.get("market_context"), dict)
            else None,
            context_result.get("global", {}).get("market_state")
            if isinstance(context_result.get("global"), dict)
            else None,
            context_result.get("market_state"),
        ]
        for value in candidates:
            state = str(value or "").upper()
            if state in ("TENDANCE", "RANGE", "IMPULSION", "CORRECTION", "TRANSITION"):
                return state
        return "NEUTRE"

    @staticmethod
    def _get_context_direction(context_result: Dict[str, Any], location: str) -> str:
        if not isinstance(context_result, dict):
            return "NEUTRE"
        if location == "global":
            context = context_result.get("global", {})
            if not isinstance(context, dict):
                context = context_result.get("contextual_environment", {})
        else:
            context = context_result.get("timeframes", {}).get(location, {})
        if not isinstance(context, dict):
            return "NEUTRE"
        return Moteur2Setups._normalize_direction(context.get("direction"))

    @staticmethod
    def _direction_compatible(context_direction: str, direction: str) -> bool:
        return context_direction in ("NEUTRE", direction)

    # ------------------------------------------------------------------
    # PRICE BEHAVIOUR
    # ------------------------------------------------------------------
    def _is_price_near_zone(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
    ) -> bool:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 5:
            return False
        recent = candles[-8:]
        avg = self._average_range(recent)
        if avg <= 0:
            return False
        last_close = self._float(getattr(recent[-1], "close", None))
        if last_close is None:
            return False
        return abs(last_close - zone_price) <= avg * ZONE_DISTANCE_RANGE_MULTIPLIER or any(
            (self._float(getattr(c, "low", None)) or 0) <= zone_price <= (self._float(getattr(c, "high", None)) or 0)
            for c in recent
        )

    def _recent_primary_reaction(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone: Dict[str, Any],
        zone_price: float,
    ) -> str:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 5:
            return "NEUTRE"
        recent = candles[-6:]
        avg = self._average_range(recent)
        if avg <= 0:
            return "NEUTRE"
        tolerance = avg * ZONE_DISTANCE_RANGE_MULTIPLIER
        bullish = bearish = 0.0
        touched = False
        low_zone, high_zone = self._zone_bounds(zone)
        for candle in recent:
            high = self._float(getattr(candle, "high", None))
            low = self._float(getattr(candle, "low", None))
            op = self._float(getattr(candle, "open", None))
            close = self._float(getattr(candle, "close", None))
            if None in (high, low, op, close):
                continue
            if high >= low_zone - tolerance and low <= high_zone + tolerance:
                touched = True
                rng = high - low
                if rng <= 0:
                    continue
                pos = (close - low) / rng
                body_ratio = abs(close - op) / rng
                if close > op and pos >= 0.55 and body_ratio >= 0.25:
                    bullish += 1.0
                elif close < op and pos <= 0.45 and body_ratio >= 0.25:
                    bearish += 1.0
        if not touched:
            return "NEUTRE"
        if bullish > bearish and bullish >= 1.5:
            return "HAUSSIER"
        if bearish > bullish and bearish >= 1.5:
            return "BAISSIER"
        return "NEUTRE"

    def _has_correction_before_zone(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
        direction: str,
    ) -> bool:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 10:
            return False
        recent = candles[-10:]
        avg = self._average_range(recent)
        if avg <= 0:
            return False
        first = self._float(getattr(recent[0], "close", None))
        middle = self._float(getattr(recent[5], "close", None))
        last = self._float(getattr(recent[-1], "close", None))
        if None in (first, middle, last):
            return False
        near = abs(last - zone_price) <= avg * ZONE_DISTANCE_RANGE_MULTIPLIER
        if not near:
            return False
        initial = middle - first
        correction = last - middle
        if direction == "HAUSSIER":
            return initial > avg * 0.35 and correction < -avg * 0.18
        return initial < -avg * 0.35 and correction > avg * 0.18

    def _has_rejection_shape(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone_price: float,
        direction: str,
    ) -> bool:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 4:
            return False
        recent = candles[-5:]
        avg = self._average_range(recent)
        if avg <= 0:
            return False
        tolerance = avg * ZONE_DISTANCE_RANGE_MULTIPLIER
        for candle in recent:
            high = self._float(getattr(candle, "high", None))
            low = self._float(getattr(candle, "low", None))
            op = self._float(getattr(candle, "open", None))
            close = self._float(getattr(candle, "close", None))
            if None in (high, low, op, close):
                continue
            if not (low - tolerance <= zone_price <= high + tolerance):
                continue
            rng = high - low
            body = abs(close - op)
            if rng <= 0:
                continue
            upper = high - max(op, close)
            lower = min(op, close) - low
            if direction == "HAUSSIER" and lower >= max(body * 1.05, rng * 0.25) and close >= op:
                return True
            if direction == "BAISSIER" and upper >= max(body * 1.05, rng * 0.25) and close <= op:
                return True
        return False

    def _has_directional_transition(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        direction: str,
    ) -> bool:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 8:
            return False
        recent = candles[-8:]
        closes = [self._float(getattr(c, "close", None)) for c in recent]
        if any(v is None for v in closes):
            return False
        avg = self._average_range(recent)
        if avg <= 0:
            return False
        first = closes[:4]
        second = closes[4:]
        move1 = first[-1] - first[0]
        move2 = second[-1] - second[0]
        if direction == "HAUSSIER":
            return move1 < 0 and move2 > avg * 0.30
        return move1 > 0 and move2 < -avg * 0.30

    def _has_recent_impulse(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        direction: str,
    ) -> bool:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 8:
            return False
        recent = candles[-8:]
        avg = self._average_range(recent[:-2])
        if avg <= 0:
            return False
        closes = [self._float(getattr(c, "close", None)) for c in recent]
        if any(v is None for v in closes):
            return False
        move = closes[-1] - closes[-4]
        return move > avg * 0.75 if direction == "HAUSSIER" else move < -avg * 0.75

    def _has_breakout_retake(
        self,
        candles_by_timeframe: Dict[str, List[Any]],
        zone: Dict[str, Any],
        zone_price: float,
        direction: str,
    ) -> bool:
        candles = candles_by_timeframe.get("M15", [])
        if len(candles) < 12:
            return False
        recent = candles[-12:]
        avg = self._average_range(recent)
        if avg <= 0:
            return False
        buffer = avg * BREAKOUT_BUFFER_RANGE_MULTIPLIER
        zone_low, zone_high = self._zone_bounds(zone)
        closes = [self._float(getattr(c, "close", None)) for c in recent]
        highs = [self._float(getattr(c, "high", None)) for c in recent]
        lows = [self._float(getattr(c, "low", None)) for c in recent]
        if any(v is None for v in closes + highs + lows):
            return False
        if direction == "HAUSSIER":
            reference = max(highs[:7])
            broke = any(c > reference + buffer for c in closes[7:10])
            retest = any(l <= zone_high + buffer and c >= zone_price for l, c in zip(lows[9:], closes[9:]))
            return broke and retest and closes[-1] >= zone_price
        reference = min(lows[:7])
        broke = any(c < reference - buffer for c in closes[7:10])
        retest = any(h >= zone_low - buffer and c <= zone_price for h, c in zip(highs[9:], closes[9:]))
        return broke and retest and closes[-1] <= zone_price

    # ------------------------------------------------------------------
    # ZONE / DIRECTION / UTILS
    # ------------------------------------------------------------------
    @staticmethod
    def _find_matching_zone(
        confluence_zone: Dict[str, Any],
        zones: List[Dict[str, Any]],
        candles_by_timeframe: Dict[str, List[Any]],
    ) -> Optional[Dict[str, Any]]:
        zone_id = str(confluence_zone.get("zone_id", ""))
        if zone_id:
            for zone in zones:
                if isinstance(zone, dict) and str(zone.get("id", "")) == zone_id:
                    return zone
        target = Moteur2Setups._extract_zone_price(confluence_zone)
        if target <= 0:
            return None
        avg = Moteur2Setups._average_range(candles_by_timeframe.get("M15", [])[-20:])
        if avg <= 0:
            return None
        tolerance = avg * 1.5
        candidates = []
        for zone in zones:
            if not isinstance(zone, dict):
                continue
            price = Moteur2Setups._extract_zone_price(zone)
            if price > 0:
                candidates.append((abs(target - price), zone))
        candidates.sort(key=lambda x: x[0])
        for distance, zone in candidates:
            if distance <= tolerance:
                return zone
        return None

    @staticmethod
    def _zone_bounds(zone: Dict[str, Any]) -> Tuple[float, float]:
        low = Moteur2Setups._float(zone.get("low"))
        high = Moteur2Setups._float(zone.get("high"))
        if low is not None and high is not None and low > 0 and high > 0:
            return (low, high) if low <= high else (high, low)
        center = Moteur2Setups._extract_zone_price(zone)
        return center, center

    @staticmethod
    def _extract_zone_price(zone: Dict[str, Any]) -> float:
        for key in ("center", "price", "level", "value", "mid"):
            value = Moteur2Setups._float(zone.get(key))
            if value is not None and value > 0:
                return value
        low = Moteur2Setups._float(zone.get("low"))
        high = Moteur2Setups._float(zone.get("high"))
        if low is not None and high is not None and low > 0 and high > 0:
            return (low + high) / 2.0
        return 0.0

    @staticmethod
    def _zone_direction_matches(zone_type: str, direction: str) -> bool:
        value = str(zone_type or "").upper()
        if not value or value == "UNKNOWN":
            return True
        if direction == "HAUSSIER":
            return any(k in value for k in ("SUPPORT", "DEMANDE", "LOW"))
        return any(k in value for k in ("RESISTANCE", "OFFRE", "HIGH"))

    @staticmethod
    def _infer_direction(zone: Dict[str, Any], context_result: Dict[str, Any]) -> str:
        zone_type = str(zone.get("type", "")).upper()
        if any(k in zone_type for k in ("SUPPORT", "DEMANDE", "LOW")):
            return "HAUSSIER"
        if any(k in zone_type for k in ("RESISTANCE", "OFFRE", "HIGH")):
            return "BAISSIER"
        for location in ("M15", "H1", "H4", "global"):
            direction = Moteur2Setups._get_context_direction(context_result, location)
            if direction in ("HAUSSIER", "BAISSIER"):
                return direction
        return "NEUTRE"

    @staticmethod
    def _normalize_direction(value: Any) -> str:
        text = str(value or "").strip().upper()
        if text in ("HAUSSIER", "BULLISH", "BUY", "LONG"):
            return "HAUSSIER"
        if text in ("BAISSIER", "BEARISH", "SELL", "SHORT"):
            return "BAISSIER"
        return "NEUTRE"

    @staticmethod
    def _average_range(candles: List[Any]) -> float:
        ranges = []
        for candle in candles:
            high = Moteur2Setups._float(getattr(candle, "high", None))
            low = Moteur2Setups._float(getattr(candle, "low", None))
            if high is not None and low is not None and high > low:
                ranges.append(high - low)
        return sum(ranges) / len(ranges) if ranges else 0.0

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        return Moteur2Setups._float(value)

    @staticmethod
    def _resolve_symbol(
        symbol: Optional[str],
        zones_result: Dict[str, Any],
        confluences_result: Dict[str, Any],
        context_result: Dict[str, Any],
    ) -> Optional[str]:
        for candidate in (
            symbol,
            zones_result.get("symbol"),
            confluences_result.get("symbol"),
            context_result.get("symbol"),
        ):
            if candidate is None:
                continue
            normalized = (
                str(candidate).upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
            )
            if normalized in SUPPORTED_SYMBOLS:
                return normalized
        return None


def analyser_setups(
    zones_result: Dict[str, Any],
    confluences_result: Dict[str, Any],
    context_result: Dict[str, Any],
    candles_by_timeframe: Dict[str, List[Any]],
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """Fonction pratique de génération et classement des setups."""
    return Moteur2Setups().analyser(
        zones_result=zones_result,
        confluences_result=confluences_result,
        context_result=context_result,
        candles_by_timeframe=candles_by_timeframe,
        symbol=symbol,
    )
