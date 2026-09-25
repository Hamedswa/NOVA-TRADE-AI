import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moteur2_evidence import Moteur2Evidence


def test_evidence_extracts_primary_support_and_timing():
    engine = Moteur2Evidence()

    result = engine.analyser(
        "BTCUSD",
        intelligence={
            "directional_bias": "BUY",
            "trend_strength": 72,
            "timeframe_alignment": {
                "H4": {"direction": "BUY", "strength": 80},
                "H1": {"direction": "BUY", "strength": 75},
                "M15": {"direction": "BUY", "strength": 68},
                "M5": {"direction": "SELL", "strength": 55},
                "M1": {"direction": "BUY", "strength": 60},
            },
            "observations": ["Pression acheteuse observée."],
        },
        opportunites=[{
            "opportunity_id": "OP-1",
            "opportunity_type": "CONTINUATION",
            "direction": "BUY",
            "state": "DEVELOPING",
            "strength": 70,
            "timeframe_focus": "M15",
            "evidence": ["Contexte directionnel cohérent."],
        }],
        confirmation={
            "direction": "BUY",
            "m5_confirmed": False,
            "m1_confirmed": True,
            "m5_score": 45,
            "m1_score": 65,
            "confirmation_status": "INFORMATIVE",
            "entry_triggered": False,
            "warnings": ["M5 encore hésitant."],
        },
    )

    assert result["symbol"] == "BTCUSD"
    assert result["descriptive_only"] is True
    assert result["decision_owner"] == "moteur2_decision.py"
    assert result["maturity_inputs"]["has_directional_evidence"] is True
    assert result["maturity_inputs"]["primary_evidence_count"] > 0
    assert result["timing_information"]["m1_confirmed"] is True
    assert result["timing_information"]["m5_confirmed"] is False
    assert any(x["direction"] == "BUY" for x in result["supportive"])
    assert any(x["timeframe"] == "M5" for x in result["evidence"])


def test_neutral_input_does_not_create_direction():
    engine = Moteur2Evidence()

    result = engine.analyser(
        "EURUSD",
        intelligence={
            "directional_bias": "NEUTRAL",
            "observations": ["Marché sans direction claire."],
        },
    )

    assert result["direction_summary"]["BUY"]["support"] == 0.0
    assert result["direction_summary"]["SELL"]["support"] == 0.0
    assert result["maturity_inputs"]["has_directional_evidence"] is False


def test_invalid_symbol_rejected():
    engine = Moteur2Evidence()

    try:
        engine.analyser("USDJPY", intelligence={})
    except ValueError:
        return

    raise AssertionError("Un symbole hors univers doit être rejeté.")
