"""The flow section of the chatbot brief, and the summary that feeds it."""

from ingest.chatbot_brief import render_brief
from ingest.report import flow_summary, loss_growth


def _station(x, loss, wheels=None, rev=0.0):
    return {"x_m": x, "lossIntegralM2": loss, "lossAreaM2": loss * 2, "wheels": wheels or {}, "reverseFlowAreaM2": rev, "minU_ms": -3.0, "vortices": []}


def _flow():
    wheel = {"lossIntegralM2": 0.2, "lossAreaM2": 0.3, "minCpt": 0.1, "widthM": 0.4}
    return {
        "stations": [
            _station(0.0, 0.0),
            _station(0.1, 0.1),
            _station(0.2, 0.5, {"front": wheel}),
            _station(0.3, 0.6, {"front": wheel}, rev=0.1),
        ],
        "vortexTracks": [
            {
                "turn": "przeciwnie do ruchu wskazówek",
                "fromX_m": 0.1,
                "toX_m": 0.3,
                "start": {"y_m": -0.5, "z_m": 0.3},
                "end": {"y_m": -0.5, "z_m": 0.3},
                "strongestAtX_m": 0.2,
                "peakCirculationM2s": -2.5,
                "region": "pod podłogą",
                "points": [{"x_m": 0.1}],
            }
        ],
    }


def _walls():
    return {"strips": {"fw": [{"x_m": 0.15, "Cd": 0.01, "downforceCoeff": 0.1}, {"x_m": 0.25, "Cd": 0.3, "downforceCoeff": 0.2}]}}


def test_loss_growth_names_the_part_that_makes_drag_in_the_biggest_strip():
    growth = loss_growth(_flow(), _walls())
    assert growth[0]["fromX_m"] == 0.1 and growth[0]["toX_m"] == 0.2
    assert growth[0]["growthM2"] == 0.4
    assert growth[0]["dragMostlyFrom"] == "przednie skrzydło"


def test_flow_summary_keeps_only_the_headline_numbers():
    summary = flow_summary(_flow(), _walls())
    assert summary["lossBehindCar"]["integralM2"] == 0.6
    assert "points" not in summary["vortexTracks"][0]
    assert summary["wheelWakes"]["front"]["lossIntegralM2"] == 0.2
    assert summary["reverseFlow"]["atX_m"] == 0.3


def test_brief_without_a_flow_scan_says_how_to_make_one():
    text = render_brief({"identity": {"caseId": "X"}, "kpis": {}})
    assert "## Przepływ wokół auta" in text
    assert "Skanu przepływu nie ma" in text and "python -m ingest report" in text


def test_brief_with_a_flow_scan_lists_losses_vortices_and_wakes():
    pack = {"identity": {"caseId": "X"}, "kpis": {}, "flowSummary": flow_summary(_flow(), _walls())}
    text = render_brief(pack)
    assert "Strata rośnie o" in text
    assert "przednie skrzydło" in text
    assert "pod podłogą" in text
    assert "Za kołem przednim" in text
    assert "Przepływ cofnięty" in text
