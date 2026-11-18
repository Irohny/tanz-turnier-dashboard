"""Gemeinsame Identitaeten und belegbare Turnierkennzahlen."""

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from urllib.parse import urlsplit


class RoundStage(StrEnum):
    PRELIMINARY = "Vorrunde"
    INTERMEDIATE = "Zwischenrunde"
    QUARTER_FINAL = "Viertelfinale"
    SEMI_FINAL = "Halbfinale"
    FINAL = "Finale/Endrunde"


class PlacementOutcome(StrEnum):
    WINS = "wins"
    LOSSES = "losses"
    TIES = "ties"
    UNKNOWN = "unknown"


PlaceRange = tuple[int, int]

ROUND_ORDER = {
    RoundStage.PRELIMINARY: 0,
    RoundStage.INTERMEDIATE: 1,
    RoundStage.QUARTER_FINAL: 2,
    RoundStage.SEMI_FINAL: 3,
    RoundStage.FINAL: 4,
}
PRE_FINAL_STAGES = (
    RoundStage.PRELIMINARY,
    RoundStage.INTERMEDIATE,
    RoundStage.QUARTER_FINAL,
    RoundStage.SEMI_FINAL,
)
ROUND_BY_CODE = {
    "V": RoundStage.PRELIMINARY,
    "VR": RoundStage.PRELIMINARY,
    "1": RoundStage.PRELIMINARY,
    "Z": RoundStage.INTERMEDIATE,
    "ZR": RoundStage.INTERMEDIATE,
    "2": RoundStage.INTERMEDIATE,
    "H": RoundStage.SEMI_FINAL,
    "HF": RoundStage.SEMI_FINAL,
    "3": RoundStage.SEMI_FINAL,
    "F": RoundStage.FINAL,
}


@dataclass(frozen=True, slots=True)
class JudgeMark:
    dance: str
    code: str
    name: str
    raw: str
    cross: bool


@dataclass(frozen=True, slots=True)
class OpponentResult:
    key: str
    name: str
    club: str
    outcome: PlacementOutcome
    own_place: PlaceRange | None
    opponent_place: PlaceRange | None
    last_seen: date | None


@dataclass(slots=True)
class OpponentSummary:
    name: str
    starts: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    unknown: int = 0
    last_seen: date | None = None
    clubs: set[str] = field(default_factory=set)

    def add(self, result: OpponentResult) -> None:
        self.starts += 1
        if result.outcome is PlacementOutcome.WINS:
            self.wins += 1
        elif result.outcome is PlacementOutcome.LOSSES:
            self.losses += 1
        elif result.outcome is PlacementOutcome.TIES:
            self.ties += 1
        else:
            self.unknown += 1
        if result.club:
            self.clubs.add(result.club)
        if result.last_seen and (
            self.last_seen is None or result.last_seen > self.last_seen
        ):
            self.last_seen = result.last_seen


@dataclass(frozen=True, slots=True)
class PointRecord:
    event_id: str
    title: str
    date: date | None
    source: str
    url: str
    label: str
    points: float


@dataclass(frozen=True, slots=True)
class DanceCross:
    dance: str
    judge: str
    crosses: int
    possible: int


@dataclass(frozen=True, slots=True)
class IndividualJudgeMark:
    dance: str
    judge: str
    mark: str


@dataclass(frozen=True, slots=True)
class JudgeCross:
    judge: str
    crosses: object
    possible: object


@dataclass(frozen=True, slots=True)
class RoundQualification:
    qualified: object
    qualified_for: str
    cutoff: int | None
    margin: int | None
    field_size: int | None


