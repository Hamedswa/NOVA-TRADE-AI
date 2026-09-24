from moteur2_regime import Moteur2Regime


def test_neutral_market_is_not_directional():
    market = {
        "timeframes": {
            "H4": {"market_state": {"state": "RANGE", "phase": "RANGE"}, "direction": "NEUTRE"},
            "H1": {"market_state": {"state": "RANGE", "phase": "RANGE"}, "direction": "NEUTRE"},
            "M15": {"market_state": {"state": "RANGE", "phase": "RANGE"}, "direction": "NEUTRE"},
            "M5": {"direction": "NEUTRE"},
            "M1": {"direction": "NEUTRE"},
        }
    }
    result = Moteur2Regime().analyser(market, symbol="XAUUSD")
    assert result["regime"] == "RANGE"
    assert result["direction"] == "NEUTRE"
    assert result["decision_authority"] == "NONE"


def test_primary_alignment_is_directional_but_not_a_signal():
    market = {
        "timeframes": {
            "H4": {"market_state": {"state": "TENDANCE", "phase": "DIRECTIONNEL"}, "direction": "HAUSSIER", "strength": 80},
            "H1": {"market_state": {"state": "TENDANCE", "phase": "DIRECTIONNEL"}, "direction": "HAUSSIER", "strength": 70},
            "M15": {"market_state": {"state": "TENDANCE", "phase": "DIRECTIONNEL"}, "direction": "HAUSSIER", "strength": 60},
            "M5": {"direction": "BAISSIER", "strength": 40},
            "M1": {"direction": "NEUTRE", "strength": 20},
        }
    }
    result = Moteur2Regime().analyser(market, symbol="EURUSD")
    assert result["regime"] == "TENDANCE_HAUSSIERE"
    assert result["direction"] == "HAUSSIER"
    assert result["timing"]["informational_only"] is True
    assert result["decision_authority"] == "NONE"


def test_missing_data_is_indeterminate():
    result = Moteur2Regime().analyser(symbol="BTCUSD")
    assert result["regime"] == "INDETERMINE"
    assert result["direction"] == "NEUTRE"
