from app import services


def test_smart_money_supports_arbitrary_period_pair():
    out = services.smart_money("demo", "2025Q4", "2025Q2")
    assert out["selected_period"] == "2025Q4"
    assert out["compare_period"] == "2025Q2"
    assert out["prior_period"] is None
    assert out["comparison_gap_quarters"] == 2
    assert all(row.get("acceleration") is None for row in out["lifecycle"])
    assert out["lifecycle"]
    assert out["sector_change"]
    assert all("state" in row for row in out["lifecycle"])
    assert all(round(float(row["delta"]), 2) == float(row["delta"]) for row in out["sector_change"])


def test_smart_money_falls_back_to_latest_pair():
    out = services.smart_money("demo", "2099Q4", "2099Q3")
    assert out["selected_period"] == out["periods"][-1]
    assert out["compare_period"] == out["periods"][-2]
    assert out["summary"]["security_count"] >= 0
    assert "p75_coverage" in out["summary"]
