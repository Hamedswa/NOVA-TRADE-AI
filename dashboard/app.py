"""
NOVA TRADE AI
dashboard/app.py

Founder Dashboard — lecture seule.

IMPORTANT
---------
Le dashboard :
    - observe uniquement le système ;
    - ne génère aucun signal ;
    - ne valide aucun setup ;
    - ne rejette aucun setup ;
    - ne modifie aucun signal ;
    - n'exécute aucun ordre.

Architecture affichée :

    BiQuote
       ↓
    Moteur 2
       ↓
    H4 → H1 → M15 → M5 → M1
       ↓
    Validation
       ↓
    Anti-spam
       ↓
    Telegram

Le dashboard n'intervient jamais dans cette chaîne.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse


# ============================================================
# CONFIGURATION
# ============================================================

try:
    from config import CONFIG

except Exception:
    CONFIG = None


# ============================================================
# RUNTIME
# ============================================================

try:
    from signals.runtime import (
        get_runtime_status,
        signal_tracker,
    )

except Exception:
    get_runtime_status = None
    signal_tracker = None


# ============================================================
# SESSION SUPERVISOR
# ============================================================

try:
    from ai_session_supervisor import (
        session_supervisor,
    )

except Exception:
    session_supervisor = None


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

try:
    from economic_calendar import (
        economic_calendar,
    )

except Exception:
    economic_calendar = None


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="NOVA TRADE AI — Founder Dashboard",
    version="2.0.0",
    description=(
        "Dashboard lecture seule du Moteur 2 NOVA TRADE AI."
    ),
)


# ============================================================
# HELPERS
# ============================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

DISPLAY_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
}

TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)


def now_utc() -> str:
    """Retourne l'heure UTC actuelle."""

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def safe_get(
    obj: Any,
    name: str,
    default: Any = None,
) -> Any:
    """Lecture défensive d'un attribut."""

    if obj is None:
        return default

    try:
        value = getattr(
            obj,
            name,
            default,
        )

        if callable(value):
            return default

        return value

    except Exception:
        return default


