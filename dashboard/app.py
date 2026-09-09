from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="NOVA TRADE AI — Founder Dashboard",
    version="1.0.0",
)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1.0">

        <title>NOVA TRADE AI — Founder Dashboard</title>

        <style>
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont,
                             "Segoe UI", sans-serif;
                background: #0b0f14;
                color: #ffffff;
                min-height: 100vh;
                padding: 20px;
            }

            .container {
                max-width: 1100px;
                margin: auto;
            }

            header {
                margin-bottom: 25px;
            }

            .brand {
                font-size: 24px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }

            .subtitle {
                color: #8b949e;
                margin-top: 5px;
                font-size: 14px;
            }

            .status-card {
                background: #111820;
                border: 1px solid #1f2a35;
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 20px;
            }

            .status-title {
                color: #8b949e;
                font-size: 13px;
                margin-bottom: 8px;
            }

            .online {
                color: #35d07f;
                font-size: 22px;
                font-weight: 700;
            }

            .grid {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(150px, 1fr));
                gap: 12px;
                margin-bottom: 20px;
            }

            .card {
                background: #111820;
                border: 1px solid #1f2a35;
                border-radius: 16px;
                padding: 18px;
            }

            .card-title {
                color: #8b949e;
                font-size: 12px;
                margin-bottom: 10px;
            }

            .card-value {
                font-size: 20px;
                font-weight: 700;
            }

            .green {
                color: #35d07f;
            }

            .yellow {
                color: #f0c674;
            }

            .section {
                background: #111820;
                border: 1px solid #1f2a35;
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 20px;
            }

            .section h2 {
                font-size: 18px;
                margin-bottom: 15px;
            }

            .market {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 14px 0;
                border-bottom: 1px solid #1f2a35;
            }

            .market:last-child {
                border-bottom: none;
            }

            .market-name {
                font-weight: 700;
            }

            .market-info {
                text-align: right;
                color: #8b949e;
                font-size: 13px;
            }

            .badge {
                display: inline-block;
                padding: 5px 9px;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 700;
                margin-left: 6px;
            }

            .active {
                background: rgba(53, 208, 127, 0.12);
                color: #35d07f;
            }

            .reject {
                background: rgba(240, 198, 116, 0.12);
                color: #f0c674;
            }

            footer {
                text-align: center;
                color: #59636e;
                font-size: 12px;
                padding: 10px 0 20px;
            }
        </style>
    </head>

    <body>
        <div class="container">

            <header>
                <div class="brand">
                    NOVA TRADE AI
                </div>

                <div class="subtitle">
                    Founder Dashboard
                </div>
            </header>

            <div class="status-card">
                <div class="status-title">
                    SYSTEM STATUS
                </div>

                <div class="online">
                    ● ONLINE
                </div>
            </div>

            <div class="grid">

                <div class="card">
                    <div class="card-title">
                        TELEGRAM
                    </div>

                    <div class="card-value green">
                        ONLINE
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        TRADING ENGINE
                    </div>

                    <div class="card-value green">
                        ONLINE
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        MARKET DATA
                    </div>

                    <div class="card-value green">
                        ONLINE
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        NEWS SUPERVISOR
                    </div>

                    <div class="card-value green">
                        ONLINE
                    </div>
                </div>

            </div>

            <div class="section">

                <h2>📊 Marchés</h2>

                <div class="market">
                    <div class="market-name">
                        XAU/USD
                    </div>

                    <div class="market-info">
                        En attente
                        <span class="badge active">
                            READY
                        </span>
                    </div>
                </div>

                <div class="market">
                    <div class="market-name">
                        EUR/USD
                    </div>

                    <div class="market-info">
                        En attente
                        <span class="badge active">
                            READY
                        </span>
                    </div>
                </div>

                <div class="market">
                    <div class="market-name">
                        GBP/USD
                    </div>

                    <div class="market-info">
                        En attente
                        <span class="badge active">
                            READY
                        </span>
                    </div>
                </div>

                <div class="market">
                    <div class="market-name">
                        BTC/USD
                    </div>

                    <div class="market-info">
                        En attente
                        <span class="badge active">
                            READY
                        </span>
                    </div>
                </div>

            </div>

            <div class="grid">

                <div class="card">
                    <div class="card-title">
                        DERNIER SCAN
                    </div>

                    <div class="card-value">
                        —
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        SIGNAUX ACTIFS
                    </div>

                    <div class="card-value">
                        0
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        SIGNAUX REJETÉS
                    </div>

                    <div class="card-value">
                        0
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">
                        NEWS HIGH IMPACT
                    </div>

                    <div class="card-value yellow">
                        0
                    </div>
                </div>

            </div>

            <div class="section">

                <h2>🌍 Sessions</h2>

                <div class="market">
                    <div>Tokyo</div>
                    <div class="market-info">—</div>
                </div>

                <div class="market">
                    <div>London</div>
                    <div class="market-info">—</div>
                </div>

                <div class="market">
                    <div>New York</div>
                    <div class="market-info">—</div>
                </div>

            </div>

            <footer>
                NOVA TRADE AI · Founder Dashboard · Read Only
            </footer>

        </div>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "NOVA TRADE AI Founder Dashboard",
    }