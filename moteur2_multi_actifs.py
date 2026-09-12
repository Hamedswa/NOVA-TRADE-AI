"""
NOVA TRADE AI — ENGINE 2
moteur2_multi_actifs.py
GESTIONNAIRE MULTI-ACTIFS

Rôle
----
Orchestrer plusieurs instances indépendantes de Moteur2.

Actifs surveillés :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD

Ce module :
    - initialise les 4 moteurs ;
    - démarre leurs streams ;
    - attend que les streams soient prêts ;
    - attend la disponibilité des prix ;
    - lance les analyses ;
    - récupère les résultats ;
    - rassemble les opportunités ;
    - prépare les résultats pour moteur2_ranking.py.

IMPORTANT
---------
Ce module ne décide PAS quel signal envoyer.

Il ne :
    - supprime aucun setup ;
    - modifie aucun score ;
    - modifie aucune décision ;
    - impose aucun quota ;
    - force aucun signal.

Le classement TOP 3 est effectué ensuite par :
    moteur2_ranking.py
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

from moteur2 import (
    Moteur2,
    SUPPORTED_SYMBOLS,
)


logger = logging.getLogger("NOVA_ENGINE_2_MULTI")


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

DEFAULT_ANALYSIS_INTERVAL = 900

# Sécurité contre une analyse individuelle qui resterait bloquée.
ANALYSIS_TIMEOUT_SECONDS = 120

# ---------------------------------------------------------------------------
# NOUVEAU : préparation du flux avant la première analyse
# ---------------------------------------------------------------------------

# Temps maximum pendant lequel le gestionnaire attend qu'un prix soit
# disponible après le démarrage des streams.
STREAM_READY_TIMEOUT_SECONDS = 30

# Fréquence de vérification de la disponibilité des prix.
STREAM_READY_CHECK_INTERVAL_SECONDS = 0.5

# Petite marge minimale après le lancement des streams.
# Elle laisse à SignalR/BiQuote le temps de commencer la négociation.
STREAM_STARTUP_GRACE_SECONDS = 1.0


# ============================================================================
# UTILITAIRES
# ============================================================================

def _normaliser_symbole(symbol: Any) -> str:
    """
    Normalise un symbole.

    Exemples :
        XAU/USD -> XAUUSD
        xauusd  -> XAUUSD
        BTC-USD -> BTCUSD
    """
    value = str(symbol or "").strip().upper()

    value = (
        value
        .replace("/", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )

    return value


def _get(
    data: Any,
    key: str,
    default: Any = None,
) -> Any:
    """
    Lecture compatible dict / objet.
    """
    if data is None:
        return default

    if isinstance(data, dict):
        return data.get(key, default)

    return getattr(data, key, default)


def _valeur_prix_valide(value: Any) -> bool:
    """
    Vérifie qu'une valeur peut réellement représenter un prix.
    """
    if value is None:
        return False

    if isinstance(value, bool):
        return False

    try:
        price = float(value)
    except (TypeError, ValueError):
        return False

    return price > 0


def _contient_prix(data: Any) -> bool:
    """
    Recherche récursivement un prix exploitable dans le statut
    retourné par le moteur.

    Cette fonction reste volontairement générique afin de ne pas
    dépendre d'une structure interne précise de Moteur2.
    """

    if data is None:
        return False

    # ------------------------------------------------------------------------
    # Dict
    # ------------------------------------------------------------------------
    if isinstance(data, dict):

        # Clés de prix courantes.
        price_keys = (
            "current_price",
            "currentPrice",
            "last_price",
            "lastPrice",
            "price",
            "bid",
            "ask",
            "close",
            "last",
            "mid",
            "current",
        )

        for key in price_keys:
            if key in data and _valeur_prix_valide(data[key]):
                return True

        # Recherche dans les structures imbriquées.
        for value in data.values():
            if isinstance(value, (dict, list, tuple)):
                if _contient_prix(value):
                    return True

        return False

    # ------------------------------------------------------------------------
    # Liste / tuple
    # ------------------------------------------------------------------------
    if isinstance(data, (list, tuple)):
        for value in data:
            if isinstance(value, (dict, list, tuple)):
                if _contient_prix(value):
                    return True

        return False

    # ------------------------------------------------------------------------
    # Objet
    # ------------------------------------------------------------------------
    for key in (
        "current_price",
        "currentPrice",
        "last_price",
        "lastPrice",
        "price",
        "bid",
        "ask",
        "close",
        "last",
        "mid",
        "current",
    ):
        try:
            value = getattr(data, key, None)
        except Exception:
            value = None

        if _valeur_prix_valide(value):
            return True

    return False


# ============================================================================
# MOTEUR MULTI-ACTIFS
# ============================================================================

class Moteur2MultiActifs:
    """
    Orchestrateur de plusieurs instances indépendantes de Moteur2.
    """

    def __init__(
        self,
        symbols: Optional[Sequence[str]] = None,
        *,
        analysis_interval_seconds: int = DEFAULT_ANALYSIS_INTERVAL,
        parallel: bool = True,
    ) -> None:

        requested_symbols = (
            symbols
            if symbols is not None
            else DEFAULT_SYMBOLS
        )

        self.symbols = self._valider_symboles(
            requested_symbols
        )

        self.analysis_interval_seconds = max(
            1,
            int(analysis_interval_seconds),
        )

        self.parallel = bool(parallel)

        self.moteurs: Dict[str, Moteur2] = {}

        self.initialized = False
        self.running = False

        self.last_results: Dict[str, Dict[str, Any]] = {}

        self.last_cycle: Optional[
            Dict[str, Any]
        ] = None

        self._cycle_lock = asyncio.Lock()

        # --------------------------------------------------------------------
        # Gestion interne des tâches streams.
        #
        # Cela évite de démarrer plusieurs fois le même stream.
        # --------------------------------------------------------------------
        self._stream_tasks: Dict[
            str,
            asyncio.Task,
        ] = {}

        self._streams_started = False

        # --------------------------------------------------------------------
        # Création des moteurs indépendants
        # --------------------------------------------------------------------

        for symbol in self.symbols:

            self.moteurs[symbol] = Moteur2(
                symbol=symbol
            )

        logger.info(
            "Multi-actifs créé : %s",
            ", ".join(self.symbols),
        )

    # =========================================================================
    # VALIDATION DES SYMBOLES
    # =========================================================================

    @staticmethod
    def _valider_symboles(
        symbols: Iterable[str],
    ) -> List[str]:

        result: List[str] = []

        for symbol in symbols:

            normalized = _normaliser_symbole(
                symbol
            )

            if not normalized:
                continue

            if normalized not in SUPPORTED_SYMBOLS:

                raise ValueError(
                    "Symbole non supporté par "
                    f"Engine 2 : {normalized}. "
                    f"Symboles disponibles : "
                    f"{', '.join(SUPPORTED_SYMBOLS)}"
                )

            if normalized not in result:
                result.append(normalized)

        if not result:

            raise ValueError(
                "Aucun actif valide fourni au "
                "gestionnaire multi-actifs."
            )

        return result

    # =========================================================================
    # INITIALISATION
    # =========================================================================

    async def initialiser(
        self,
    ) -> Dict[str, Any]:

        logger.info(
            "NOVA ENGINE 2 — INITIALISATION MULTI-ACTIFS"
        )

        logger.info(
            "Actifs à initialiser : %s",
            ", ".join(self.symbols),
        )

        results: Dict[str, Any] = {}

        if self.parallel:

            tasks = {
                symbol: asyncio.create_task(
                    self._initialiser_moteur(symbol)
                )
                for symbol in self.symbols
            }

            completed = await asyncio.gather(
                *tasks.values(),
                return_exceptions=True,
            )

            for symbol, result in zip(
                tasks.keys(),
                completed,
            ):

                if isinstance(
                    result,
                    Exception,
                ):

                    logger.error(
                        "Erreur initialisation %s : %s",
                        symbol,
                        result,
                    )

                    results[symbol] = {
                        "success": False,
                        "symbol": symbol,
                        "error": str(result),
                    }

                else:

                    results[symbol] = result

        else:

            for symbol in self.symbols:

                try:

                    results[symbol] = (
                        await self._initialiser_moteur(
                            symbol
                        )
                    )

                except Exception as exc:

                    logger.exception(
                        "Erreur initialisation %s",
                        symbol,
                    )

                    results[symbol] = {
                        "success": False,
                        "symbol": symbol,
                        "error": str(exc),
                    }

        successful = [
            symbol
            for symbol, result in results.items()
            if bool(
                _get(
                    result,
                    "success",
                    False,
                )
            )
        ]

        self.initialized = bool(
            successful
        )

        logger.info(
            "Initialisation terminée : %s/%s actifs prêts",
            len(successful),
            len(self.symbols),
        )

        return {
            "success": bool(successful),
            "engine": "NOVA TRADE AI - ENGINE 2",
            "module": "moteur2_multi_actifs",
            "symbols": list(self.symbols),
            "initialized_symbols": successful,
            "failed_symbols": [
                symbol
                for symbol in self.symbols
                if symbol not in successful
            ],
            "results": results,
        }

    async def _initialiser_moteur(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        logger.info(
            "Initialisation moteur individuel : %s",
            symbol,
        )

        started = time.monotonic()

        moteur = self.moteurs[symbol]

        result = await moteur.initialiser()

        elapsed = time.monotonic() - started

        logger.info(
            "Initialisation %s terminée en %.2fs",
            symbol,
            elapsed,
        )

        return result

    # =========================================================================
    # STREAMS
    # =========================================================================

    async def demarrer_streams(
        self,
    ) -> Dict[str, Any]:

        results: Dict[str, Any] = {}

        logger.info(
            "Démarrage des streams BiQuote multi-actifs..."
        )

        # ---------------------------------------------------------------------
        # Ne pas démarrer deux fois les streams.
        # ---------------------------------------------------------------------

        for symbol in self.symbols:

            existing_task = self._stream_tasks.get(
                symbol
            )

            if (
                existing_task is not None
                and not existing_task.done()
            ):

                logger.info(
                    "Stream déjà actif ou en démarrage : %s",
                    symbol,
                )

                results[symbol] = {
                    "success": True,
                    "symbol": symbol,
                    "already_started": True,
                }

                continue

            logger.info(
                "Création tâche stream : %s",
                symbol,
            )

            self._stream_tasks[symbol] = (
                asyncio.create_task(
                    self._stream_safe(
                        self.moteurs[symbol],
                        symbol,
                    )
                )
            )

            results[symbol] = {
                "success": True,
                "symbol": symbol,
                "already_started": False,
            }

        self._streams_started = True

        # ---------------------------------------------------------------------
        # Laisser SignalR/BiQuote démarrer sa négociation.
        # ---------------------------------------------------------------------

        logger.info(
            "Streams lancés. Attente du démarrage BiQuote..."
        )

        await asyncio.sleep(
            STREAM_STARTUP_GRACE_SECONDS
        )

        return results

    async def _demarrer_stream(
        self,
        symbol: str,
    ) -> None:

        logger.info(
            "Démarrage stream : %s",
            symbol,
        )

        moteur = self.moteurs[symbol]

        await moteur.demarrer_stream()

        logger.info(
            "Stream démarré : %s",
            symbol,
        )

    async def _stream_safe(
        self,
        moteur: Moteur2,
        symbol: str,
    ) -> None:

        try:

            logger.info(
                "Stream sécurisé démarrage : %s",
                symbol,
            )

            await moteur.demarrer_stream()

        except asyncio.CancelledError:

            raise

        except Exception as exc:

            logger.exception(
                "Stream %s arrêté avec erreur : %s",
                symbol,
                exc,
            )

    # =========================================================================
    # ATTENTE DU PRIX
    # =========================================================================

    async def attendre_prix(
        self,
    ) -> Dict[str, Any]:
        """
        Attend que les moteurs disposent d'au moins un prix exploitable.

        IMPORTANT :
        cette fonction ne crée aucun signal et ne modifie aucune stratégie.

        Elle sert uniquement à éviter que le premier cycle d'analyse
        démarre avant que BiQuote soit réellement prêt.
        """

        logger.info(
            "Vérification disponibilité des prix BiQuote..."
        )

        started = time.monotonic()

        ready: Dict[str, bool] = {
            symbol: False
            for symbol in self.symbols
        }

        while True:

            elapsed = (
                time.monotonic()
                - started
            )

            # ---------------------------------------------------------------
            # Vérification de chaque moteur
            # ---------------------------------------------------------------

            for symbol in self.symbols:

                if ready[symbol]:
                    continue

                moteur = self.moteurs[symbol]

                try:

                    status = moteur.get_status()

                    if _contient_prix(status):

                        ready[symbol] = True

                        logger.info(
                            "Prix disponible : %s",
                            symbol,
                        )

                except Exception as exc:

                    logger.debug(
                        "Impossible de vérifier le prix %s : %s",
                        symbol,
                        exc,
                    )

            # ---------------------------------------------------------------
            # Tous les actifs sont prêts.
            # ---------------------------------------------------------------

            if all(ready.values()):

                logger.info(
                    "BiQuote prêt : prix disponibles pour les %s actifs.",
                    len(self.symbols),
                )

                return {
                    "ready": True,
                    "timed_out": False,
                    "elapsed_seconds": round(
                        elapsed,
                        3,
                    ),
                    "ready_symbols": [
                        symbol
                        for symbol, value in ready.items()
                        if value
                    ],
                    "not_ready_symbols": [
                        symbol
                        for symbol, value in ready.items()
                        if not value
                    ],
                }

            # ---------------------------------------------------------------
            # Timeout.
            #
            # On ne fabrique aucun prix.
            # Les actifs non prêts pourront retourner NO_PRICE
            # naturellement dans moteur2.
            # ---------------------------------------------------------------

            if (
                elapsed
                >= STREAM_READY_TIMEOUT_SECONDS
            ):

                not_ready = [
                    symbol
                    for symbol, value in ready.items()
                    if not value
                ]

                logger.warning(
                    "Timeout attente prix BiQuote après %.2fs. "
                    "Actifs sans prix : %s",
                    elapsed,
                    ", ".join(not_ready),
                )

                return {
                    "ready": False,
                    "timed_out": True,
                    "elapsed_seconds": round(
                        elapsed,
                        3,
                    ),
                    "ready_symbols": [
                        symbol
                        for symbol, value in ready.items()
                        if value
                    ],
                    "not_ready_symbols": not_ready,
                }

            await asyncio.sleep(
                STREAM_READY_CHECK_INTERVAL_SECONDS
            )

    # =========================================================================
    # ANALYSE D'UN ACTIF
    # =========================================================================

    async def analyser_symbol(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        normalized = _normaliser_symbole(
            symbol
        )

        if normalized not in self.moteurs:

            logger.warning(
                "Symbole non enregistré : %s",
                normalized,
            )

            return {
                "status": "SYMBOL_NOT_REGISTERED",
                "symbol": normalized,
                "signals": [],
            }

        moteur = self.moteurs[normalized]

        started = time.monotonic()

        logger.info(
            "--------------------------------------------------"
        )

        logger.info(
            "DEBUT ANALYSE : %s",
            normalized,
        )

        logger.info(
            "Appel moteur2.analyser() : %s",
            normalized,
        )

        try:

            result = await asyncio.wait_for(
                moteur.analyser(),
                timeout=ANALYSIS_TIMEOUT_SECONDS,
            )

            elapsed = (
                time.monotonic()
                - started
            )

            if not isinstance(
                result,
                dict,
            ):

                result = {
                    "status":
                        "INVALID_ENGINE_RESULT",
                    "symbol":
                        normalized,
                    "raw_result":
                        result,
                    "signals":
                        [],
                }

            result.setdefault(
                "symbol",
                normalized,
            )

            self.last_results[
                normalized
            ] = result

            status = str(
                result.get(
                    "status",
                    "UNKNOWN",
                )
            )

            signals = result.get(
                "signals",
                [],
            )

            if not isinstance(
                signals,
                list,
            ):
                signals = [signals]

            logger.info(
                "FIN ANALYSE : %s | status=%s | signals=%s | duree=%.2fs",
                normalized,
                status,
                len(signals),
                elapsed,
            )

            logger.info(
                "--------------------------------------------------"
            )

            return result

        except asyncio.TimeoutError:

            elapsed = (
                time.monotonic()
                - started
            )

            logger.error(
                "TIMEOUT ANALYSE : %s | duree=%.2fs | timeout=%ss",
                normalized,
                elapsed,
                ANALYSIS_TIMEOUT_SECONDS,
            )

            result = {
                "status":
                    "ANALYSIS_TIMEOUT",
                "symbol":
                    normalized,
                "error":
                    (
                        "Analyse dépassant "
                        f"{ANALYSIS_TIMEOUT_SECONDS} secondes."
                    ),
                "signals":
                    [],
            }

            self.last_results[
                normalized
            ] = result

            logger.info(
                "--------------------------------------------------"
            )

            return result

        except asyncio.CancelledError:

            logger.warning(
                "Analyse annulée : %s",
                normalized,
            )

            raise

        except Exception as exc:

            elapsed = (
                time.monotonic()
                - started
            )

            logger.exception(
                "ERREUR ANALYSE : %s | duree=%.2fs",
                normalized,
                elapsed,
            )

            result = {
                "status":
                    "ENGINE_ERROR",
                "symbol":
                    normalized,
                "error":
                    str(exc),
                "signals":
                    [],
            }

            self.last_results[
                normalized
            ] = result

            logger.info(
                "--------------------------------------------------"
            )

            return result

    # =========================================================================
    # ANALYSE DE TOUS LES ACTIFS
    # =========================================================================

    async def analyser_tous(
        self,
    ) -> Dict[str, Any]:

        async with self._cycle_lock:

            cycle_started = time.monotonic()

            logger.info("")

            logger.info(
                "=================================================="
            )

            logger.info(
                "NOVA ENGINE 2 — CYCLE MULTI-ACTIFS"
            )

            logger.info(
                "ACTIFS : %s",
                ", ".join(self.symbols),
            )

            logger.info(
                "MODE : %s",
                "PARALLELE" if self.parallel else "SEQUENTIEL",
            )

            logger.info(
                "TIMEOUT PAR ACTIF : %ss",
                ANALYSIS_TIMEOUT_SECONDS,
            )

            logger.info(
                "=================================================="
            )

            # -----------------------------------------------------------------
            # SÉCURITÉ :
            # si analyser_tous() est appelé directement sans passer par run(),
            # on démarre quand même les streams avant l'analyse.
            # -----------------------------------------------------------------

            if not self._streams_started:

                logger.info(
                    "Streams non démarrés. "
                    "Démarrage avant le cycle d'analyse..."
                )

                await self.demarrer_streams()

            # -----------------------------------------------------------------
            # NOUVEAU :
            # attendre que BiQuote fournisse les prix.
            # -----------------------------------------------------------------

            readiness = await self.attendre_prix()

            logger.info(
                "État préparation BiQuote : %s",
                readiness,
            )

            results: Dict[
                str,
                Dict[str, Any],
            ] = {}

            # -----------------------------------------------------------------
            # MODE PARALLÈLE
            # -----------------------------------------------------------------

            if self.parallel:

                logger.info(
                    "Lancement des %s analyses simultanées...",
                    len(self.symbols),
                )

                tasks = {}

                for symbol in self.symbols:

                    logger.info(
                        "Création tâche : %s",
                        symbol,
                    )

                    tasks[symbol] = (
                        asyncio.create_task(
                            self.analyser_symbol(
                                symbol
                            )
                        )
                    )

                logger.info(
                    "%s tâches créées.",
                    len(tasks),
                )

                logger.info(
                    "Attente des résultats des moteurs..."
                )

                completed = await asyncio.gather(
                    *tasks.values(),
                    return_exceptions=True,
                )

                logger.info(
                    "asyncio.gather() terminé."
                )

                for symbol, result in zip(
                    tasks.keys(),
                    completed,
                ):

                    if isinstance(
                        result,
                        Exception,
                    ):

                        logger.error(
                            "Exception retournée pour %s : %s",
                            symbol,
                            result,
                        )

                        results[symbol] = {
                            "status":
                                "ENGINE_ERROR",
                            "symbol":
                                symbol,
                            "error":
                                str(result),
                            "signals":
                                [],
                        }

                    else:

                        results[symbol] = result

            # -----------------------------------------------------------------
            # MODE SÉQUENTIEL
            # -----------------------------------------------------------------

            else:

                logger.info(
                    "Analyse séquentielle activée."
                )

                for symbol in self.symbols:

                    logger.info(
                        "Passage à l'actif : %s",
                        symbol,
                    )

                    results[symbol] = (
                        await self.analyser_symbol(
                            symbol
                        )
                    )

            # -----------------------------------------------------------------
            # EXTRACTION DES SIGNAUX
            # -----------------------------------------------------------------

            all_signals: List[Any] = []

            status_by_symbol: Dict[
                str,
                str,
            ] = {}

            signals_by_symbol: Dict[
                str,
                Any,
            ] = {}

            for symbol, result in results.items():

                status = str(
                    _get(
                        result,
                        "status",
                        "UNKNOWN",
                    )
                )

                status_by_symbol[
                    symbol
                ] = status

                signals = _get(
                    result,
                    "signals",
                    [],
                )

                if not isinstance(
                    signals,
                    list,
                ):

                    signals = [signals]

                signals_by_symbol[
                    symbol
                ] = signals

                logger.info(
                    "RESULTAT %s : status=%s | signals=%s",
                    symbol,
                    status,
                    len(signals),
                )

                for signal in signals:

                    if signal is None:
                        continue

                    all_signals.append(
                        {
                            "symbol":
                                symbol,
                            "signal":
                                signal,
                        }
                    )

            # -----------------------------------------------------------------
            # RÉSUMÉ DU CYCLE
            # -----------------------------------------------------------------

            cycle_elapsed = (
                time.monotonic()
                - cycle_started
            )

            cycle = {
                "status":
                    "COMPLETED",

                "symbols":
                    list(self.symbols),

                "results":
                    results,

                "status_by_symbol":
                    status_by_symbol,

                "signals_by_symbol":
                    signals_by_symbol,

                "all_signals":
                    all_signals,

                "total_symbols":
                    len(self.symbols),

                "total_signals":
                    len(all_signals),

                "cycle_duration_seconds":
                    round(
                        cycle_elapsed,
                        3,
                    ),

                "stream_readiness":
                    readiness,
            }

            self.last_cycle = cycle

            logger.info(
                "=================================================="
            )

            logger.info(
                "CYCLE MULTI-ACTIFS TERMINE"
            )

            logger.info(
                "Actifs analyses : %s",
                len(self.symbols),
            )

            logger.info(
                "Signaux existants : %s",
                len(all_signals),
            )

            logger.info(
                "Duree totale : %.2fs",
                cycle_elapsed,
            )

            logger.info(
                "Etats : %s",
                status_by_symbol,
            )

            logger.info(
                "=================================================="
            )

            return cycle

    # =========================================================================
    # RUN CONTINU
    # =========================================================================

    async def run(
        self,
        *,
        analysis_interval_seconds: Optional[int] = None,
        start_streams: bool = True,
    ) -> None:

        interval = (
            self.analysis_interval_seconds
            if analysis_interval_seconds is None
            else max(
                1,
                int(
                    analysis_interval_seconds
                ),
            )
        )

        # ---------------------------------------------------------------------
        # INITIALISATION
        # ---------------------------------------------------------------------

        if not self.initialized:

            logger.info(
                "RUN ENGINE 2 : initialisation requise."
            )

            init = await self.initialiser()

            if not init.get(
                "success",
                False,
            ):

                raise RuntimeError(
                    "Aucun moteur Engine 2 "
                    "n'a pu etre initialise."
                )

        # ---------------------------------------------------------------------
        # STREAMS
        # ---------------------------------------------------------------------

        self.running = True

        if start_streams:

            logger.info(
                "RUN ENGINE 2 : démarrage des streams..."
            )

            await self.demarrer_streams()

            # ---------------------------------------------------------------
            # CRITIQUE :
            # attendre ici AVANT le premier cycle.
            # ---------------------------------------------------------------

            readiness = await self.attendre_prix()

            logger.info(
                "RUN ENGINE 2 : préparation des streams terminée : %s",
                readiness,
            )

        # ---------------------------------------------------------------------
        # BOUCLE
        # ---------------------------------------------------------------------

        try:

            while self.running:

                try:

                    await self.analyser_tous()

                except Exception as exc:

                    logger.exception(
                        "Erreur cycle multi-actifs : %s",
                        exc,
                    )

                logger.info(
                    "Prochain cycle dans %ss.",
                    interval,
                )

                await asyncio.sleep(
                    interval
                )

        finally:

            self.running = False

            await self._arreter_stream_tasks()

    # =========================================================================
    # ARRÊT DES STREAM TASKS
    # =========================================================================

    async def _arreter_stream_tasks(
        self,
    ) -> None:

        tasks = list(
            self._stream_tasks.values()
        )

        if not tasks:
            return

        logger.info(
            "Arrêt des tâches streams BiQuote..."
        )

        for task in tasks:

            if not task.done():
                task.cancel()

        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        self._stream_tasks.clear()

        self._streams_started = False

        logger.info(
            "Tâches streams BiQuote arrêtées."
        )

    # =========================================================================
    # STOP
    # =========================================================================

    async def stop(
        self,
    ) -> None:

        self.running = False

        logger.info(
            "Arrêt des moteurs multi-actifs..."
        )

        await self._arreter_stream_tasks()

        tasks = [
            asyncio.create_task(
                self._stop_symbol(symbol)
            )
            for symbol in self.symbols
        ]

        if tasks:

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        logger.info(
            "Moteurs multi-actifs arrêtés."
        )

    async def _stop_symbol(
        self,
        symbol: str,
    ) -> None:

        moteur = self.moteurs.get(
            symbol
        )

        if moteur is None:
            return

        try:

            await moteur.stop()

        except Exception as exc:

            logger.warning(
                "Erreur arrêt %s : %s",
                symbol,
                exc,
            )

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(
        self,
    ) -> Dict[str, Any]:

        engines: Dict[
            str,
            Any,
        ] = {}

        for symbol, moteur in (
            self.moteurs.items()
        ):

            try:

                engines[symbol] = (
                    moteur.get_status()
                )

            except Exception as exc:

                engines[symbol] = {
                    "symbol":
                        symbol,
                    "status":
                        "STATUS_ERROR",
                    "error":
                        str(exc),
                }

        return {
            "engine":
                "NOVA TRADE AI - ENGINE 2",

            "module":
                "moteur2_multi_actifs",

            "symbols":
                list(self.symbols),

            "symbol_count":
                len(self.symbols),

            "initialized":
                self.initialized,

            "running":
                self.running,

            "parallel":
                self.parallel,

            "analysis_interval_seconds":
                self.analysis_interval_seconds,

            "analysis_timeout_seconds":
                ANALYSIS_TIMEOUT_SECONDS,

            "stream_ready_timeout_seconds":
                STREAM_READY_TIMEOUT_SECONDS,

            "streams_started":
                self._streams_started,

            "stream_tasks":
                {
                    symbol:
                        not task.done()
                    for symbol, task
                    in self._stream_tasks.items()
                },

            "engines":
                engines,

            "last_cycle":
                self.last_cycle,
        }


# ============================================================================
# INSTANCE PAR DEFAUT
# ============================================================================

multi_actifs = Moteur2MultiActifs()


# ============================================================================
# RACCOURCIS
# ============================================================================

async def initialiser_multi_actifs() -> Dict[str, Any]:
    return await multi_actifs.initialiser()


async def analyser_multi_actifs() -> Dict[str, Any]:
    return await multi_actifs.analyser_tous()


async def arreter_multi_actifs() -> None:
    await multi_actifs.stop()


def statut_multi_actifs() -> Dict[str, Any]:
    return multi_actifs.get_status()


# ============================================================================
# TEST DIRECT
# ============================================================================

async def main() -> None:

    moteur = Moteur2MultiActifs()

    try:

        print("=" * 70)

        print(
            "NOVA TRADE AI — ENGINE 2"
        )

        print(
            "GESTIONNAIRE MULTI-ACTIFS"
        )

        print("=" * 70)

        print(
            "ACTIFS :",
            ", ".join(
                moteur.symbols
            ),
        )

        init = await moteur.initialiser()

        print()

        print(
            "INITIALISATION :"
        )

        print(init)

        if not init.get(
            "success",
            False,
        ):
            return

        # ---------------------------------------------------------------------
        # Le test direct doit lui aussi démarrer les streams avant l'analyse.
        # ---------------------------------------------------------------------

        await moteur.demarrer_streams()

        readiness = await moteur.attendre_prix()

        print()

        print(
            "PREPARATION BIQUOTE :"
        )

        print(
            readiness
        )

        result = (
            await moteur.analyser_tous()
        )

        print()

        print(
            "CYCLE :"
        )

        print(
            result
        )

    finally:

        await moteur.stop()


if __name__ == "__main__":

    asyncio.run(main())


__all__ = [
    "DEFAULT_SYMBOLS",
    "DEFAULT_ANALYSIS_INTERVAL",
    "ANALYSIS_TIMEOUT_SECONDS",
    "STREAM_READY_TIMEOUT_SECONDS",
    "Moteur2MultiActifs",
    "multi_actifs",
    "initialiser_multi_actifs",
    "analyser_multi_actifs",
    "arreter_multi_actifs",
    "statut_multi_actifs",
]