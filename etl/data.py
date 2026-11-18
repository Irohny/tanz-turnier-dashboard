"""Bereitet archivierte Turnierseiten für das Streamlit-Dashboard auf."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from statistics import median
from typing import Any

from etl.archiv import clean_judge_name
from etl.auswertung import (
    competition_key,
    cross_count,
    cross_vote,
    explicit_place,
    judge_cross_maximum,
    normalize,
    normalized_judge_cross_rate,
    normalized_rank,
    numeric_value,
    pair_matches,
    result_fields,
    result_judges,
    round_name,
    source_name,
)
from etl.domain import (
    PRE_FINAL_STAGES,
    DanceCross,
    IndividualJudgeMark,
    JudgeCross,
    JudgeMark,
    OpponentResult,
    OpponentSummary,
    PlacementOutcome,
    PointRecord,
    RoundAccumulator,
    RoundQualification,
    RoundStage,
    compare_places,
    integer_value,
    pair_identity,
    pair_place,
    place_range,
    qualification_cutoff,
    round_sort_key,
    round_type,
)

Page = dict[str, Any]
EventKey = tuple[str, str]

_DATE_RE = re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b")
_DISCIPLINE_RE = re.compile(r"\b(Standard|Latein|Kombination)\b", re.IGNORECASE)
_DANCE_NAMES = {
    "lw": "Langsamer Walzer",
    "langsame walzer": "Langsamer Walzer",
    "langsamer walzer": "Langsamer Walzer",
    "tg": "Tango",
    "tango": "Tango",
    "ww": "Wiener Walzer",
    "wiener walzer": "Wiener Walzer",
    "sf": "Slowfox",
    "slowfox": "Slowfox",
    "qs": "Quickstep",
    "quickstep": "Quickstep",
}


@dataclass(frozen=True, slots=True)
class EventSummary:
    id: str
    key: EventKey
    title: str
    city: str
    date: date | None
    group: str
    start_class: str
    discipline: str
    place: float | None
    place_range: tuple[int, int] | None
    field_size: int | None
    normalized_place: float | None
    target_index: int | None
    rank_pairs: list[dict[str, Any]]
    pages: list[Page]
    results: list[tuple[Page, dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class RoundSummary:
    stage: str
    crosses: int | None
    votes: int | None
    cross_totals_derived: bool
    cross_rate: float | None
    field_size: int | None
    place: float | None
    normalized_place: float | None
    dance_places: dict[str, float]
    judges: list[str]
    dance_crosses: list[dict[str, Any]]
    individual_marks: list[dict[str, Any]]
    judge_crosses: list[dict[str, Any]]
    qualified: object
    qualified_for: str
    qualification_inferred: bool
    cross_cutoff: int | None
    cross_margin: int | None
    cross_conflict: bool
    quality_issues: list[str]


@dataclass(frozen=True, slots=True)
class DanceObservation:
    event_id: str
    title: str
    date: date | None
    city: str
    group: str
    discipline: str
    stage: str
    score: float
    url: str
    place: float
    field_size: int


@dataclass(frozen=True, slots=True)
class DanceSummary:
    dance: str
    normalized_place: float
    observations: int
    events: int


@dataclass(frozen=True, slots=True)
class DanceClassSummary(DanceSummary):
    start_class: str


@dataclass(frozen=True, slots=True)
class DanceHistory:
    dance: str
    start_class: str
    event_id: str
    title: str
    date: date | None
    city: str
    group: str
    discipline: str
    stage: str
    normalized_place: float
    url: str
    place: float
    field_size: int


@dataclass(frozen=True, slots=True)
class QualityIssue:
    tournament: str
    round: str
    note: str
    source: str
    event_id: str = ""
    code: str = "incomplete_round_data"
    severity: str = "unvollständig"
    action: str = "Rundenbeleg und Quelldaten prüfen."

    def to_dict(self) -> dict[str, str]:
        return {
            "Event-ID": self.event_id,
            "Code": self.code,
            "Status": self.severity,
            "Turnier": self.tournament,
            "Runde": self.round,
            "Hinweis": self.note,
            "Quelle": self.source,
            "Nächster Schritt": self.action,
        }


@dataclass(frozen=True, slots=True)
class OpponentEvidence:
    key: str
    name: str
    club: str
    event_id: str
    group: str
    discipline: str
    starts: int
    wins: int
    losses: int
    ties: int
    unknown: int
    own_place: tuple[int, int] | None
    opponent_place: tuple[int, int] | None
    outcome: str
    last_seen: date | None
    title: str
    date: date | None
    city: str
    sources: list[str]


@dataclass(frozen=True, slots=True)
class JudgeEvidence:
    name: str
    event_id: str
    title: str
    stage: str
    dance: str
    score: float
    panel_median: float
    deviation_pp: float
    url: str


@dataclass(frozen=True, slots=True)
class JudgeSummary:
    name: str
    deviation_pp: float
    observations: int
    tournaments: int
    marks: int
    raw_marks: int
    raw_tournaments: int


@dataclass(frozen=True, slots=True)
class OpponentRow:
    name: str
    starts: int
    wins: int
    losses: int
    ties: int
    unknown: int
    last_seen: date | None
    club: str


@dataclass(frozen=True, slots=True)
class RoundCrossSummary:
    stage: str
    cross_rate: float
    observations: int
    events: int


def _page_source(page: Page) -> str:
    return source_name(page).lower()


def _event_date(title: str) -> date | None:
    match = _DATE_RE.search(title)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d.%m.%Y").date()
    except ValueError:
        return None


def _category(title: str) -> tuple[str, str]:
    without_date = _DATE_RE.sub("", title).strip(" .-")
    match = _DISCIPLINE_RE.search(without_date)
    if not match:
        return without_date or "Nicht angegeben", "Nicht angegeben"
    group = f"{without_date[: match.start()]} {without_date[match.end() :]}".strip(
        " .-"
    )
    return group or "Nicht angegeben", match.group(1).capitalize()


def _start_class(group: str) -> str:
    match = re.search(r"(?:^|[\s.])([A-Z])$", group.strip(), re.IGNORECASE)
    return match.group(1).upper() if match else group.strip() or "Nicht angegeben"


def _pair_name(pair: dict[str, Any]) -> str:
    name = str(pair.get("name") or pair.get("paar") or "").strip()
    return re.sub(r"^\s*\d{1,4}\s+", "", name)


def _pair_key(name: str) -> str:
    return pair_identity(name)


def pair_options(pages: list[Page]) -> list[str]:
    """Ergaenzt Startlisten um Paare aus allen verfuegbaren Ergebnisquellen."""
    candidates: list[str] = []
    for page in pages:
        if _page_source(page) == "starter.htm":
            candidates.extend(
                _pair_name(pair)
                for pair in page.get("paare", [])
                if "/" in _pair_name(pair)
            )

    for page in pages:
        candidates.extend(
            _pair_name(pair)
            for pair in (*page.get("paare", []), *page.get("paar_ergebnisse", []))
            if "/" in _pair_name(pair)
        )

    by_identity: dict[str, str] = {}
    for name in candidates:
        if identity := _pair_key(name):
            by_identity.setdefault(identity, name)
    return sorted(by_identity.values(), key=str.casefold)


def _group_pages(pages: list[Page]) -> dict[EventKey, list[Page]]:
    grouped: dict[EventKey, list[Page]] = defaultdict(list)
    for page in pages:
        grouped[competition_key(page)].append(page)
    return grouped


def _event_matches_pair(pages: list[Page], pair_query: str) -> bool:
    return any(
        pair_matches(pair_query, pair)
        for page in pages
        for pair in (
            *page.get("paare", []),
            *page.get("paar_ergebnisse", []),
        )
    )


def filter_tournaments_for_pair(pages: list[Page], pair_query: str) -> list[Page]:
    """Keep every page from competitions where the queried pair is present."""
    if not pair_query.strip():
        raise ValueError("Für die Turnierfilterung muss ein Paar angegeben werden.")

    matching_keys = {
        key
        for key, event_pages in _group_pages(pages).items()
        if _event_matches_pair(event_pages, pair_query)
    }
    return [page for page in pages if competition_key(page) in matching_keys]


def _matching_results(
    pages: list[Page], pair_query: str
) -> list[tuple[Page, dict[str, Any]]]:
    return [
        (page, result)
        for page in pages
        for result in page.get("paar_ergebnisse", [])
        if pair_matches(pair_query, result)
    ]


def _field_size(result: dict[str, Any]) -> int | None:
    value = integer_value(result.get("feldgroesse"))
    return value if value is not None and value > 0 else None


def _integer_or_none(value: Any) -> int | None:
    return integer_value(value)


def _dance_name(value: str) -> str:
    cleaned = value.strip()
    return _DANCE_NAMES.get(normalize(cleaned), cleaned or "Tanz nicht angegeben")


def _dance_placements(result: dict[str, Any]) -> dict[str, float]:
    placements: dict[str, float] = {}
    for key, value in result_fields(result).items():
        parts = key.rsplit("|", 1)
        if len(parts) != 2 or normalize(parts[1]) != "su":
            continue
        place = numeric_value(value)
        if place is not None:
            placements.setdefault(_dance_name(parts[0]), place)
    return placements


def _judge_marks(result: dict[str, Any]) -> list[JudgeMark]:
    structured = result.get("richter_wertungen")
    candidates: list[JudgeMark]
    if structured:
        candidates = [
            JudgeMark(
                dance=_dance_name(str(mark.get("tanz") or result.get("tanz", ""))),
                code=str(mark.get("kuerzel", "")).strip(),
                name=clean_judge_name(
                    str(mark.get("kuerzel", "")).strip(),
                    str(mark.get("name", "")),
                ),
                raw=str(mark.get("rohwert", "")),
                cross=bool(mark.get("kreuz"))
                or cross_count(mark.get("rohwert", "")) > 0,
            )
            for mark in structured
        ]
    else:
        candidates = [
            JudgeMark(
                dance=_dance_name(dance),
                code=code,
                name=clean_judge_name(code, name),
                raw=raw,
                cross=cross_count(raw) > 0,
            )
            for dance, code, name, raw in result_judges(result)
        ]

    unique: dict[tuple[str, str], JudgeMark] = {}
    for mark in candidates:
        identity = (
            mark.dance,
            normalize(mark.name) or f"code:{mark.code.casefold()}",
        )
        unique.setdefault(identity, mark)
    return list(unique.values())


def judge_meetings(
    events: list[dict[str, Any]], judge_name: str
) -> list[dict[str, Any]]:
    identity = normalize(judge_name)
    if not identity:
        return []
    meetings = []
    for event in events:
        names = [
            str(judge.get("name", ""))
            for page in event["pages"]
            for judge in page.get("wertungsrichter", [])
        ]
        for _, result in event["results"]:
            names.extend(mark.name for mark in _judge_marks(result))
            names.extend(
                clean_judge_name(
                    str(mark.get("kuerzel", "")), str(mark.get("name", ""))
                )
                for mark in result.get("richter_kreuze", [])
            )
        if any(normalize(name) == identity for name in names):
            meetings.append(event)
    return meetings


def _canonical_rank_pair(
    pair: dict[str, Any], starter_pairs: list[dict[str, Any]]
) -> tuple[str, str]:
    for starter_pair in starter_pairs:
        name = _pair_name(starter_pair)
        if name and pair_matches(name, pair):
            return (
                _pair_name(pair) or name,
                str(pair.get("verein") or starter_pair.get("verein") or "").strip(),
            )
    return _pair_name(pair), str(pair.get("verein") or "").strip()


def _event_summary(
    key: EventKey, pages: list[Page], pair_query: str
) -> dict[str, Any] | None:
    if not _event_matches_pair(pages, pair_query):
        return None

    title = next(
        (str(page.get("titel", "")) for page in pages if page.get("titel")), ""
    )
    rank_page = next(
        (
            page
            for page in pages
            if _page_source(page) == "ergwert.htm" and page.get("paare")
        ),
        None,
    )
    starter_page = next(
        (
            page
            for page in pages
            if _page_source(page) == "starter.htm" and page.get("paare")
        ),
        None,
    )
    rank_pairs = rank_page.get("paare", []) if rank_page else []
    starter_pairs = starter_page.get("paare", []) if starter_page else []
    target_index = next(
        (
            index
            for index, pair in enumerate(rank_pairs)
            if pair_matches(pair_query, pair)
        ),
        None,
    )
    results = _matching_results(pages, pair_query)
    target_pair = next(
        (
            pair
            for page in pages
            for pair in page.get("paare", [])
            if pair_matches(pair_query, pair)
        ),
        {"paar": results[0][1].get("paar", "")} if results else {},
    )
    bounds = pair_place(pages, target_pair)
    place = float(bounds[0]) if bounds and bounds[0] == bounds[1] else None

    result_sizes = [
        size for _, result in results if (size := _field_size(result)) is not None
    ]
    field_size = (
        len(starter_pairs)
        or len(rank_pairs)
        or (max(result_sizes) if result_sizes else None)
    )
    normalized_place = (
        normalized_rank(place, field_size)
        if place is not None and field_size is not None
        else None
    )
    group, discipline = _category(title)
    event_id = f"{key[0]}|{key[1]}"
    return EventSummary(
        id=event_id,
        key=key,
        title=title or key[1] or "Turnier ohne Titel",
        city=next(
            (
                str(page.get("stadt", "")).strip()
                for page in pages
                if str(page.get("stadt", "")).strip()
            ),
            "",
        ),
        date=_event_date(title),
        group=group,
        start_class=_start_class(group),
        discipline=discipline,
        place=place,
        place_range=bounds,
        field_size=field_size,
        normalized_place=normalized_place,
        target_index=target_index,
        rank_pairs=rank_pairs,
        pages=pages,
        results=results,
    ).to_dict()


def _tabges_round_details(
    event: dict[str, Any], pair_query: str
) -> dict[str, RoundQualification]:
    records_by_stage: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    complete_by_stage: dict[str, bool] = {}
    for page in sorted(
        event["pages"], key=lambda page: _page_source(page) == "tabges.htm"
    ):
        if _page_source(page) not in {"tabges.htm", "ergwert.htm"}:
            continue
        for result in page.get("paar_ergebnisse", []):
            if result.get("runde") == "Gesamtwertung":
                continue
            if "kreuze_anzahl" not in result:
                continue
            stage = round_name(page, result)
            pair_id = str(
                result.get("paar_id")
                or result.get("startnr")
                or _pair_key(_pair_name(result))
            )
            records_by_stage[stage][pair_id] = result
            complete_by_stage[stage] = complete_by_stage.get(stage, True) and bool(
                page.get("alle_paare_erfasst", False)
            )

    details: dict[str, RoundQualification] = {}
    for stage, records in records_by_stage.items():
        target = next(
            (result for result in records.values() if pair_matches(pair_query, result)),
            None,
        )
        if target is None:
            continue

        margin = None
        field_size = _field_size(target)
        following = sorted(
            (
                candidate
                for candidate in records_by_stage
                if round_sort_key(candidate) > round_sort_key(stage)
            ),
            key=round_sort_key,
        )
        next_records = records_by_stage[following[0]] if following else {}
        next_complete = (
            bool(next_records)
            and complete_by_stage.get(following[0], False)
            and all(
                _field_size(result) == len(next_records)
                for result in next_records.values()
            )
        )
        cutoff = qualification_cutoff(
            records,
            complete_by_stage.get(stage, False),
            set(next_records) if next_complete else None,
        )
        target_crosses = _integer_or_none(target.get("kreuze_anzahl"))
        if cutoff is not None and target_crosses is not None:
            margin = target_crosses - cutoff

        details[stage] = RoundQualification(
            qualified=target.get("qualifiziert"),
            qualified_for=str(target.get("qualifiziert_fuer", "")),
            cutoff=cutoff,
            margin=margin,
            field_size=field_size,
        )
    return details


def _build_rounds(event: dict[str, Any], pair_query: str) -> list[dict[str, Any]]:
    field_size_priority = {
        "tabges.htm": 3,
        "ergwert.htm": 2,
        "wert_er.htm": 1,
        "erg.htm": 0,
    }
    rounds: dict[str, RoundAccumulator] = {}
    tabges_details = _tabges_round_details(event, pair_query)
    for page, result in event["results"]:
        source = _page_source(page)
        if source == "starter.htm" or (
            source == "tabges.htm"
            and (
                result.get("runde") == "Gesamtwertung"
                or "moegliche_kreuzstimmen" not in result
            )
        ):
            continue
        stage = round_name(page, result)
        item = rounds.setdefault(stage, RoundAccumulator(stage=stage))
        current_size = _field_size(result)
        current_priority = field_size_priority.get(source, -1)
        if current_size is not None and current_priority >= item.field_size_priority:
            item.field_size = current_size
            item.field_size_priority = current_priority
        judge_count = _integer_or_none(result.get("richteranzahl"))
        if judge_count is not None:
            item.judge_count = max(item.judge_count or 0, judge_count)
        dance_count = _integer_or_none(result.get("tanzanzahl"))
        if source == "ergwert.htm" and judge_count and dance_count:
            item.expected_votes.add(judge_count * dance_count)
        if source == "ergwert.htm" and result.get("wertungen_vollstaendig") is True:
            item.expected_votes.add(len(_judge_marks(result)))
        for mark in _judge_marks(result):
            judge_identity = normalize(mark.name)
            if mark.name:
                item.judges.add(mark.name)
            vote = cross_vote(mark.raw, stage)
            if source == "ergwert.htm" and vote is not None:
                mark_key = (mark.dance, judge_identity or mark.code.casefold())
                item.cross_votes.setdefault(mark_key, vote)
                item.dance_crosses.setdefault(
                    mark_key,
                    DanceCross(
                        dance=mark.dance,
                        judge=mark.name or mark.code,
                        crosses=vote,
                        possible=1,
                    ),
                )
            elif source == "wert_er.htm":
                mark_key = (
                    mark.dance,
                    judge_identity or mark.code.casefold(),
                )
                item.individual_marks.setdefault(
                    mark_key,
                    IndividualJudgeMark(
                        dance=mark.dance,
                        judge=mark.name or mark.code,
                        mark=mark.raw,
                    ),
                )
        if source == "ergwert.htm":
            place_text = explicit_place([(page, result)])
            bounds = place_range(place_text)
            place = float(bounds[0]) if bounds and bounds[0] == bounds[1] else None
            if place is not None:
                item.place = place
            for dance, place in _dance_placements(result).items():
                item.dance_places.setdefault(dance, place)
            try:
                reported = int(result.get("kreuze_anzahl", 0) or 0)
            except (TypeError, ValueError):
                reported = 0
            if reported and round_type(stage) is not RoundStage.FINAL:
                item.reported_crosses.append(reported)
        elif source == "tabges.htm":
            crosses = _integer_or_none(result.get("kreuze_anzahl"))
            votes = _integer_or_none(result.get("moegliche_kreuzstimmen"))
            if crosses is not None:
                item.tabges_crosses = crosses
            if votes is not None:
                item.tabges_votes = votes
            for mark in result.get("richter_kreuze", []):
                name = str(mark.get("name", "")).strip()
                code = str(mark.get("kuerzel", "")).strip()
                identity = normalize(name) or f"code:{code.casefold()}"
                if name:
                    item.judges.add(name)
                item.judge_crosses.setdefault(
                    identity,
                    JudgeCross(
                        judge=name or code,
                        crosses=mark.get("kreuze"),
                        possible=mark.get("max_kreuze"),
                    ),
                )

    observed_stages = {
        stage
        for stage, item in rounds.items()
        if item.individual_marks
        or item.dance_places
        or item.cross_votes
        or item.judge_crosses
        or item.tabges_crosses is not None
        or item.place is not None
    }
    output = []
    for item in rounds.values():
        vote_values = list(item.cross_votes.values())
        crosses = None
        votes: int | None = None
        expected = item.expected_votes
        if vote_values:
            if len(expected) == 1 and len(vote_values) == next(iter(expected)):
                crosses, votes = sum(vote_values), len(vote_values)
            else:
                item.quality_issues.append(
                    "Einzelzellen belegen keine vollständige Runden-Stimmenzahl."
                )
        if crosses is None and item.reported_crosses:
            crosses = max(item.reported_crosses)
        if item.tabges_crosses is not None:
            crosses = item.tabges_crosses
        if item.tabges_votes is not None:
            votes = item.tabges_votes

        derived_cross_totals = False
        judge_crosses = list(item.judge_crosses.values())
        judge_count = item.judge_count
        judge_totals = [
            (total, maximum)
            for mark in judge_crosses
            if (total := _integer_or_none(mark.crosses)) is not None
            and (maximum := _integer_or_none(mark.possible)) is not None
            and maximum > 0
            and 0 <= total <= maximum
        ]
        if (
            judge_count
            and len(judge_crosses) == judge_count
            and len(judge_totals) == judge_count
        ):
            judge_total_crosses = sum(total[0] for total in judge_totals)
            judge_total_votes = sum(total[1] for total in judge_totals)
            consistent_crosses = crosses is None or crosses == judge_total_crosses
            consistent_votes = votes is None or votes == judge_total_votes
            if consistent_crosses and consistent_votes:
                if crosses is None:
                    crosses = judge_total_crosses
                    derived_cross_totals = True
                if votes is None:
                    votes = judge_total_votes
                    derived_cross_totals = True
            else:
                item.quality_issues.append(
                    "Gesamtstimmen und Richterkreuze widersprechen sich."
                )
                item.cross_conflict = True

        if crosses is not None and votes is not None and not 0 <= crosses <= votes:
            item.quality_issues.append(
                "Kreuzsumme liegt außerhalb der möglichen Stimmen."
            )
            item.cross_conflict = True

        details = tabges_details.get(item.stage)
        dance_places = item.dance_places
        field_size = (details.field_size if details else None) or item.field_size
        place = item.place
        if place is not None and field_size is not None and place > field_size:
            place = None

        qualified = details.qualified if details else None
        qualified_for = details.qualified_for if details else ""
        qualification_inferred = False
        current_stage_order = round_sort_key(item.stage)
        if qualified is None and round_type(item.stage) in PRE_FINAL_STAGES:
            later_stages = sorted(
                (
                    stage
                    for stage in observed_stages
                    if round_sort_key(stage) > current_stage_order
                    and isinstance(round_type(stage), RoundStage)
                ),
                key=round_sort_key,
            )
            if later_stages:
                qualified = True
                qualified_for = later_stages[0]
                qualification_inferred = True

        normalized_place = (
            normalized_rank(place, field_size)
            if place is not None and field_size is not None and place <= field_size
            else None
        )
        if not any(
            (
                crosses is not None,
                votes is not None,
                place is not None,
                dance_places,
                item.judges,
                item.individual_marks,
                item.judge_crosses,
                qualified is not None,
                details is not None and details.cutoff is not None,
            )
        ):
            continue
        output.append(
            asdict(
                RoundSummary(
                    stage=item.stage,
                    crosses=crosses,
                    votes=votes,
                    cross_totals_derived=derived_cross_totals,
                    cross_rate=(
                        crosses / votes
                        if votes
                        and crosses is not None
                        and 0 <= crosses <= votes
                        and not item.cross_conflict
                        else None
                    ),
                    field_size=field_size,
                    place=place,
                    normalized_place=normalized_place,
                    dance_places=dance_places,
                    judges=sorted(item.judges),
                    dance_crosses=[
                        asdict(mark) for mark in item.dance_crosses.values()
                    ],
                    individual_marks=[
                        asdict(mark) for mark in item.individual_marks.values()
                    ],
                    judge_crosses=[
                        asdict(mark) for mark in item.judge_crosses.values()
                    ],
                    qualified=qualified,
                    qualified_for=qualified_for,
                    qualification_inferred=qualification_inferred,
                    cross_cutoff=(
                        details.cutoff if details and not item.cross_conflict else None
                    ),
                    cross_margin=(
                        details.margin if details and not item.cross_conflict else None
                    ),
                    cross_conflict=item.cross_conflict,
                    quality_issues=item.quality_issues,
                )
            )
        )
    return sorted(
        output,
        key=lambda item: round_sort_key(item["stage"]),
    )


def _opponent_rows(event: dict[str, Any], pair_query: str) -> list[OpponentResult]:
    rank_pairs = event["rank_pairs"]
    target_index = event["target_index"]
    if target_index is None:
        return []

    starter_pairs = [
        pair
        for page in event["pages"]
        if _page_source(page) == "starter.htm"
        for pair in page.get("paare", [])
    ]
    grouped: dict[str, list[OpponentResult]] = defaultdict(list)
    for index, pair in enumerate(rank_pairs):
        if index == target_index:
            continue
        name, club = _canonical_rank_pair(pair, starter_pairs)
        if not name or pair_matches(pair_query, {"name": name}):
            continue
        opponent_place = pair_place(event["pages"], pair)
        outcome = compare_places(event["place_range"], opponent_place)
        grouped[_pair_key(name)].append(
            OpponentResult(
                key=_pair_key(name),
                name=name,
                club=club,
                outcome=outcome,
                own_place=event["place_range"],
                opponent_place=opponent_place,
                last_seen=event["date"],
            )
        )
    rows = []
    for key, candidates in grouped.items():
        signatures = {
            (
                row.club,
                row.own_place,
                row.opponent_place,
                row.outcome,
            )
            for row in candidates
        }
        if len(signatures) == 1:
            rows.append(candidates[0])
            continue
        clubs = {row.club for row in candidates}
        own_places = {row.own_place for row in candidates}
        rows.append(
            OpponentResult(
                key=key,
                name=candidates[0].name,
                club=next(iter(clubs)) if len(clubs) == 1 else "",
                outcome=PlacementOutcome.UNKNOWN,
                own_place=(next(iter(own_places)) if len(own_places) == 1 else None),
                opponent_place=None,
                last_seen=event["date"],
            )
        )
    return rows


def _point_records(event: dict[str, Any], pair_query: str) -> list[PointRecord]:
    points = []
    for page in event["pages"]:
        if _page_source(page) != "tabges.htm":
            continue
        for result in page.get("paar_ergebnisse", []):
            if not pair_matches(pair_query, result):
                continue
            for key, value in result_fields(result).items():
                if "punkt" not in normalize(key):
                    continue
                amount = numeric_value(value)
                if amount is not None:
                    points.append(
                        PointRecord(
                            event_id=event["id"],
                            title=event["title"],
                            date=event["date"],
                            source=source_name(page),
                            url=page["url"],
                            label=key,
                            points=amount,
                        )
                    )
    return points


def normalize_quality_issue(issue: dict[str, Any]) -> dict[str, str]:
    """Normalize current and legacy quality-issue field names."""
    fields = (
        ("event_id", "Event-ID", "event_id"),
        ("code", "Code", "code"),
        ("severity", "Status", "severity"),
        ("tournament", "Turnier", "tournament"),
        ("round", "Runde", "round"),
        ("note", "Hinweis", "note"),
        ("source", "Quelle", "source"),
        ("action", "Nächster Schritt", "action"),
    )
    return {
        target: str(issue.get(current, issue.get(legacy, "")))
        for target, current, legacy in fields
    }


def summarize_pair_events(pages: list[Page], pair_query: str) -> list[dict[str, Any]]:
    """Bereitet nur Turniermetadaten und Filter vor, ohne Detailanalysen."""
    events = []
    for key, event_pages in _group_pages(pages).items():
        event = _event_summary(key, event_pages, pair_query)
        if event is not None:
            events.append(event)
    events.sort(
        key=lambda event: (
            event["date"] is None,
            event["date"] or date.max,
            event["title"].casefold(),
        )
    )
    return events


def build_pair_dashboard(pages: list[Page], pair_query: str) -> dict[str, Any]:
    """Erstellt normalisierte und nachvollziehbare Ansichten für ein Paar."""
    events = summarize_pair_events(pages, pair_query)

    dance_observations_by_class: dict[tuple[str, str], list[DanceObservation]] = (
        defaultdict(list)
    )
    judge_panels: dict[tuple[str, str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    judge_names: dict[str, str] = {}
    judge_tournaments: dict[str, set[str]] = defaultdict(set)
    judge_total_marks: dict[str, int] = defaultdict(int)
    judge_panel_counts: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(
        dict
    )
    judge_panel_sources: dict[tuple[str, str, str, str], dict[str, str]] = defaultdict(
        dict
    )
    opponents: dict[str, OpponentSummary] = {}
    opponent_evidence: list[OpponentEvidence] = []
    quality_issues: list[QualityIssue] = []
    point_records: list[PointRecord] = []
    for event in events:
        event_id = event["id"]
        for page, result in event["results"]:
            source = _page_source(page)
            stage = round_name(page, result)
            if source == "ergwert.htm":
                size = _field_size(result) or event["field_size"]
                for dance, place in _dance_placements(result).items():
                    score = normalized_rank(place, size) if size else None
                    if score is not None:
                        dance_observations_by_class[
                            (dance, event["start_class"])
                        ].append(
                            DanceObservation(
                                event_id=event_id,
                                title=event["title"],
                                date=event["date"],
                                city=event["city"],
                                group=event["group"],
                                discipline=event["discipline"],
                                stage=stage,
                                score=score,
                                url=page["url"],
                                place=place,
                                field_size=size,
                            )
                        )
                    elif size:
                        quality_issues.append(
                            QualityIssue(
                                tournament=event["title"],
                                round=stage,
                                note=f"{dance}: Platz {place:g} ist für Feldgröße {size} ungültig.",
                                source=page["url"],
                            )
                        )
            elif source == "wert_er.htm":
                size = _field_size(result) or event["field_size"]
                if not size:
                    continue
                for mark in _judge_marks(result):
                    rank = numeric_value(mark.raw)
                    score = normalized_rank(rank, size) if rank is not None else None
                    if score is not None:
                        key = (event_id, stage, mark.dance, event["title"])
                        judge_identity = normalize(mark.name)
                        if judge_identity:
                            judge_names.setdefault(judge_identity, mark.name)
                            judge_panels[key][judge_identity].append(score)
                            judge_panel_counts[key][judge_identity] = 1
                            judge_panel_sources[key][judge_identity] = page["url"]
                    elif rank is not None:
                        quality_issues.append(
                            QualityIssue(
                                tournament=event["title"],
                                round=stage,
                                note=f"{mark.name}: Richternote {rank:g} ist für Feldgröße {size} ungültig.",
                                source=page["url"],
                            )
                        )
            elif source == "tabges.htm" and result.get("runde") != "Gesamtwertung":
                key = (event_id, stage, "Rundenkreuzrate", event["title"])
                for mark in result.get("richter_kreuze", []):
                    score = normalized_judge_cross_rate(result, mark)
                    maximum = judge_cross_maximum(result, mark)
                    if score is None or maximum is None:
                        continue
                    code = str(mark.get("kuerzel", "")).strip()
                    name = clean_judge_name(code, str(mark.get("name", "")))
                    judge_identity = normalize(name)
                    if not judge_identity:
                        continue
                    judge_names.setdefault(judge_identity, name)
                    judge_panels[key][judge_identity].append(score)
                    judge_panel_counts[key][judge_identity] = maximum
                    judge_panel_sources[key][judge_identity] = page["url"]

        for row in _opponent_rows(event, pair_query):
            if not row.key:
                continue
            opponent_evidence.append(
                OpponentEvidence(
                    key=row.key,
                    name=row.name,
                    club=row.club,
                    event_id=event_id,
                    group=event["group"],
                    discipline=event["discipline"],
                    starts=1,
                    wins=int(row.outcome is PlacementOutcome.WINS),
                    losses=int(row.outcome is PlacementOutcome.LOSSES),
                    ties=int(row.outcome is PlacementOutcome.TIES),
                    unknown=int(row.outcome is PlacementOutcome.UNKNOWN),
                    own_place=row.own_place,
                    opponent_place=row.opponent_place,
                    outcome=row.outcome.value,
                    last_seen=row.last_seen,
                    title=event["title"],
                    date=event["date"],
                    city=event["city"],
                    sources=[
                        page["url"]
                        for page in event["pages"]
                        if _page_source(page) in {"ergwert.htm", "tabges.htm"}
                    ],
                )
            )
            current = opponents.setdefault(
                row.key,
                OpponentSummary(name=row.name),
            )
            current.add(row)

        point_records.extend(_point_records(event, pair_query))

    dance_observations: dict[str, list[DanceObservation]] = defaultdict(list)
    dance_class_rows: list[DanceClassSummary] = []
    dance_history_rows: list[DanceHistory] = []
    for (dance, start_class), observations in dance_observations_by_class.items():
        dance_observations[dance].extend(observations)
        dance_class_rows.append(
            DanceClassSummary(
                dance=dance,
                start_class=start_class,
                normalized_place=sum(item.score for item in observations)
                / len(observations),
                observations=len(observations),
                events=len({item.event_id for item in observations}),
            )
        )
        dance_history_rows.extend(
            DanceHistory(
                dance=dance,
                start_class=start_class,
                event_id=item.event_id,
                title=item.title,
                date=item.date,
                city=item.city,
                group=item.group,
                discipline=item.discipline,
                stage=item.stage,
                normalized_place=item.score,
                url=item.url,
                place=item.place,
                field_size=item.field_size,
            )
            for item in observations
        )
    dance_class_rows.sort(key=lambda row: (row.dance, row.start_class))
    dance_history_rows.sort(
        key=lambda row: (
            row.date is None,
            row.date or date.max,
            row.title.casefold(),
            row.stage,
            row.start_class,
        )
    )

    dance_rows: list[DanceSummary] = []
    for dance, observations in dance_observations.items():
        dance_rows.append(
            DanceSummary(
                dance=dance,
                normalized_place=sum(item.score for item in observations)
                / len(observations),
                observations=len(observations),
                events=len({item.event_id for item in observations}),
            )
        )
    dance_rows.sort(key=lambda row: row.normalized_place, reverse=True)

    judge_deviations: dict[str, list[float]] = defaultdict(list)
    judge_evidence: list[JudgeEvidence] = []
    for panel_key, judges in judge_panels.items():
        normalized_by_judge = {
            judge: sum(scores) / len(scores)
            for judge, scores in judges.items()
            if scores
        }
        if len(normalized_by_judge) < 2:
            continue
        for judge, score in normalized_by_judge.items():
            other_scores = [
                other_score
                for other_judge, other_score in normalized_by_judge.items()
                if other_judge != judge
            ]
            judge_deviations[judge].append(score - median(other_scores))
            judge_tournaments[judge].add(panel_key[0])
            judge_total_marks[judge] += judge_panel_counts[panel_key][judge]
            judge_evidence.append(
                JudgeEvidence(
                    name=judge_names[judge],
                    event_id=panel_key[0],
                    title=panel_key[3],
                    stage=panel_key[1],
                    dance=panel_key[2],
                    score=score,
                    panel_median=median(other_scores),
                    deviation_pp=(score - median(other_scores)) * 100,
                    url=judge_panel_sources[panel_key][judge],
                )
            )
    judge_rows = [
        JudgeSummary(
            name=judge_names[judge],
            deviation_pp=sum(values) / len(values) * 100,
            observations=len(values),
            tournaments=len(judge_tournaments[judge]),
            marks=judge_total_marks[judge],
            raw_marks=sum(
                counts.get(judge, 0) for counts in judge_panel_counts.values()
            ),
            raw_tournaments=len(
                {
                    key[0]
                    for key, counts in judge_panel_counts.items()
                    if judge in counts
                }
            ),
        )
        for judge, values in judge_deviations.items()
    ]
    judge_rows.sort(key=lambda row: row.deviation_pp, reverse=True)

    opponent_rows = [
        OpponentRow(
            name=row.name,
            starts=row.starts,
            wins=row.wins,
            losses=row.losses,
            ties=row.ties,
            unknown=row.unknown,
            last_seen=row.last_seen,
            club="; ".join(sorted(row.clubs)),
        )
        for row in opponents.values()
    ]
    opponent_rows.sort(
        key=lambda row: (
            -row.starts,
            -row.wins,
            row.name.casefold(),
        ),
    )
    rounds_by_event = {
        event["id"]: _build_rounds(event, pair_query) for event in events
    }
    event_quality = []
    for event in events:
        sources = {_page_source(page) for page in event["pages"]}
        source_urls = ", ".join(page["url"] for page in event["pages"])
        checks = (
            (
                "missing_date",
                event.get("date") is None,
                "Datum nicht erkannt",
                "Turnierdatum in der Quelle prüfen.",
            ),
            (
                "missing_city",
                not event.get("city"),
                "Turnierort nicht gespeichert",
                "Quellseite auf eine Ortsangabe prüfen.",
            ),
            (
                "missing_placement",
                event.get("place_range") is None,
                "Endplatzierung fehlt oder ist nicht eindeutig",
                "Ranglistenbeleg für dieses Paar prüfen.",
            ),
            (
                "missing_field_size",
                event.get("field_size") is None,
                "Feldgröße nicht verfügbar",
                "Start- oder Rangliste auf Feldgröße prüfen.",
            ),
            (
                "missing_details",
                not ({"ergwert.htm", "tabges.htm", "wert_er.htm"} & sources),
                "Keine Runden- oder Richterdetailseiten archiviert",
                "Prüfen, ob Detailseiten gecrawlt und importiert werden können.",
            ),
        )
        for code, missing, note, action in checks:
            if missing:
                event_quality.append(
                    {
                        "event_id": event["id"],
                        "code": code,
                        "severity": "unvollständig",
                        "tournament": event["title"],
                        "round": "",
                        "note": note,
                        "source": source_urls,
                        "action": action,
                    }
                )
        has_judge_data = any(
            page.get("wertungsrichter")
            or any(
                result.get("richter_wertungen") or result.get("richter_kreuze")
                for result in page.get("paar_ergebnisse", [])
            )
            for page in event["pages"]
        )
        if not has_judge_data:
            event_quality.append(
                {
                    "event_id": event["id"],
                    "code": "missing_judge_data",
                    "severity": "nicht verfügbar",
                    "tournament": event["title"],
                    "round": "",
                    "note": "Keine Einzelrichterdaten verfügbar",
                    "source": source_urls,
                    "action": "Prüfen, ob eine Wertungsdetailseite in der Quelle vorliegt.",
                }
            )
        for round_data in rounds_by_event[event["id"]]:
            if (
                round_type(round_data["stage"]) in PRE_FINAL_STAGES
                and round_data["qualified"] is None
            ):
                event_quality.append(
                    {
                        "event_id": event["id"],
                        "code": "unknown_qualification",
                        "severity": "nicht verfügbar",
                        "tournament": event["title"],
                        "round": round_data["stage"],
                        "note": "Qualifikationsstatus unbekannt",
                        "source": source_urls,
                        "action": "Rundenbeleg und Qualifikationskennzeichnung prüfen.",
                    }
                )
    for event in events:
        for round_data in rounds_by_event[event["id"]]:
            for issue in round_data["quality_issues"]:
                quality_issues.append(
                    QualityIssue(
                        tournament=event["title"],
                        round=round_data["stage"],
                        note=issue,
                        source=", ".join(
                            page["url"]
                            for page in event["pages"]
                            if _page_source(page) in {"ergwert.htm", "tabges.htm"}
                        ),
                        event_id=event["id"],
                        code=(
                            "cross_conflict"
                            if "widersprechen" in issue or "außerhalb" in issue
                            else "incomplete_round_data"
                        ),
                        severity=(
                            "widersprüchlich"
                            if "widersprechen" in issue or "außerhalb" in issue
                            else "unvollständig"
                        ),
                    )
                )
    round_observations: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for event in events:
        for round_data in rounds_by_event[event["id"]]:
            stage = round_data["stage"]
            rate = round_data["cross_rate"]
            if round_type(stage) in PRE_FINAL_STAGES and rate is not None:
                round_observations[round_type(stage)].append((event["id"], rate))
    round_cross_rows = [
        RoundCrossSummary(
            stage=stage.value,
            cross_rate=sum(rate for _, rate in observations) / len(observations),
            observations=len(observations),
            events=len({event_id for event_id, _ in observations}),
        )
        for stage in PRE_FINAL_STAGES
        if (observations := round_observations[stage])
    ]
    return {
        "events": events,
        "dance_rows": [asdict(row) for row in dance_rows],
        "dance_class_rows": [asdict(row) for row in dance_class_rows],
        "dance_history_rows": [asdict(row) for row in dance_history_rows],
        "round_cross_rows": [asdict(row) for row in round_cross_rows],
        "judge_rows": [asdict(row) for row in judge_rows],
        "judge_evidence": [asdict(row) for row in judge_evidence],
        "opponent_rows": [asdict(row) for row in opponent_rows],
        "opponent_evidence": [asdict(row) for row in opponent_evidence],
        "rounds_by_event": rounds_by_event,
        "event_quality": event_quality,
        "point_records": [asdict(record) for record in point_records],
        "quality_issues": [issue.to_dict() for issue in quality_issues],
    }


def filter_events(
    events: list[dict[str, Any]],
    group: str = "Alle",
    discipline: str = "Alle",
    date_range: tuple[date, date] | None = None,
) -> list[dict[str, Any]]:
    """Filtert Turniere ohne Kennzahlen oder Rundendaten zu duplizieren."""
    start, end = date_range or (None, None)
    return [
        event
        for event in events
        if (group == "Alle" or event["group"] == group)
        and (discipline == "Alle" or event["discipline"] == discipline)
        and (
            date_range is None
            or (
                event["date"] is not None
                and (start is None or event["date"] >= start)
                and (end is None or event["date"] <= end)
            )
        )
    ]
