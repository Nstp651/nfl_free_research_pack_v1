from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from zipfile import ZipFile

import pandas as pd
import requests

SCHEMA_VERSION = "tennis_quant_v1"
VALUEBETENNIS_BASE = "https://www.valuebetennis.com/datasets"
UCI_2013_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/00300/Tennis-Major-Tournaments-Match-Statistics.zip"

_MARKET_TOKENS = (
    "odds", "odd_", "book", "bookmaker", "price", "market", "implied",
    "probability", "prediction", "favorite", "favourite", "cote", "yield",
)


@dataclass(frozen=True)
class SourcePolicy:
    key: str
    role: str
    license: str
    automated_access: bool
    production_eligible: bool
    contains_market_data: bool = False
    notes: str = ""


SOURCE_POLICIES = {
    "valuebetennis_open_data": SourcePolicy(
        key="valuebetennis_open_data",
        role="results_metadata",
        license="CC BY 4.0",
        automated_access=True,
        production_eligible=True,
        contains_market_data=True,
        notes="Odds columns exist upstream and must be dropped in-memory before persistence.",
    ),
    "uci_tennis_majors_2013": SourcePolicy(
        key="uci_tennis_majors_2013",
        role="serve_stats_reference_only",
        license="CC BY 4.0",
        automated_access=True,
        production_eligible=False,
        contains_market_data=False,
        notes="Both tours but only the 2013 majors; insufficient depth/freshness for production state training.",
    ),
}


def is_market_column(name: str) -> bool:
    n = name.strip().lower()
    return any(token in n for token in _MARKET_TOKENS)