def normalize_symbol(
    symbol: str,
) -> str:
    """Normalise un symbole d'affichage/interne."""

    value = str(
        symbol or ""
    ).upper().strip()

    return (
        value
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def display_symbol(
    symbol: str,
) -> str:
    """Convertit XAUUSD → XAU/USD."""

    normalized = normalize_symbol(
        symbol
    )

    return DISPLAY_SYMBOLS.get(
        normalized,
        normalized,
    )


def get_config_value(
    name: str,
    default: Any,
) -> Any:
    """Lit une valeur de CONFIG sans faire planter le dashboard."""

    if CONFIG is None:
        return default

    return getattr(
        CONFIG,
        name,
        default,
    )


# ============================================================
# RUNTIME STATUS
# ============================================================

def collect_runtime_status() -> dict[str, Any]:
    """
    Récupère uniquement les informations réellement
    disponibles dans le runtime.
    """

    if get_runtime_status is None:

        return {
            "available": False,
            "reason": "Runtime signaux indisponible.",
        }

    try:

        status = get_runtime_status()

        if not isinstance(
            status,
            dict,
        ):

            return {
                "available": False,
                "reason": "Format runtime invalide.",
            }

        return status

    except Exception as exc:

        return {
            "available": False,
            "reason": str(exc),
        }


# ============================================================
# TRACKER STATUS
# ============================================================

def collect_tracker_status() -> dict[str, Any]:
    """
    Retourne l'état réel du tracker.

    Aucun signal n'est créé ici.
    """

    if signal_tracker is None:

        return {
            "available": False,
            "active_signals": 0,
            "tracked_signals": [],
        }

    try:

        states = signal_tracker.all_states()

    except Exception:

        states = []

    if states is None:
        states = []

    if isinstance(
        states,
        dict,
    ):

        states = list(
            states.values()
        )

    tracked = []

    for state in states:

        signal = safe_get(
            state,
            "signal",
        )

        symbol = safe_get(
            state,
            "symbol",
        )

        if symbol is None and signal is not None:

            symbol = safe_get(
                signal,
                "symbol",
            )

        normalized = normalize_symbol(
            symbol
        )

        if not normalized:
            continue

        tracked.append(
            {
                "symbol": normalized,
                "display_symbol": display_symbol(
                    normalized
                ),
                "status": safe_get(
                    state,
                    "status",
                    "UNKNOWN",
                ),
                "current_r": safe_get(
                    state,
                    "current_r",
                ),
                "best_r": safe_get(
                    state,
                    "best_r",
                ),
                "worst_r": safe_get(
                    state,
                    "worst_r",
                ),
                "tp1_hit": bool(
                    safe_get(
                        state,
                        "tp1_hit",
                        False,
                    )
                ),
                "tp2_hit": bool(
                    safe_get(
                        state,
                        "tp2_hit",
                        False,
                    )
                ),
                "tp3_hit": bool(
                    safe_get(
                        state,
                        "tp3_hit",
                        False,
                    )
                ),
                "sl_hit": bool(
                    safe_get(
                        state,
                        "sl_hit",
                        False,
                    )
                ),
                "be_recommended": bool(
                    safe_get(
                        state,
                        "be_recommended",
                        False,
                    )
                ),
            }
        )

    return {
        "available": True,
        "active_signals": len(
            tracked
        ),
        "tracked_signals": tracked,
    }


# ============================================================
# MARKET STATUS
# ============================================================

def collect_market_status() -> list[dict[str, Any]]:
    """
    Construit l'état descriptif des quatre marchés.

    IMPORTANT :
    Aucun READY artificiel n'est produit.

    Un marché peut être :
        - TRACKED
        - NO_ACTIVE_SIGNAL
        - UNAVAILABLE
    """

    tracker_status = (
        collect_tracker_status()
    )

    tracked_by_symbol = {
        item["symbol"]: item
        for item in tracker_status.get(
            "tracked_signals",
            [],
        )
    }

    result = []

    for symbol in SUPPORTED_SYMBOLS:

        tracked = tracked_by_symbol.get(
            symbol
        )

        if tracked is not None:

            status = tracked.get(
                "status",
                "TRACKING",
            )

            label = "SUIVI"

        else:

            status = "NO_ACTIVE_SIGNAL"

            label = "AUCUN SIGNAL ACTIF"

        result.append(
            {
                "symbol": symbol,
                "display_symbol": display_symbol(
                    symbol
                ),
                "status": status,
                "label": label,
                "signal_active": (
                    tracked is not None
                ),
            }
        )

    return result


# ============================================================
# SESSION STATUS
# ============================================================

def collect_sessions() -> list[dict[str, Any]]:
    """
    Lit les sessions depuis le superviseur.

    Le superviseur reste purement informatif.
    """

    if session_supervisor is None:

        return [
            {
                "name": "Tokyo",
                "status": "—",
            },
            {
                "name": "London",
                "status": "—",
            },
            {
                "name": "New York",
                "status": "—",
            },
        ]

    try:

        data = (
            session_supervisor.get_all_sessions_status()
        )

    except Exception:

        data = {}

    result = []

    names = (
        "Tokyo",
        "London",
        "New York",
    )

    for name in names:

        item = {}

        if isinstance(
            data,
            dict,
        ):

            item = (
                data.get(name)
                or data.get(
                    name.lower(),
                )
                or {}
            )

        if not isinstance(
            item,
            dict,
        ):

            item = {}

        result.append(
            {
                "name": name,
                "status": str(
                    item.get(
                        "status",
                        "—",
                    )
                ).upper(),
            }
        )

    return result


# ============================================================
# NEWS STATUS
# ============================================================

def collect_news_status() -> dict[str, Any]:
    """
    Informations économiques uniquement.

    Aucun blocage de signal n'est effectué.
    """

    if economic_calendar is None:

        return {
            "available": False,
            "high_impact_events": 0,
            "informational_only": True,
        }

    try:

        events = (
            economic_calendar.get_relevant_events()
        )

        if events is None:
            events = []

        return {
            "available": True,
            "high_impact_events": len(
                events
            ),
            "informational_only": True,
            "blocking": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_modify_signal": False,
        }

    except Exception:

        return {
            "available": True,
            "high_impact_events": 0,
            "informational_only": True,
            "blocking": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_modify_signal": False,
        }


# ============================================================
# API STATUS
# ============================================================

@app.get("/api/status")
async def api_status():
    """
    API de statut globale.

    Lecture seule.
    """

    runtime = (
        collect_runtime_status()
    )

    tracker = (
        collect_tracker_status()
    )

    news = (
        collect_news_status()
    )

    return JSONResponse(
        {
            "system": "NOVA TRADE AI",
            "engine": "Moteur 2",
            "data_provider": get_config_value(
                "DATA_PROVIDER",
                "BiQuote",
            ),
            "timeframes": list(
                TIMEFRAMES
            ),
            "supported_symbols": [
                display_symbol(symbol)
                for symbol in SUPPORTED_SYMBOLS
            ],
            "minimum_rr": get_config_value(
                "MINIMUM_RR",
                3.0,
            ),
            "score_threshold": get_config_value(
                "SIGNAL_THRESHOLD",
                60.0,
            ),
            "auto_execution": False,
            "read_only": True,
            "runtime": runtime,
            "tracker": tracker,
            "news": news,
            "timestamp_utc": now_utc(),
        }
    )


# ============================================================
# API MARKETS
# ============================================================

@app.get("/api/markets")
async def api_markets():
    """État des quatre marchés."""

    return JSONResponse(
        {
            "markets": collect_market_status(),
            "timestamp_utc": now_utc(),
        }
    )


# ============================================================
# API SESSIONS
# ============================================================

@app.get("/api/sessions")
async def api_sessions():
    """État informatif des sessions."""

    return JSONResponse(
        {
            "sessions": collect_sessions(),
            "informational_only": True,
            "timestamp_utc": now_utc(),
        }
    )


# ============================================================
# API TRACKER
# ============================================================

@app.get("/api/tracker")
async def api_tracker():
    """État observationnel du tracker."""

    return JSONResponse(
        collect_tracker_status()
    )


# ============================================================
# DASHBOARD HTML
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
async def dashboard():

    runtime = (
        collect_runtime_status()
    )

    tracker = (
        collect_tracker_status()
    )

    markets = (
        collect_market_status()
    )

    sessions = (
        collect_sessions()
    )

    news = (
        collect_news_status()
    )

    runtime_available = bool(
        runtime.get(
            "available",
            True,
        )
    )

    runtime_label = (
        "CONNECTÉ"
        if runtime_available
        else "NON DISPONIBLE"
    )

    runtime_class = (
        "green"
        if runtime_available
        else "yellow"
    )

    active_signals = int(
        tracker.get(
            "active_signals",
            0,
        )
        or 0
    )

    news_count = int(
        news.get(
            "high_impact_events",
            0,
        )
        or 0
    )

    minimum_rr = get_config_value(
        "MINIMUM_RR",
        3.0,
    )

    score_threshold = get_config_value(
        "SIGNAL_THRESHOLD",
        60.0,
    )

    market_html = ""

    for market in markets:

        label = escape(
            str(
                market.get(
                    "label",
                    "—",
                )
            )
        )

        status = escape(
            str(
                market.get(
                    "status",
                    "—",
                )
            )
        )

        market_class = (
            "active"
            if market.get(
                "signal_active",
                False,
            )
            else "neutral"
        )

        market_html += f"""
        <div class="market">
            <div>
                <div class="market-name">
                    {escape(market["display_symbol"])}
                </div>
                <div class="market-sub">
                    BiQuote · H4 · H1 · M15 · M5 · M1
                </div>
            </div>

            <div class="market-info">
                {label}
                <span class="badge {market_class}">
                    {status}
                </span>
            </div>
        </div>
        """

    session_html = ""

    for session in sessions:

        session_status = escape(
            str(
                session.get(
                    "status",
                    "—",
                )
            )
        )

        session_class = (
            "active"
            if session_status == "OPEN"
            else "neutral"
        )

        session_html += f"""
        <div class="market">
            <div class="market-name">
                {escape(session["name"])}
            </div>

            <div class="market-info">
                <span class="badge {session_class}">
                    {session_status}
                </span>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="fr">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <meta
            http-equiv="refresh"
            content="30"
        >

        <title>
            NOVA TRADE AI — Founder Dashboard
        </title>

        <style>

            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}

            body {{
                font-family:
                    -apple-system,
                    BlinkMacSystemFont,
                    "Segoe UI",
                    sans-serif;

                background: #0b0f14;
                color: #ffffff;
                min-height: 100vh;
                padding: 20px;
            }}

            .container {{
                max-width: 1100px;
                margin: auto;
            }}

            header {{
                margin-bottom: 25px;
            }}

            .brand {{
                font-size: 24px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }}

            .subtitle {{
                color: #8b949e;
                margin-top: 5px;
                font-size: 14px;
            }}

            .status-card,
            .card,
            .section {{
                background: #111820;
                border: 1px solid #1f2a35;
                border-radius: 16px;
            }}

            .status-card {{
                padding: 20px;
                margin-bottom: 20px;
            }}

            .status-title,
            .card-title {{
                color: #8b949e;
                font-size: 12px;
                margin-bottom: 8px;
            }}

            .online {{
                font-size: 22px;
                font-weight: 700;
            }}

            .green {{
                color: #35d07f;
            }}

            .yellow {{
                color: #f0c674;
            }}

            .grid {{
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(150px, 1fr));
                gap: 12px;
                margin-bottom: 20px;
            }}

            .card {{
                padding: 18px;
            }}

            .card-value {{
                font-size: 20px;
                font-weight: 700;
            }}

            .section {{
                padding: 20px;
                margin-bottom: 20px;
            }}

            .section h2 {{
                font-size: 18px;
                margin-bottom: 15px;
            }}

            .market {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 15px;
                padding: 14px 0;
                border-bottom: 1px solid #1f2a35;
            }}

            .market:last-child {{
                border-bottom: none;
            }}

            .market-name {{
                font-weight: 700;
            }}

            .market-sub {{
                color: #59636e;
                font-size: 11px;
                margin-top: 4px;
            }}

            .market-info {{
                text-align: right;
                color: #8b949e;
                font-size: 13px;
            }}

            .badge {{
                display: inline-block;
                padding: 5px 9px;
                border-radius: 8px;
                font-size: 10px;
                font-weight: 700;
                margin-left: 6px;
            }}

            .active {{
                background: rgba(
                    53,
                    208,
                    127,
                    0.12
                );

                color: #35d07f;
            }}

            .neutral {{
                background: rgba(
                    139,
                    148,
                    158,
                    0.10
                );

                color: #8b949e;
            }}

            .yellow-badge {{
                background: rgba(
                    240,
                    198,
                    116,
                    0.12
                );

                color: #f0c674;
            }}

            .architecture {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                align-items: center;
            }}

            .step {{
                background: #0b0f14;
                border: 1px solid #1f2a35;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 12px;
                font-weight: 700;
            }}

            .arrow {{
                color: #59636e;
            }}

            .notice {{
                color: #8b949e;
                font-size: 13px;
                line-height: 1.6;
                margin-top: 8px;
            }}

            footer {{
                text-align: center;
                color: #59636e;
                font-size: 12px;
                padding: 10px 0 20px;
            }}

            @media (max-width: 600px) {{

                body {{
                    padding: 12px;
                }}

                .market {{
                    align-items: flex-start;
                }}

                .market-info {{
                    max-width: 150px;
                }}

            }}

        </style>

    </head>

    <body>

        <div class="container">

            <header>

                <div class="brand">
                    NOVA TRADE AI
                </div>

                <div class="subtitle">
                    Founder Dashboard · Moteur 2 · Lecture seule
                </div>

            </header>


            <!-- SYSTEM -->

            <div class="status-card">

                <div class="status-title">
                    SYSTEM STATUS
                </div>

                <div class="online {runtime_class}">
                    ● {runtime_label}
                </div>

                <div class="notice">
                    Dernière lecture :
                    {escape(now_utc())}
                </div>

            </div>


            <!-- CONFIGURATION -->

            <div class="grid">

                <div class="card">

                    <div class="card-title">
                        DATA PROVIDER
                    </div>

                    <div class="card-value green">
                        {escape(
                            str(
                                get_config_value(
                                    "DATA_PROVIDER",
                                    "BiQuote",
                                )
                            )
                        )}
                    </div>

                </div>


                <div class="card">

                    <div class="card-title">
                        TIMEFRAMES
                    </div>

                    <div class="card-value">
                        H4 → H1 → M15
                    </div>

                    <div class="notice">
                        M5 → M1 confirmation
                    </div>

                </div>


                <div class="card">

                    <div class="card-title">
                        RR MINIMUM
                    </div>

                    <div class="card-value green">
                        1:{minimum_rr:g}
                    </div>

                </div>


                <div class="card">

                    <div class="card-title">
                        SCORE INDICATIF
                    </div>

                    <div class="card-value">
                        {score_threshold:g}/100
                    </div>

                    <div class="notice">
                        Qualité / confiance
                    </div>

                </div>

            </div>


            <!-- MARCHES -->

            <div class="section">

                <h2>📊 Marchés</h2>

                {market_html}

            </div>


            <!-- TRACKER -->

            <div class="grid">

                <div class="card">

                    <div class="card-title">
                        SIGNAUX ACTIFS
                    </div>

                    <div class="card-value">
                        {active_signals}
                    </div>

                </div>


                <div class="card">

                    <div class="card-title">
                        NEWS HIGH IMPACT
                    </div>

                    <div class="card-value yellow">
                        {news_count}
                    </div>

                    <div class="notice">
                        Informatif uniquement
                    </div>

                </div>


                <div class="card">

                    <div class="card-title">
                        EXÉCUTION AUTOMATIQUE
                    </div>

                    <div class="card-value">
                        OFF
                    </div>

                </div>


                <div class="card">

                    <div class="card-title">
                        MODE DASHBOARD
                    </div>

                    <div class="card-value green">
                        READ ONLY
                    </div>

                </div>

            </div>


            <!-- ARCHITECTURE -->

            <div class="section">

                <h2>⚙️ Pipeline Moteur 2</h2>

                <div class="architecture">

                    <div class="step">
                        BiQuote
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        H4
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        H1
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        M15
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        M5
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        M1
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        VALIDATION
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        ANTI-SPAM
                    </div>

                    <div class="arrow">→</div>

                    <div class="step">
                        TELEGRAM
                    </div>

                </div>

                <div class="notice">
                    Le dashboard observe cette architecture.
                    Il n'intervient dans aucune décision de trading.
                </div>

            </div>


            <!-- SESSIONS -->

            <div class="section">

                <h2>🌍 Sessions</h2>

                {session_html}

                <div class="notice">
                    Le superviseur de sessions est
                    strictement informatif.
                    Il ne bloque et ne modifie aucun signal.
                </div>

            </div>


            <!-- AUTHORITIES -->

            <div class="section">

                <h2>🔒 Autorités système</h2>

                <div class="market">

                    <div>
                        Validation finale
                    </div>

                    <div class="market-info">
                        moteur2_validation.py
                    </div>

                </div>

                <div class="market">

                    <div>
                        Anti-spam
                    </div>

                    <div class="market-info">
                        moteur2_antispam.py
                    </div>

                </div>

                <div class="market">

                    <div>
                        Tracker / Monitor
                    </div>

                    <div class="market-info">
                        Observation uniquement
                    </div>

                </div>

                <div class="market">

                    <div>
                        Exécution automatique
                    </div>

                    <div class="market-info">
                        DÉSACTIVÉE
                    </div>

                </div>

            </div>


            <footer>
                NOVA TRADE AI · Moteur 2 · Founder Dashboard · Read Only
            </footer>

        </div>

    </body>

    </html>
    """


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": "NOVA TRADE AI Founder Dashboard",
        "engine": "Moteur 2",
        "read_only": True,
        "auto_execution": False,
        "timestamp_utc": now_utc(),
    }