@dataclass(slots=True)
class RoundAccumulator:
    stage: str
    dance_places: dict[str, float] = field(default_factory=dict)
    cross_votes: dict[tuple[str, str], int] = field(default_factory=dict)
    dance_crosses: dict[tuple[str, str], DanceCross] = field(default_factory=dict)
    judges: set[str] = field(default_factory=set)
    reported_crosses: list[int] = field(default_factory=list)
    individual_marks: dict[tuple[str, str], IndividualJudgeMark] = field(
        default_factory=dict
    )
    tabges_crosses: int | None = None
    tabges_votes: int | None = None
    judge_crosses: dict[str, JudgeCross] = field(default_factory=dict)
    field_size: int | None = None
    field_size_priority: int = -1
    place: float | None = None
    judge_count: int | None = None
    expected_votes: set[int] = field(default_factory=set)
    quality_issues: list[str] = field(default_factory=list)
    cross_conflict: bool = False


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower().replace("ß", "ss"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def pair_identity(name: str) -> str:
    name = re.sub(r"\s*\(\d{1,4}\)\s*$", "", name)
    parts = [
        normalize(re.sub(r"^\s*\d{1,4}\s+", "", part))
        for part in name.split("/")
        if part.strip()
    ]
    return " / ".join(sorted(parts)) if len(parts) == 2 else normalize(name)


def competition_key(page: dict) -> tuple[str, str]:
    parsed = urlsplit(str(page.get("url", "")))
    origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    directory = parsed.path.rsplit("/", 1)[0].rstrip("/") + "/"
    return origin, directory


def canonical_round(value: str) -> RoundStage | str | None:
    text = normalize(value)
    if "zwischen" in text or re.search(r"\bzr\b", text):
        stage = RoundStage.INTERMEDIATE
    elif "vorschluss" in text or "halb" in text or re.search(r"\bhf\b", text):
        stage = RoundStage.SEMI_FINAL
    elif "viertel" in text:
        stage = RoundStage.QUARTER_FINAL
    elif "vor" in text or re.search(r"\bvr\b", text):
        stage = RoundStage.PRELIMINARY
    elif "final" in text or "endrunde" in text:
        stage = RoundStage.FINAL
    else:
        return None
    number = re.search(r"(?:^(\d+)\s+zwischenrunde|zwischenrunde\s+(\d+)\b)", text)
    if number:
        return f"{number.group(1) or number.group(2)}. {stage}"
    return stage


def round_type(value: str) -> RoundStage | str:
    canonical = canonical_round(value)
    if isinstance(canonical, RoundStage):
        return canonical
    return re.sub(r"^\d+\.\s*", "", canonical or value)


def round_sort_key(value: str) -> tuple[int, int, str]:
    number = re.match(r"^(\d+)\.", value)
    stage = round_type(value)
    return (
        (
            ROUND_ORDER.get(stage, len(ROUND_ORDER))
            if isinstance(stage, RoundStage)
            else len(ROUND_ORDER)
        ),
        int(number.group(1)) if number else 0,
        value,
    )


def integer_value(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = int(value)
    except (ValueError, OverflowError):
        return None
    if isinstance(value, float) and value != parsed:
        return None
    return parsed


def place_range(value: object) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d+)(?:[.,]0)?\.?(?:\s*[-–]\s*(\d+)\.?)?\s*", str(value))
    if match is None:
        return None
    first = int(match.group(1))
    last = int(match.group(2) or first)
    return (first, last) if 1 <= first <= last else None


def pair_place(pages: list[dict], pair: dict) -> tuple[int, int] | None:
    identity = pair_identity(str(pair.get("paar") or pair.get("name") or ""))
    places: set[tuple[int, int]] = set()
    for page in pages:
        source = urlsplit(page.get("url", "")).path.rsplit("/", 1)[-1].lower()
        if source not in {"ergwert.htm", "tabges.htm"}:
            continue
        candidates = [*page.get("paare", []), *page.get("paar_ergebnisse", [])]
        for candidate in candidates:
            name = str(candidate.get("paar") or candidate.get("name") or "")
            if not identity or pair_identity(name) != identity:
                continue
            bounds = None
            if candidate.get("platz_von") is not None:
                bounds = place_range(
                    f"{candidate['platz_von']}-{candidate.get('platz_bis', candidate['platz_von'])}"
                )
            fields = {
                **candidate.get("alle_weiteren_spalten", {}),
                **candidate.get("platzierung_spalten", {}),
            }
            if source == "ergwert.htm":
                for key, value in fields.items():
                    if key.strip().lower() == "platz":
                        bounds = place_range(value)
            elif "Platz von" in fields:
                first = fields["Platz von"]
                last = fields.get("Platz bis")
                bounds = place_range(f"{first}-{last}" if last else first)
            if bounds:
                places.add(bounds)
    return next(iter(places)) if len(places) == 1 else None


def compare_places(
    own: PlaceRange | None, other: PlaceRange | None
) -> PlacementOutcome:
    if own is None or other is None:
        return PlacementOutcome.UNKNOWN
    if own == other:
        return PlacementOutcome.TIES
    if own[1] < other[0]:
        return PlacementOutcome.WINS
    if other[1] < own[0]:
        return PlacementOutcome.LOSSES
    return PlacementOutcome.UNKNOWN


def normalized_rank(rank: float, field_size: int) -> float | None:
    if not math.isfinite(rank) or field_size < 2 or not 1 <= rank <= field_size:
        return None
    return 1 - (rank - 1) / (field_size - 1)


def qualification_cutoff(
    records: dict[str, dict], complete: bool, qualified_ids: set[str] | None = None
) -> int | None:
    sizes = {integer_value(result.get("feldgroesse")) for result in records.values()}
    if not complete or not records or sizes != {len(records)}:
        return None
    if any(
        result.get("rundendaten_vollstaendig") is False for result in records.values()
    ):
        return None
    flags = [result.get("qualifiziert") for result in records.values()]
    if any(flag is not None for flag in flags):
        if not all(isinstance(flag, bool) for flag in flags):
            return None
        qualified_ids = {
            key for key, result in records.items() if result["qualifiziert"]
        }
    if not qualified_ids or not qualified_ids.issubset(records):
        return None
    crosses = {
        key: integer_value(result.get("kreuze_anzahl"))
        for key, result in records.items()
    }
    if any(value is None or value < 0 for value in crosses.values()):
        return None
    qualified_crosses = [crosses[key] for key in qualified_ids]
    cutoff = min(value for value in qualified_crosses if value is not None)
    if any(
        value is not None and value > cutoff
        for key, value in crosses.items()
        if key not in qualified_ids
    ):
        return None
    return cutoff