def strip_market_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Irreversibly remove market-derived columns before research/model persistence."""
    drop = [c for c in df.columns if is_market_column(str(c))]
    clean = df.drop(columns=drop, errors="ignore").copy()
    remaining = [c for c in clean.columns if is_market_column(str(c))]
    if remaining:
        raise AssertionError(f"market columns survived sanitization: {remaining}")
    return clean


def assert_market_blind(df: pd.DataFrame) -> None:
    bad = [c for c in df.columns if is_market_column(str(c))]
    if bad:
        raise AssertionError(f"market-derived columns prohibited in quantitative pack: {bad}")


def _get(url: str, timeout: int = 45) -> requests.Response:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "KJ-Tennis-V1/1.0 (+private quantitative research)"},
    )
    response.raise_for_status()
    return response


class ValuebetennisSource:
    source_key = "valuebetennis_open_data"

    @staticmethod
    def url(year: int) -> str:
        return f"{VALUEBETENNIS_BASE}/valuebetennis-matchs-{year}.csv"

    def fetch_year(self, year: int) -> pd.DataFrame:
        response = _get(self.url(year))
        raw = pd.read_csv(BytesIO(response.content), low_memory=False)
        # Upstream includes Pinnacle market columns. Remove them immediately;
        # the unsanitized table is never returned or persisted.
        clean = strip_market_columns(raw)
        return self.normalize(clean, retrieved_at=pd.Timestamp.now(tz="UTC"))

    def normalize(self, df: pd.DataFrame, retrieved_at: pd.Timestamp) -> pd.DataFrame:
        assert_market_blind(df)
        aliases = {
            "match_id": "source_record_id",
            "date": "event_date",
            "tournoi": "tournament_name",
            "tournoi_id": "tournament_id",
            "categorie": "category",
            "genre": "tour",
            "surface": "surface",
            "tour": "round_raw",
            "joueur1": "player_a_name",
            "joueur1_id": "player_a_id",
            "joueur2": "player_b_name",
            "joueur2_id": "player_b_id",
            "vainqueur_id": "winner_id",
            "score": "score",
            "duree_min": "duration_minutes",
        }
        missing = [c for c in aliases if c not in df.columns]
        if missing:
            raise ValueError(f"Valuebetennis schema drift; missing columns: {missing}")
        out = df[list(aliases)].rename(columns=aliases).copy()
        out["event_date"] = pd.to_datetime(out["event_date"], utc=True, errors="coerce")
        out["tour"] = out["tour"].astype(str).str.upper()
        out["surface"] = out["surface"].astype(str).str.lower().replace(
            {"dur": "hard", "terre": "clay", "gazon": "grass"}
        )
        out["source"] = self.source_key
        out["retrieved_at_utc"] = retrieved_at
        out["schema_version"] = SCHEMA_VERSION
        out["quality_flags"] = out.apply(self._quality_flags, axis=1)
        assert_market_blind(out)
        return out

    @staticmethod
    def _quality_flags(row: pd.Series) -> str:
        flags: list[str] = []
        if pd.isna(row.get("event_date")):
            flags.append("missing_event_date")
        if pd.isna(row.get("player_a_id")) or pd.isna(row.get("player_b_id")):
            flags.append("missing_player_id")
        if pd.isna(row.get("winner_id")):
            flags.append("missing_winner")
        if pd.isna(row.get("duration_minutes")):
            flags.append("missing_duration")
        return "|".join(flags) if flags else "ok"


class UCI2013ServeStatsSource:
    source_key = "uci_tennis_majors_2013"

    def fetch(self) -> pd.DataFrame:
        response = _get(UCI_2013_URL)
        frames: list[pd.DataFrame] = []
        with ZipFile(BytesIO(response.content)) as zf:
            for name in sorted(zf.namelist()):
                if name.lower().endswith(".csv"):
                    with zf.open(name) as f:
                        frame = pd.read_csv(f)
                    frames.append(self.normalize(frame, name, pd.Timestamp.now(tz="UTC")))
        if not frames:
            raise ValueError("UCI archive contained no CSV files")
        out = pd.concat(frames, ignore_index=True)
        assert_market_blind(out)
        return out

    @staticmethod
    def _canonical(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(name).lower())

    def normalize(self, df: pd.DataFrame, filename: str, retrieved_at: pd.Timestamp) -> pd.DataFrame:
        cols = {self._canonical(c): c for c in df.columns}

        def find(*names: str) -> str | None:
            for name in names:
                key = self._canonical(name)
                if key in cols:
                    return cols[key]
            return None

        p1 = find("Player1")
        p2 = find("Player2")
        result = find("Result")
        if any(x is None for x in (p1, p2, result)):
            raise ValueError(f"UCI schema drift in {filename}: missing player/result columns")

        def num(*names: str) -> pd.Series:
            c = find(*names)
            return pd.to_numeric(df[c], errors="coerce") if c else pd.Series([pd.NA] * len(df), dtype="Float64")

        lower = filename.lower()
        tour = "WTA" if "women" in lower else "ATP"
        tournament = (
            "Australian Open" if "ausopen" in lower else
            "Roland Garros" if "frenchopen" in lower else
            "Wimbledon" if "wimbledon" in lower else
            "US Open"
        )
        surface = "clay" if tournament == "Roland Garros" else "grass" if tournament == "Wimbledon" else "hard"

        out = pd.DataFrame({
            "source_record_id": [f"{filename}:{i}" for i in range(len(df))],
            "event_year": 2013,
            "event_date": pd.NaT,
            "tour": tour,
            "tournament_name": tournament,
            "surface": surface,
            "player_a_name": df[p1].astype(str),
            "player_b_name": df[p2].astype(str),
            "result_code": pd.to_numeric(df[result], errors="coerce"),
            "a_first_serve_pct": num("FSP.1", "FSP1"),
            "a_first_serve_points_won": num("FSW.1", "FSW1"),
            "a_second_serve_pct": num("SSP.1", "SSP1"),
            "a_second_serve_points_won": num("SSW.1", "SSW1"),
            "a_aces": num("ACE.1", "ACE1"),
            "a_double_faults": num("DBF.1", "DBF1"),
            "a_break_points_created": num("BPC.1", "BPC1"),
            "a_break_points_won": num("BPW.1", "BPW1"),
            "b_first_serve_pct": num("FSP.2", "FSP2"),
            "b_first_serve_points_won": num("FSW.2", "FSW2"),
            "b_second_serve_pct": num("SSP.2", "SSP2"),
            "b_second_serve_points_won": num("SSW.2", "SSW2"),
            "b_aces": num("ACE.2", "ACE2"),
            "b_double_faults": num("DBF.2", "DBF2"),
            "b_break_points_created": num("BPC.2", "BPC2"),
            "b_break_points_won": num("BPW.2", "BPW2"),
            "source": self.source_key,
            "retrieved_at_utc": retrieved_at,
            "schema_version": SCHEMA_VERSION,
            "quality_flags": "reference_only|missing_exact_match_date|insufficient_for_production",
        })
        return out
