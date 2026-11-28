from __future__ import annotations

import pytest

from power_fault_analyzer.diagram.topology_layout import BayLaneRequest, layout_bay_lanes


def test_bay_lanes_separate_overlapping_spans_and_reuse_disjoint_levels():
    requests = (
        BayLaneRequest("CB-1", 0.0, 300.0, 400.0, 180.0),
        BayLaneRequest("DS-1", 0.0, 300.0, 400.0, 220.0),
        BayLaneRequest("LINE-1", 340.0, 620.0, 400.0, 240.0),
    )
    first = layout_bay_lanes(requests)
    second = layout_bay_lanes(requests)
    assert first == second
    assert abs(first["CB-1"] - first["DS-1"]) >= 236.0
    assert first["LINE-1"] == 400.0


def test_bay_lane_layout_rejects_duplicate_or_invalid_requests():
    with pytest.raises(ValueError, match="unique"):
        layout_bay_lanes((
            BayLaneRequest("CB-1", 0.0, 100.0, 0.0, 80.0),
            BayLaneRequest("CB-1", 200.0, 300.0, 0.0, 80.0),
        ))
    with pytest.raises(ValueError, match="positive"):
        BayLaneRequest("bad", 1.0, 1.0, 0.0, 80.0)
