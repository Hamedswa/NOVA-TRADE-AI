"""
NOVA TRADE AI - Moteur 2
moteur2_contexte.py
Détermination du contexte de marché.
Actifs :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD
Timeframes :
    H4
    H1
    M15
    M5
    M1
Rôle :
    - analyser le contexte H4
    - analyser le contexte H1
    - analyser le comportement M15
    - analyser le comportement M5
    - analyser le timing M1
    - déterminer le contexte global
    - décrire le comportement du prix autour des zones
IMPORTANT :
    Ce module est descriptif.
    Il ne :
        - produit pas de BUY/SELL
        - ne valide pas de setup
        - ne calcule pas Entry/SL/TP
        - ne calcule pas le RR
        - ne bloque pas un signal
La décision finale appartient exclusivement
à moteur2_validation.py.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from biquote_client import Candle
# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)
SUPPORTED_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)
MIN_CANDLES_TREND = 20
MIN_CANDLES_STRUCTURE = 5
# Nombre de bougies utilisées pour la détection de direction.
DIRECTION_LOOKBACK = {
    "H4": 20,
    "H1": 30,
    "M15": 30,
    "M5": 25,
    "M1": 20,
}
# Seuil de variation minimale exprimé en multiples
# de l'amplitude moyenne des bougies.
#
# Cela remplace le seuil fixe de 0.10 %.
TREND_RANGE_MULTIPLIER = {
    "H4": 1.50,
    "H1": 1.50,
    "M15": 1.35,
    "M5": 1.25,
    "M1": 1.15,
}
VOLATILITY_LOOKBACK = 20
# Seuil maximal de largeur relative d'un marché considéré
# comme comprimé/range.
RANGE_WIDTH_ATR_MULTIPLIER = 8.0
# Tolérance autour d'une zone :
# exprimée en multiples de l'amplitude moyenne des bougies.
ZONE_REACTION_ATR_MULTIPLIER = {
    "H4": 1.50,
    "H1": 1.50,
    "M15": 1.35,
    "M5": 1.20,
    "M1": 1.00,
}
TIMEFRAME_PRIORITY = {
    "H4": 4,
    "H1": 3,
    "M15": 2,
    "M5": 1,
    "M1": 0,
}
# ---------------------------------------------------------------------------
# STRUCTURES
# ---------------------------------------------------------------------------
@dataclass
class ContextTimeframe:
    """
    Contexte descriptif d'un timeframe.
    """
    timeframe: str
    direction: str
    structure: str
    strength: float
    price: Optional[float]
    reason: str
@dataclass
class GlobalContext:
    """
    Contexte descriptif global du marché.
    """
    direction: str
    state: str
    strength: float
    dominant_timeframe: str
    alignment: str
    reason: str
# ---------------------------------------------------------------------------
# MOTEUR CONTEXTE
# ---------------------------------------------------------------------------
class Moteur2Contexte:
    """
    Analyse du contexte de marché.
    H4 :
        contexte global
    H1 :
        contexte intermédiaire
    M15 :
        contexte principal
    M5 :
        comportement de confirmation
    M1 :
        timing secondaire
    Aucun timeframe ne produit ici une décision finale.
    """
    def __init__(self) -> None:
        pass
    # -----------------------------------------------------------------------
    # ANALYSE PRINCIPALE
    # -----------------------------------------------------------------------
    def analyser(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        zones_result: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyse le contexte de tous les timeframes disponibles.
        """
        resolved_symbol = self._resolve_symbol(
            symbol=symbol,
            zones_result=zones_result,
        )
        contexts: Dict[str, Dict[str, Any]] = {}
        for timeframe in SUPPORTED_TIMEFRAMES:
            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )
            if not candles:
                continue
            context = self._analyser_timeframe(
                candles=candles,
                timeframe=timeframe,
            )
            contexts[timeframe] = asdict(
                context
            )
        global_context = (
            self._determine_global_context(
                contexts
            )
        )
        zone_context = (
            self._analyser_zone_context(
                candles_by_timeframe=candles_by_timeframe,
                zones_result=zones_result,
            )
        )
        return {
            "symbol": resolved_symbol,
            "timeframes": contexts,
            "global": asdict(
                global_context
            ),
            "zone_context": zone_context,
        }
    # -----------------------------------------------------------------------
    # SYMBOLE
    # -----------------------------------------------------------------------
    @staticmethod
    def _normalize_symbol(
        symbol: Optional[str],
    ) -> Optional[str]:
        if symbol is None:
            return None
        normalized = (
            str(symbol)
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )
        return normalized or None
    def _resolve_symbol(
        self,
        symbol: Optional[str],
        zones_result: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        normalized = self._normalize_symbol(
            symbol
        )
        if normalized:
            return normalized
        if isinstance(
            zones_result,
            dict,
        ):
            normalized = self._normalize_symbol(
                zones_result.get("symbol")
            )
            if normalized:
                return normalized
        # Aucun fallback artificiel vers XAUUSD.
        return None
    # -----------------------------------------------------------------------
    # ANALYSE TIMEFRAME
    # -----------------------------------------------------------------------
    def _analyser_timeframe(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> ContextTimeframe:
        cleaned = self._clean_candles(
            candles
        )
        if len(cleaned) < MIN_CANDLES_STRUCTURE:
            return ContextTimeframe(
                timeframe=timeframe,
                direction="NEUTRE",
                structure="INSUFFISANTE",
                strength=0.0,
                price=None,
                reason="Pas assez de données.",
            )
        price = self._safe_float(
            cleaned[-1].close
        )
        direction = self._detect_direction(
            cleaned,
            timeframe,
        )
        structure = self._detect_structure(
            cleaned,
            timeframe,
        )
        strength = self._calculate_strength(
            candles=cleaned,
            direction=direction,
            structure=structure,
            timeframe=timeframe,
        )
        reason = self._build_reason(
            direction=direction,
            structure=structure,
        )
        return ContextTimeframe(
            timeframe=timeframe,
            direction=direction,
            structure=structure,
            strength=round(
                strength,
                2,
            ),
            price=price,
            reason=reason,
        )
    # -----------------------------------------------------------------------
    # DIRECTION
    # -----------------------------------------------------------------------
    def _detect_direction(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> str:
        if len(candles) < MIN_CANDLES_STRUCTURE:
            return "NEUTRE"
        lookback = min(
            DIRECTION_LOOKBACK.get(
                timeframe,
                20,
            ),
            len(candles),
        )
        recent = candles[-lookback:]
        start_price = self._safe_float(
            recent[0].close
        )
        end_price = self._safe_float(
            recent[-1].close
        )
        if (
            start_price is None
            or end_price is None
            or start_price <= 0
        ):
            return "NEUTRE"
        variation = abs(
            end_price - start_price
        )
        average_range = (
            self._average_candle_range(
                recent
            )
        )
        if (
            average_range is None
            or average_range <= 0
        ):
            return "NEUTRE"
        # Variation totale rapportée à la volatilité
        # moyenne du timeframe.
        movement_units = (
            variation / average_range
        )
        minimum_units = (
            TREND_RANGE_MULTIPLIER.get(
                timeframe,
                1.25,
            )
        )
        if movement_units < minimum_units:
            return "NEUTRE"
        if end_price > start_price:
            return "HAUSSIER"
        if end_price < start_price:
            return "BAISSIER"
        return "NEUTRE"
    # -----------------------------------------------------------------------
    # STRUCTURE DESCRIPTIVE
    # -----------------------------------------------------------------------
    def _detect_structure(
        self,
        candles: List[Candle],
        timeframe: str,
    ) -> str:
        if len(candles) < 6:
            return "INSUFFISANTE"
        recent = candles[-6:]
        highs = [
            float(c.high)
            for c in recent
        ]
        lows = [
            float(c.low)
            for c in recent
        ]
        higher_highs = self._is_increasing(
            highs
        )
        higher_lows = self._is_increasing(
            lows
        )
        lower_highs = self._is_decreasing(
            highs
        )
        lower_lows = self._is_decreasing(
            lows
        )
        if higher_highs and higher_lows:
            return "STRUCTURE_HAUSSIERE"
        if lower_highs and lower_lows:
            return "STRUCTURE_BAISSIERE"
        # -------------------------------------------------------------------
        # Détection d'une compression/range avec volatilité locale.
        # -------------------------------------------------------------------
        recent_range = (
            max(highs) - min(lows)
        )
        average_range = (
            self._average_candle_range(
                recent
            )
        )
        if (
            average_range is not None
            and average_range > 0
            and recent_range
            <= average_range
            * RANGE_WIDTH_ATR_MULTIPLIER
        ):
            return "RANGE"
        return "TRANSITION"
    # -----------------------------------------------------------------------
    # FORCE DU CONTEXTE
    # -----------------------------------------------------------------------
    def _calculate_strength(
        self,
        candles: List[Candle],
        direction: str,
        structure: str,
        timeframe: str,
    ) -> float:
        score = 0.0
        if direction in (
            "HAUSSIER",
            "BAISSIER",
        ):
            score += 40.0
        if structure in (
            "STRUCTURE_HAUSSIERE",
            "STRUCTURE_BAISSIERE",
        ):
            score += 35.0
        elif structure == "RANGE":
            score += 15.0
        elif structure == "TRANSITION":
            score += 10.0
        momentum = self._calculate_momentum(
            candles
        )
        score += min(
            momentum * 25.0,
            25.0,
        )
        # Les petits timeframes sont légèrement
        # moins stables comme contexte global.
        if timeframe in (
            "M5",
            "M1",
        ):
            score *= 0.90
        return min(
            score,
            100.0,
        )
    # -----------------------------------------------------------------------
    # MOMENTUM DESCRIPTIF
    # -----------------------------------------------------------------------
    @staticmethod
    def _calculate_momentum(
        candles: List[Candle],
    ) -> float:
        if len(candles) < 5:
            return 0.0
        recent = candles[-5:]
        bullish = 0
        bearish = 0
        for candle in recent:
            open_price = float(
                candle.open
            )
            close_price = float(
                candle.close
            )
            if close_price > open_price:
                bullish += 1
            elif close_price < open_price:
                bearish += 1
        return abs(
            bullish - bearish
        ) / 5.0
    # -----------------------------------------------------------------------
    # CONTEXTE AUTOUR DES ZONES
    # -----------------------------------------------------------------------
    def _analyser_zone_context(
        self,
        candles_by_timeframe: Dict[str, List[Candle]],
        zones_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not zones_result:
            return {
                "available": False,
                "zones": [],
            }
        zones = zones_result.get(
            "zones",
            [],
        )
        if not isinstance(
            zones,
            list,
        ):
            zones = []
        if not zones:
            return {
                "available": True,
                "zones": [],
            }
        output: List[Dict[str, Any]] = []
        for zone in zones:
            if not isinstance(zone, dict):
                continue
            center = self._safe_float(
                zone.get("center")
            )
            if (
                center is None
                or center <= 0
            ):
                continue
            timeframe = str(
                zone.get(
                    "timeframe",
                    "",
                )
            ).upper()
            if timeframe not in SUPPORTED_TIMEFRAMES:
                continue
            candles = candles_by_timeframe.get(
                timeframe,
                [],
            )
            behavior = (
                self._analyser_price_around_zone(
                    candles=candles,
                    zone_price=center,
                    timeframe=timeframe,
                )
            )
            item = dict(zone)
            item["price_behavior"] = behavior
            output.append(item)
        return {
            "available": True,
            "zones": output,
        }
    # -----------------------------------------------------------------------
    # COMPORTEMENT AUTOUR D'UNE ZONE
    # -----------------------------------------------------------------------
    def _analyser_price_around_zone(
        self,
        candles: List[Candle],
        zone_price: float,
        timeframe: str,
    ) -> Dict[str, Any]:
        cleaned = self._clean_candles(
            candles
        )
        if not cleaned:
            return {
                "state": "INCONNU",
                "reaction": "AUCUNE_DONNEE",
                "touches": 0,
                "bullish_reactions": 0,
                "bearish_reactions": 0,
            }
        recent = cleaned[-10:]
        average_range = (
            self._average_candle_range(
                recent
            )
        )
        if (
            average_range is None
            or average_range <= 0
        ):
            return {
                "state": "INCONNU",
                "reaction": "VOLATILITE_INDISPONIBLE",
                "touches": 0,
                "bullish_reactions": 0,
                "bearish_reactions": 0,
            }
        tolerance = (
            average_range
            * ZONE_REACTION_ATR_MULTIPLIER.get(
                timeframe,
                1.20,
            )
        )
        touches = 0
        bullish_reactions = 0
        bearish_reactions = 0
        for candle in recent:
            high = float(
                candle.high
            )
            low = float(
                candle.low
            )
            close = float(
                candle.close
            )
            open_price = float(
                candle.open
            )
            if (
                low - tolerance
                <= zone_price
                <= high + tolerance
            ):
                touches += 1
                if close > open_price:
                    bullish_reactions += 1
                elif close < open_price:
                    bearish_reactions += 1
        if touches == 0:
            state = "HORS_ZONE"
            reaction = "AUCUNE"
        elif bullish_reactions > bearish_reactions:
            state = "REACTION_HAUSSIERE"
            reaction = "HAUSSIERE"
        elif bearish_reactions > bullish_reactions:
            state = "REACTION_BAISSIERE"
            reaction = "BAISSIERE"
        else:
            state = "ZONE_TESTEE"
            reaction = "NEUTRE"
        return {
            "state": state,
            "reaction": reaction,
            "touches": touches,
            "bullish_reactions": bullish_reactions,
            "bearish_reactions": bearish_reactions,
            "tolerance": round(
                tolerance,
                8,
            ),
        }
    # -----------------------------------------------------------------------
    # CONTEXTE GLOBAL
    # -----------------------------------------------------------------------
    def _determine_global_context(
        self,
        contexts: Dict[str, Dict[str, Any]],
    ) -> GlobalContext:
        if not contexts:
            return GlobalContext(
                direction="NEUTRE",
                state="DONNEES_INSUFFISANTES",
                strength=0.0,
                dominant_timeframe="NONE",
                alignment="NONE",
                reason="Aucun timeframe disponible.",
            )
        # H4 / H1 / M15 constituent le contexte principal.
        h4 = contexts.get("H4")
        h1 = contexts.get("H1")
        m15 = contexts.get("M15")
        main_contexts = [
            context
            for context in (
                h4,
                h1,
                m15,
            )
            if context is not None
        ]
        # -------------------------------------------------------------------
        # Vote directionnel pondéré.
        #
        # H4 possède la priorité maximale.
        # H1 puis M15.
        # M5/M1 ne participent pas à cette direction globale.
        # -------------------------------------------------------------------
        directional_votes = {
            "HAUSSIER": 0.0,
            "BAISSIER": 0.0,
        }
        for timeframe, context in (
            ("H4", h4),
            ("H1", h1),
            ("M15", m15),
        ):
            if context is None:
                continue
            direction = context.get(
                "direction"
            )
            strength = self._safe_float(
                context.get(
                    "strength",
                    0,
                )
            ) or 0.0
            priority = (
                TIMEFRAME_PRIORITY.get(
                    timeframe,
                    0,
                )
            )
            if direction in directional_votes:
                directional_votes[
                    direction
                ] += (
                    strength
                    * (priority + 1)
                )
        bullish = directional_votes[
            "HAUSSIER"
        ]
        bearish = directional_votes[
            "BAISSIER"
        ]
        if bullish > bearish:
            direction = "HAUSSIER"
        elif bearish > bullish:
            direction = "BAISSIER"
        else:
            direction = "NEUTRE"
        # -------------------------------------------------------------------
        # H4 reste l'ancrage principal lorsqu'il est directionnel.
        # -------------------------------------------------------------------
        if h4:
            h4_direction = h4.get(
                "direction"
            )
            if h4_direction in (
                "HAUSSIER",
                "BAISSIER",
            ):
                direction = h4_direction
        # -------------------------------------------------------------------
        # Alignement H4 / H1 / M15.
        # -------------------------------------------------------------------
        directional_contexts = [
            context
            for context in main_contexts
            if context.get("direction")
            in (
                "HAUSSIER",
                "BAISSIER",
            )
        ]
        if not directional_contexts:
            alignment = "NON_DEFINI"
        elif len(directional_contexts) == 3 and all(
            context.get("direction")
            == direction
            for context in directional_contexts
        ):
            alignment = "COHERENT"
        elif all(
            context.get("direction")
            == direction
            for context in directional_contexts
        ):
            alignment = "PARTIEL_COHERENT"
        else:
            alignment = "MIXTE"
        # -------------------------------------------------------------------
        # État global descriptif.
        # -------------------------------------------------------------------
        if direction == "NEUTRE":
            state = "NEUTRE"
        elif alignment == "COHERENT":
            if direction == "HAUSSIER":
                state = "TENDANCE_HAUSSIERE"
            else:
                state = "TENDANCE_BAISSIERE"
        elif alignment == "MIXTE":
            state = "TRANSITION"
        else:
            state = "CONTEXTE_DIRECTIONNEL"
        strengths = [
            self._safe_float(
                context.get(
                    "strength",
                    0,
                )
            ) or 0.0
            for context in main_contexts
        ]
        average_strength = (
            sum(strengths)
            / len(strengths)
            if strengths
            else 0.0
        )
        dominant_timeframe = (
            self._dominant_timeframe(
                contexts=contexts,
                direction=direction,
            )
        )
        reason = self._build_global_reason(
            direction=direction,
            state=state,
            alignment=alignment,
        )
        return GlobalContext(
            direction=direction,
            state=state,
            strength=round(
                average_strength,
                2,
            ),
            dominant_timeframe=dominant_timeframe,
            alignment=alignment,
            reason=reason,
        )
    # -----------------------------------------------------------------------
    # TIMEFRAME DOMINANT
    # -----------------------------------------------------------------------
    @staticmethod
    def _dominant_timeframe(
        contexts: Dict[str, Dict[str, Any]],
        direction: str,
    ) -> str:
        candidates = []
        for timeframe, context in contexts.items():
            if context.get(
                "direction"
            ) != direction:
                continue
            strength = (
                Moteur2Contexte._safe_float(
                    context.get(
                        "strength",
                        0,
                    )
                )
                or 0.0
            )
            candidates.append(
                (
                    TIMEFRAME_PRIORITY.get(
                        timeframe,
                        0,
                    ),
                    strength,
                    timeframe,
                )
            )
        if not candidates:
            return "NONE"
        candidates.sort(
            reverse=True
        )
        return candidates[0][2]
    # -----------------------------------------------------------------------
    # RAISONS
    # -----------------------------------------------------------------------
    @staticmethod
    def _build_reason(
        direction: str,
        structure: str,
    ) -> str:
        if direction == "HAUSSIER":
            direction_text = (
                "pression acheteuse"
            )
        elif direction == "BAISSIER":
            direction_text = (
                "pression vendeuse"
            )
        else:
            direction_text = (
                "absence de direction claire"
            )
        return (
            f"{direction_text}; "
            f"structure={structure}"
        )
    @staticmethod
    def _build_global_reason(
        direction: str,
        state: str,
        alignment: str,
    ) -> str:
        return (
            f"direction={direction}; "
            f"état={state}; "
            f"alignement={alignment}"
        )
    # -----------------------------------------------------------------------
    # VOLATILITÉ
    # -----------------------------------------------------------------------
    @staticmethod
    def _average_candle_range(
        candles: List[Candle],
    ) -> Optional[float]:
        if not candles:
            return None
        ranges: List[float] = []
        for candle in candles:
            try:
                high = float(
                    candle.high
                )
                low = float(
                    candle.low
                )
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue
            if (
                high > 0
                and low > 0
                and high >= low
            ):
                candle_range = (
                    high - low
                )
                if candle_range > 0:
                    ranges.append(
                        candle_range
                    )
        if not ranges:
            return None
        return (
            sum(ranges)
            / len(ranges)
        )
    # -----------------------------------------------------------------------
    # OUTILS
    # -----------------------------------------------------------------------
    @staticmethod
    def _is_increasing(
        values: List[float],
    ) -> bool:
        if len(values) < 2:
            return False
        changes = sum(
            values[i] > values[i - 1]
            for i in range(
                1,
                len(values),
            )
        )
        return changes >= (
            len(values) - 2
        )
    @staticmethod
    def _is_decreasing(
        values: List[float],
    ) -> bool:
        if len(values) < 2:
            return False
        changes = sum(
            values[i] < values[i - 1]
            for i in range(
                1,
                len(values),
            )
        )
        return changes >= (
            len(values) - 2
        )
    @staticmethod
    def _clean_candles(
        candles: List[Candle],
    ) -> List[Candle]:
        output: List[Candle] = []
        for candle in candles:
            try:
                open_price = float(
                    candle.open
                )
                high = float(
                    candle.high
                )
                low = float(
                    candle.low
                )
                close = float(
                    candle.close
                )
                if (
                    open_price > 0
                    and high > 0
                    and low > 0
                    and close > 0
                    and high >= low
                    and high >= open_price
                    and high >= close
                    and low <= open_price
                    and low <= close
                ):
                    output.append(
                        candle
                    )
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue
        return output
    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None
# ---------------------------------------------------------------------------
# FONCTION SIMPLE
# ---------------------------------------------------------------------------
def analyser_contexte(
    candles_by_timeframe: Dict[str, List[Candle]],
    zones_result: Optional[Dict[str, Any]] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fonction pratique pour analyser le contexte.
    """
    moteur = Moteur2Contexte()
    return moteur.analyser(
        candles_by_timeframe=candles_by_timeframe,
        zones_result=zones_result,
        symbol=symbol,
    )