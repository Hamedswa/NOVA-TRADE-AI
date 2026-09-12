"""
NOVA TRADE AI — ENGINE 2
moteur2.py

Orchestrateur corrigé.

XAUUSD uniquement.
Source marché : BiQuote uniquement.

Pipeline :
BiQuote → Cache → Cartographie → Zones → Contexte →
Confluences → Setups → Risk → Confirmation M5/M1 →
Score → Validation → Anti-spam → Signal.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional

from biquote_client import BiQuoteClient
from biquote_stream import BiQuoteStream
from moteur2_cache import Moteur2Cache
from moteur2_marche import Moteur2Marche
from moteur2_zones import Moteur2Zones
from moteur2_contexte import Moteur2Contexte
from moteur2_confluences import Moteur2Confluences
from moteur2_setups import Moteur2Setups
from moteur2_risk import Moteur2Risk
from moteur2_confirmation import Moteur2Confirmation
from moteur2_score import Moteur2Score
from moteur2_validation import Moteur2Validation
from moteur2_antispam import Moteur2AntiSpam
from moteur2_signal import Moteur2Signal


SYMBOL = "XAUUSD"

# Les quatre actifs surveillés en permanence par Engine 2.
# L'ordre est volontaire : XAUUSD, BTCUSD, EURUSD, GBPUSD.
SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

# Objectif opérationnel : rechercher activement les meilleures
# opportunités de la journée. Ce nombre n'est PAS un quota forcé.
DAILY_SIGNAL_TARGET = 3
MAX_SIGNALS_PER_CYCLE = 3

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)

ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"

logger = logging.getLogger("NOVA_ENGINE_2")


class Moteur2:

    def __init__(self, symbol: str = SYMBOL) -> None:

        self.symbol = (
            symbol.strip().upper().replace("/", "")
        )

        if self.symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(
                f"Engine 2 ne supporte pas {self.symbol}. "
                f"Symboles supportés : {', '.join(SUPPORTED_SYMBOLS)}."
            )

        self.biquote = BiQuoteClient()

        self.stream = BiQuoteStream(
            symbol=self.symbol,
            on_tick=self._on_tick,
        )

        self.cache = Moteur2Cache(
            client=self.biquote,
            symbol=self.symbol,
        )

        self.marche = Moteur2Marche()
        self.zones = Moteur2Zones()
        self.contexte = Moteur2Contexte()
        self.confluences = Moteur2Confluences()
        self.setups = Moteur2Setups()
        self.risk = Moteur2Risk()
        self.confirmation = Moteur2Confirmation()
        self.score = Moteur2Score()
        self.validation = Moteur2Validation()
        self.antispam = Moteur2AntiSpam()
        self.signal = Moteur2Signal()

        self.running = False
        self.initialized = False
        self.latest_tick: Optional[Any] = None
        self.last_analysis: Optional[Dict[str, Any]] = None

        self.analysis_lock = asyncio.Lock()

    # ============================================================
    # OUTILS
    # ============================================================

    @staticmethod
    def _get(
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if data is None:
            return default
        if isinstance(data, dict):
            return data.get(key, default)
        return getattr(data, key, default)

    @staticmethod
    async def _call(
        function: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:

        result = function(*args, **kwargs)

        if inspect.isawaitable(result):
            return await result

        return result

    # ============================================================
    # TICK LIVE
    # ============================================================

    async def _on_tick(self, tick: Any) -> None:

        self.latest_tick = tick

        try:
            await self._call(
                self.cache.update_tick,
                tick,
            )
        except Exception as exc:
            logger.exception(
                "Erreur mise à jour tick BiQuote : %s",
                exc,
            )

    # ============================================================
    # INITIALISATION
    # ============================================================

    async def initialiser(self) -> Dict[str, Any]:

        try:

            await self._call(
                self.cache.refresh_all
            )

            self.initialized = True

            return {
                "success": True,
                "symbol": self.symbol,
                "timeframes": list(TIMEFRAMES),
                "source": "BiQuote",
            }

        except Exception as exc:

            self.initialized = False

            logger.exception(
                "Échec initialisation Engine 2."
            )

            return {
                "success": False,
                "symbol": self.symbol,
                "error": str(exc),
            }

    async def rafraichir_cache(self) -> Any:
        return await self._call(
            self.cache.refresh_all
        )

    # ============================================================
    # DONNÉES
    # ============================================================

    def obtenir_donnees(self) -> Dict[str, Any]:

        donnees: Dict[str, Any] = {}

        for timeframe in TIMEFRAMES:

            try:
                donnees[timeframe] = (
                    self.cache.get_closed_candles(
                        timeframe
                    )
                )

            except TypeError:
                donnees[timeframe] = (
                    self.cache.get_closed_candles(
                        timeframe=timeframe
                    )
                )

        return donnees

    # ============================================================
    # CARTOGRAPHIE
    # ============================================================

    async def analyser_marche(
        self,
        donnees: Dict[str, Any],
    ) -> Any:

        return await self._call(
            self.marche.cartographier_marche,
            donnees,
        )

    # ============================================================
    # ZONES
    # ============================================================

    async def analyser_zones(
        self,
        cartographie: Any,
        current_price: float,
    ) -> Any:

        # IMPORTANT : méthode réelle de la classe = analyser()
        return await self._call(
            self.zones.analyser,
            cartographie,
            current_price,
        )

    # ============================================================
    # CONTEXTE
    # ============================================================

    async def analyser_contexte(
        self,
        donnees: Dict[str, Any],
        zones: Any,
    ) -> Any:

        # Signature réelle :
        # analyser(candles_by_timeframe, zones_result)
        return await self._call(
            self.contexte.analyser,
            donnees,
            zones,
        )

    # ============================================================
    # CONFLUENCES
    # ============================================================

    async def analyser_confluences(
        self,
        donnees: Dict[str, Any],
        zones: Any,
        contexte: Any,
        cartographie: Any,
    ) -> Any:

        # Signature réelle :
        # analyser(candles, zones, context, market_map)
        return await self._call(
            self.confluences.analyser,
            donnees,
            zones,
            contexte,
            cartographie,
        )

    # ============================================================
    # SETUPS
    # ============================================================

    async def analyser_setups(
        self,
        zones: Any,
        confluences: Any,
        contexte: Any,
        donnees: Dict[str, Any],
    ) -> Any:

        return await self._call(
            self.setups.analyser,
            zones,
            confluences,
            contexte,
            donnees,
        )

    # ============================================================
    # RISK
    # ============================================================

    async def analyser_risque(
        self,
        setups: Any,
        zones: Any,
        donnees: Dict[str, Any],
        current_price: float,
    ) -> Any:

        # Signature réelle :
        # analyser_setups(setups, zones, candles, current_price)
        return await self._call(
            self.risk.analyser_setups,
            setups,
            zones,
            donnees,
            current_price,
        )

    # ============================================================
    # CONFIRMATION
    # ============================================================

    async def analyser_confirmation(
        self,
        setup: Any,
        donnees: Dict[str, Any],
        risk_plan: Any,
    ) -> Any:

        # Signature réelle :
        # analyser(setup, candles, risk_plan)
        return await self._call(
            self.confirmation.analyser,
            setup,
            donnees,
            risk_plan,
        )

    # ============================================================
    # SCORE
    # ============================================================

    async def calculer_score(
        self,
        setup: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        confirmation: Any,
        risk_plan: Any,
    ) -> Any:

        # Signature réelle :
        # analyser(setup, zones, context, confluences,
        #          confirmation, risk_plan)
        return await self._call(
            self.score.analyser,
            setup=setup,
            zones=zones,
            context=contexte,
            confluences=confluences,
            confirmation=confirmation,
            risk_plan=risk_plan,
        )

    # ============================================================
    # VALIDATION
    # ============================================================

    async def valider(
        self,
        setup: Any,
        risk_plan: Any,
        confirmation: Any,
        score_result: Any,
        contexte: Any,
        confluences: Any,
    ) -> Any:

        return await self._call(
            self.validation.valider,
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            contexte=contexte,
            confluences=confluences,
        )

    # ============================================================
    # SETUP COMPLET
    # ============================================================

    async def traiter_setup(
        self,
        setup: Any,
        risk_plan: Any,
        zones: Any,
        contexte: Any,
        confluences: Any,
        donnees: Dict[str, Any],
    ) -> Dict[str, Any]:

        confirmation = await self.analyser_confirmation(
            setup,
            donnees,
            risk_plan,
        )

        score_result = await self.calculer_score(
            setup=setup,
            zones=zones,
            contexte=contexte,
            confluences=confluences,
            confirmation=confirmation,
            risk_plan=risk_plan,
        )

        validation = await self.valider(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            contexte=contexte,
            confluences=confluences,
        )

        validated = bool(
            self._get(
                validation,
                "validated",
                False,
            )
        )

        validation_status = str(
            self._get(
                validation,
                "status",
                "UNKNOWN",
            )
        ).upper()

        # --------------------------------------------------------
        # SETUP NON VALIDÉ
        # --------------------------------------------------------

        if not validated:

            return {
                "status": "REJECTED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
            }

        # --------------------------------------------------------
        # SETUP VALIDÉ MAIS M5/M1 EN ATTENTE
        #
        # IMPORTANT :
        # aucun anti-spam, aucun enregistrement actif,
        # aucun signal Telegram envoyé à ce stade.
        # --------------------------------------------------------

        if validation_status != "READY_FOR_SIGNAL":

            return {
                "status": "WAITING_CONFIRMATION",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "signal": None,
            }

        # --------------------------------------------------------
        # ANTI-SPAM UNIQUEMENT AU MOMENT DU SIGNAL
        # --------------------------------------------------------

        antispam = self.antispam.verifier(
            setup=setup,
            risk_plan=risk_plan,
            validation=validation,
        )

        if not bool(
            self._get(
                antispam,
                "allowed",
                False,
            )
        ):

            return {
                "status": "ANTISPAM_BLOCKED",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "antispam": antispam,
                "signal": None,
            }

        # --------------------------------------------------------
        # CONSTRUCTION SIGNAL
        # --------------------------------------------------------

        setup_id = self._get(
            antispam,
            "setup_id",
        )

        signal = self.signal.construire_signal(
            setup=setup,
            risk_plan=risk_plan,
            confirmation=confirmation,
            score_result=score_result,
            validation=validation,
            antispam_result=antispam,
            setup_id=setup_id,
        )

        if signal is None:

            return {
                "status": "SIGNAL_NOT_BUILT",
                "setup": setup,
                "risk": risk_plan,
                "confirmation": confirmation,
                "score": score_result,
                "validation": validation,
                "antispam": antispam,
                "signal": None,
            }

        # --------------------------------------------------------
        # ENREGISTREMENT APRÈS CONSTRUCTION DU SIGNAL
        # --------------------------------------------------------

        self.antispam.enregistrer_signal(
            setup=setup,
            risk_plan=risk_plan,
            setup_id=setup_id,
        )

        return {
            "status": "SIGNAL_READY",
            "signal": signal,
            "setup": setup,
            "risk": risk_plan,
            "confirmation": confirmation,
            "score": score_result,
            "validation": validation,
            "antispam": antispam,
        }

    # ============================================================
    # ANALYSE COMPLÈTE
    # ============================================================

    async def analyser(self) -> Dict[str, Any]:

        async with self.analysis_lock:

            await self.rafraichir_cache()

            # Le cache est déjà lié à self.symbol. On tente néanmoins
            # la forme explicite si une implémentation multi-symboles
            # de Moteur2Cache l'accepte, avec fallback rétrocompatible.
            try:
                current_price = self.cache.get_current_price(self.symbol)
            except TypeError:
                current_price = self.cache.get_current_price()

            if current_price is None:

                return {
                    "status": "NO_PRICE",
                    "reason": (
                        "Aucun prix live BiQuote disponible."
                    ),
                }

            donnees = self.obtenir_donnees()

            missing = [
                tf
                for tf in TIMEFRAMES
                if not donnees.get(tf)
            ]

            if missing:

                return {
                    "status": "INSUFFICIENT_DATA",
                    "missing_timeframes": missing,
                }

            cartographie = await self.analyser_marche(
                donnees
            )

            zones = await self.analyser_zones(
                cartographie,
                current_price,
            )

            contexte = await self.analyser_contexte(
                donnees,
                zones,
            )

            confluences = await self.analyser_confluences(
                donnees,
                zones,
                contexte,
                cartographie,
            )

            setups_result = await self.analyser_setups(
                zones,
                confluences,
                contexte,
                donnees,
            )

            if isinstance(setups_result, dict):
                setups = (
                    setups_result.get("setups")
                    or setups_result.get("detected_setups")
                    or []
                )
            elif isinstance(setups_result, (list, tuple)):
                setups = list(setups_result)
            else:
                setups = (
                    [setups_result]
                    if setups_result is not None
                    else []
                )

            if not setups:

                result = {
                    "status": "NO_SETUP",
                    "symbol": self.symbol,
                    "current_price": current_price,
                    "cartographie": cartographie,
                    "zones": zones,
                    "contexte": contexte,
                    "confluences": confluences,
                    "setups": [],
                    "results": [],
                    "signals": [],
                }

                self.last_analysis = result
                return result

            risk_result = await self.analyser_risque(
                setups,
                zones,
                donnees,
                current_price,
            )

            if isinstance(risk_result, dict):
                risk_plans = (
                    risk_result.get("plans")
                    or risk_result.get("risk_plans")
                    or risk_result.get("valid_plans")
                    or []
                )
            elif isinstance(risk_result, (list, tuple)):
                risk_plans = list(risk_result)
            else:
                risk_plans = []

            results = []

            for index, setup in enumerate(setups):

                setup_id = self._get(
                    setup,
                    "setup_id",
                )

                risk_plan = None

                if setup_id:

                    for candidate in risk_plans:

                        candidate_id = self._get(
                            candidate,
                            "setup_id",
                        )

                        if (
                            candidate_id
                            and candidate_id == setup_id
                        ):
                            risk_plan = candidate
                            break

                if risk_plan is None and index < len(risk_plans):
                    risk_plan = risk_plans[index]

                if risk_plan is None:

                    results.append({
                        "status": "NO_RISK_PLAN",
                        "setup": setup,
                    })

                    continue

                results.append(
                    await self.traiter_setup(
                        setup=setup,
                        risk_plan=risk_plan,
                        zones=zones,
                        contexte=contexte,
                        confluences=confluences,
                        donnees=donnees,
                    )
                )

            ready = [
                item
                for item in results
                if item.get("status") == "SIGNAL_READY"
            ]

            waiting = [
                item
                for item in results
                if item.get("status") == "WAITING_CONFIRMATION"
            ]

            if ready:
                overall_status = "SIGNAL_READY"
            elif waiting:
                overall_status = "WAITING_CONFIRMATION"
            else:
                overall_status = "ANALYZED"

            result = {
                "status": overall_status,
                "symbol": self.symbol,
                "current_price": current_price,
                "cartographie": cartographie,
                "zones": zones,
                "contexte": contexte,
                "confluences": confluences,
                "setups": setups,
                "risk": risk_result,
                "results": results,
                "signals": [
                    item["signal"]
                    for item in ready
                    if item.get("signal") is not None
                ],
            }

            self.last_analysis = result

            logger.info(
                "Engine 2 terminé : %s",
                overall_status,
            )

            return result

    # ============================================================
    # STREAM
    # ============================================================

    async def demarrer_stream(self) -> None:
        await self._call(
            self.stream.start
        )

    # ============================================================
    # RUN
    # ============================================================

    async def run(
        self,
        analyse_interval_seconds: int = 10,
    ) -> None:

        if not self.initialized:

            init = await self.initialiser()

            if not init["success"]:
                raise RuntimeError(
                    "Impossible d'initialiser Engine 2."
                )

        self.running = True

        stream_task = asyncio.create_task(
            self.demarrer_stream()
        )

        try:

            while self.running:

                try:
                    await self.analyser()
                except Exception as exc:
                    logger.exception(
                        "Erreur analyse Engine 2 : %s",
                        exc,
                    )

                await asyncio.sleep(
                    max(
                        1,
                        int(analyse_interval_seconds),
                    )
                )

        finally:

            self.running = False

            stream_task.cancel()

            try:
                await stream_task
            except asyncio.CancelledError:
                pass

    # ============================================================
    # STOP
    # ============================================================

    async def stop(self) -> None:

        self.running = False

        try:

            result = self.stream.stop()

            if inspect.isawaitable(result):
                await result

        except Exception as exc:

            logger.warning(
                "Erreur arrêt stream : %s",
                exc,
            )

    # ============================================================
    # STATUS
    # ============================================================

    def _cache_accepts_symbol_price(self) -> bool:
        """Détecte si get_current_price accepte un symbole explicite."""
        try:
            import inspect as _inspect
            signature = _inspect.signature(self.cache.get_current_price)
            parameters = list(signature.parameters.values())
            return any(
                p.kind in (_inspect.Parameter.POSITIONAL_ONLY,
                           _inspect.Parameter.POSITIONAL_OR_KEYWORD,
                           _inspect.Parameter.VAR_POSITIONAL)
                for p in parameters
            )
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:

        try:
            cache_status = self.cache.get_status()
        except Exception:
            cache_status = {}

        try:
            antispam_status = self.antispam.get_status()
        except Exception:
            antispam_status = {}

        return {
            "engine": ENGINE_NAME,
            "symbol": self.symbol,
            "source": "BiQuote",
            "running": self.running,
            "initialized": self.initialized,
            "current_price": (
                self.cache.get_current_price(self.symbol)
                if self._cache_accepts_symbol_price()
                else self.cache.get_current_price()
            ),
            "timeframes": list(TIMEFRAMES),
            "cache": cache_status,
            "antispam": antispam_status,
        }


async def analyser_xauusd() -> Dict[str, Any]:

    moteur = Moteur2()

    try:

        init = await moteur.initialiser()

        if not init["success"]:
            return init

        return await moteur.analyser()

    finally:
        await moteur.stop()


async def main() -> None:

    moteur = Moteur2()

    try:

        init = await moteur.initialiser()

        print(init)

        if not init["success"]:
            return

        result = await moteur.analyser()

        print(result)

    finally:

        await moteur.stop()


# ============================================================================
# NOVA ENGINE 2 — ORCHESTRATEUR GLOBAL MULTI-ACTIFS
# ============================================================================

class Moteur2Global:
    """Orchestrateur global multi-actifs d'Engine 2."""

    def __init__(self, symbols=None, max_signals: int = 3, parallel: bool = True,
                 analysis_interval_seconds: int = 900) -> None:
        from moteur2_multi_actifs import Moteur2MultiActifs
        from moteur2_ranking import Moteur2Ranking

        if symbols is None:
            symbols = list(SUPPORTED_SYMBOLS)

        self.symbols = tuple(
            str(symbol).strip().upper().replace('/', '').replace(' ', '')
            .replace('-', '').replace('_', '')
            for symbol in symbols
        )
        invalid = [s for s in self.symbols if s not in SUPPORTED_SYMBOLS]
        if invalid:
            raise ValueError(f"Symboles non supportés : {', '.join(invalid)}")

        self.max_signals = min(
            MAX_SIGNALS_PER_CYCLE,
            max(1, int(max_signals)),
        )
        self.parallel = bool(parallel)
        self.analysis_interval_seconds = max(1, int(analysis_interval_seconds))
        self.multi_actifs = Moteur2MultiActifs(
            symbols=self.symbols,
            analysis_interval_seconds=self.analysis_interval_seconds,
            parallel=self.parallel,
        )
        self.ranking = Moteur2Ranking(max_signals=self.max_signals)
        self.initialized = False
        self.running = False
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.last_ranking: Optional[Dict[str, Any]] = None
        self.analysis_lock = asyncio.Lock()

    async def initialiser(self) -> Dict[str, Any]:
        try:
            result = await self.multi_actifs.initialiser()
            initialized_symbols = result.get('initialized_symbols', [])
            self.initialized = bool(initialized_symbols)
            return {
                'success': self.initialized,
                'engine': ENGINE_NAME,
                'module': 'moteur2_global',
                'symbols': list(self.symbols),
                'initialized_symbols': initialized_symbols,
                'failed_symbols': result.get('failed_symbols', []),
                'max_signals': self.max_signals,
                'analysis_interval_seconds': self.analysis_interval_seconds,
                'forced_signal': False,
                'ranking_is_decision_maker': False,
                'quality_is_blocking': False,
                'results': result.get('results', {}),
            }
        except Exception as exc:
            logger.exception('Erreur initialisation Engine 2 Global : %s', exc)
            self.initialized = False
            return {'success': False, 'engine': ENGINE_NAME,
                    'module': 'moteur2_global', 'symbols': list(self.symbols),
                    'error': str(exc)}

    async def demarrer_streams(self) -> Dict[str, Any]:
        try:
            return await self.multi_actifs.demarrer_streams()
        except Exception as exc:
            logger.exception('Erreur démarrage streams globaux : %s', exc)
            return {'success': False, 'error': str(exc)}

    async def analyser(self) -> Dict[str, Any]:
        async with self.analysis_lock:
            if not self.initialized:
                init = await self.initialiser()
                if not init.get('success', False):
                    return {'status': 'INITIALIZATION_ERROR', 'engine': ENGINE_NAME,
                            'signals': [], 'error': init.get('error', 'Initialisation impossible.')}
            try:
                cycle = await self.multi_actifs.analyser_tous()
                self.last_cycle = cycle
                ranking = self.ranking.ranker(cycle)
                self.last_ranking = ranking
                signals = ranking.get('signals', [])
                return {
                    'status': 'SIGNALS_AVAILABLE' if signals else 'NO_GLOBAL_SIGNAL',
                    'engine': ENGINE_NAME,
                    'module': 'moteur2_global',
                    'symbols': list(self.symbols),
                    'max_signals': self.max_signals,
                    'daily_signal_target': DAILY_SIGNAL_TARGET,
                    'signals': signals,
                    'signal_count': len(signals),
                    'candidates_count': ranking.get('candidate_count', 0),
                    'selected_count': ranking.get('selected_count', 0),
                    'cycle': cycle,
                    'ranking': ranking,
                    'forced_signal': False,
                    'quality_is_blocking': False,
                    'ranking_is_decision_maker': False,
                    'auto_execution': False,
                    'decision_owner': 'moteur2_decision.py',
                    'risk_owner': 'moteur2_risk.py',
                    'validation_owner': 'moteur2_validation.py',
                    'ranking_owner': 'moteur2_ranking.py',
                }
            except Exception as exc:
                logger.exception('Erreur analyse Engine 2 Global : %s', exc)
                return {'status': 'GLOBAL_ENGINE_ERROR', 'engine': ENGINE_NAME,
                        'module': 'moteur2_global', 'signals': [], 'signal_count': 0,
                        'error': str(exc), 'forced_signal': False, 'auto_execution': False}

    async def analyser_symbol(self, symbol: str) -> Dict[str, Any]:
        """Analyse l'actif demandé via le moteur global multi-actifs.

        Cette méthode est une compatibilité pour l'interface Telegram :
        le moteur global analyse toujours le portefeuille des 4 actifs, puis
        retourne uniquement le résultat de l'actif demandé.
        Elle ne modifie ni la stratégie, ni le ranking, ni les critères de validation.
        """
        normalized = (
            str(symbol).strip().upper()
            .replace('/', '')
            .replace(' ', '')
            .replace('-', '')
            .replace('_', '')
        )

        if normalized not in self.symbols:
            return {
                'status': 'UNSUPPORTED_SYMBOL',
                'engine': ENGINE_NAME,
                'symbol': normalized,
                'signals': [],
                'error': f'Symbole non supporté : {normalized}',
            }

        global_result = await self.analyser()
        cycle = global_result.get('cycle') or self.last_cycle or {}
        results = cycle.get('results') or {}

        # Compatibilité avec les deux formes possibles de stockage.
        result = results.get(normalized)
        if result is None:
            for key, value in results.items():
                key_normalized = (
                    str(key).strip().upper()
                    .replace('/', '')
                    .replace(' ', '')
                    .replace('-', '')
                    .replace('_', '')
                )
                if key_normalized == normalized:
                    result = value
                    break

        if result is None:
            return {
                'status': 'SYMBOL_RESULT_UNAVAILABLE',
                'engine': ENGINE_NAME,
                'symbol': normalized,
                'signals': [],
                'global_status': global_result.get('status'),
                'error': f'Aucun résultat disponible pour {normalized}.',
            }

        return result

    def obtenir_top_signaux(self) -> List[Any]:
        if not self.last_ranking:
            return []
        return self.last_ranking.get('signals', [])

    def get_status(self) -> Dict[str, Any]:
        try:
            multi_status = self.multi_actifs.get_status()
        except Exception as exc:
            multi_status = {'status': 'ERROR', 'error': str(exc)}
        try:
            ranking_status = self.ranking.get_status()
        except Exception as exc:
            ranking_status = {'status': 'ERROR', 'error': str(exc)}
        return {
            'engine': ENGINE_NAME, 'module': 'moteur2_global',
            'symbols': list(self.symbols), 'symbol_count': len(self.symbols),
            'initialized': self.initialized, 'running': self.running,
            'max_signals': self.max_signals,
            'daily_signal_target': DAILY_SIGNAL_TARGET,
            'analysis_interval_seconds': self.analysis_interval_seconds,
            'forced_signal': False, 'quality_is_blocking': False,
            'ranking_is_decision_maker': False, 'auto_execution': False,
            'multi_actifs': multi_status, 'ranking': ranking_status,
            'last_signal_count': len(self.obtenir_top_signaux()),
        }

    async def run(self, analysis_interval_seconds: Optional[int] = None,
                  start_streams: bool = True) -> None:
        if not self.initialized:
            init = await self.initialiser()
            if not init.get('success', False):
                raise RuntimeError('Impossible d\'initialiser Engine 2 Global.')
        self.running = True
        interval = self.analysis_interval_seconds if analysis_interval_seconds is None else max(1, int(analysis_interval_seconds))
        stream_task = None
        try:
            if start_streams:
                stream_task = asyncio.create_task(self.demarrer_streams())
            while self.running:
                try:
                    await self.analyser()
                except Exception as exc:
                    logger.exception('Erreur cycle global : %s', exc)
                await asyncio.sleep(interval)
        finally:
            self.running = False
            if stream_task is not None:
                stream_task.cancel()
                try:
                    await stream_task
                except asyncio.CancelledError:
                    pass

    async def stop(self) -> None:
        self.running = False
        try:
            await self.multi_actifs.stop()
        except Exception as exc:
            logger.warning('Erreur arrêt Engine 2 Global : %s', exc)


# ============================================================================
# INSTANCE GLOBALE LAZY
# ============================================================================

_moteur2_global: Optional[Moteur2Global] = None


def obtenir_moteur2_global() -> Moteur2Global:
    global _moteur2_global
    if _moteur2_global is None:
        _moteur2_global = Moteur2Global(
            symbols=SUPPORTED_SYMBOLS,
            max_signals=3,
            parallel=True,
            analysis_interval_seconds=900,
        )
    return _moteur2_global


async def initialiser_engine2_global() -> Dict[str, Any]:
    return await obtenir_moteur2_global().initialiser()


async def demarrer_streams_engine2_global() -> Dict[str, Any]:
    return await obtenir_moteur2_global().demarrer_streams()


async def analyser_engine2_global() -> Dict[str, Any]:
    return await obtenir_moteur2_global().analyser()


async def arreter_engine2_global() -> None:
    await obtenir_moteur2_global().stop()


def statut_engine2_global() -> Dict[str, Any]:
    return obtenir_moteur2_global().get_status()


def top_signaux_engine2_global() -> List[Any]:
    return obtenir_moteur2_global().obtenir_top_signaux()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    asyncio.run(main())
