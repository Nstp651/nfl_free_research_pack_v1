from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from source_client import RosettaClient  # noqa: E402


class FakeResponse:
    status_code = 200
    url = "https://prod.rosetta.nbl.com.au/get/nbl/matches/in/season/2025/all?limit=-1"
    headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{
            "id": "fixture-1", "start_time_datetime": "2025-09-18T09:30:00",
            "match_status": "scheduled", "home_team": {"id": "h", "name": "Sydney Kings"},
            "away_team": {"id": "a", "name": "Perth Wildcats"},
            "venue": {"id": "v", "name": "Arena"}, "odds": {"bad": True},
        }], "count": 1}


class FakeSession:
    def __init__(self):
        self.params = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.params = params
        return FakeResponse()


def test_schedule_requests_all_rows_and_normalizes_utc_without_market_fields():
    session = FakeSession(); client = RosettaClient(session=session, rate_limit_rps=100000)
    out = client.schedule(2025, "all")
    assert session.params == {"limit": -1}
    assert out.data[0]["start_time_datetime"] == "2025-09-18T09:30:00Z"
    assert "odds" not in out.data[0]
    assert out.receipt["complete_schedule_request"] is True
