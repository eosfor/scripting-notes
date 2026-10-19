"""Migration planning engine. User-facing workflow is in sim.ipynb."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Callable, Optional

import simpy
import pandas as pd
from paretoset import paretoset

# =======================
# ====== CONFIG =========
# =======================

CAL_HOURS_PER_DAY = 24.0
DAYS_PER_MONTH = 30.4375  # Gregorian average

def days_to_months(days: float) -> float:
    return days / DAYS_PER_MONTH

BASE_CONFIG = {
    # Global caps (do not process beyond these totals)
    "TOTAL_REPOS": 600,        # e.g., 4200
    "TOTAL_PIPES": 200,        # e.g., 1200
    "ALLOCATION_MODE": "sequential",  # or "even"

    # Program structure
    "WAVES": 4,
    "COHORTS_PER_WAVE": 2,
    "WAVE_SPACING_DAYS": 0,      # gap between wave starts (calendar days); set 90 for "quarterly"
    "COHORT_SPACING_DAYS": 0,    # gap between cohorts inside a wave (calendar days)

    # Work volumes per cohort
    "REPOS_PER_COHORT": 1000,
    "PIPES_PER_COHORT": 300,

    # Execution crews per cohort
    "REPO_ENGINEERS_PER_COHORT": 4,
    "CI_ENGINEERS_PER_COHORT": 2,

    # Shared crews (across all waves/cohorts)
    "TRIAGE_ENGINEERS_SHARED": 3,  # first-line triage/hypercare pool
    "SWAT_CORE_CAPACITY": 2,       # core escalation capacity (architects/platform)

    # Task mix (BUSINESS-HOUR durations here)
    "REPO_DIST": {"simple": 0.7, "medium": 0.25, "complex": 0.05},
    "REPO_TIMES": {"simple": (0.5, 1.0), "medium": (2, 4), "complex": (8, 16)},
    "PIPE_DIST": {"simple": 0.6, "medium": 0.3, "complex": 0.1},
    "PIPE_TIMES": {"simple": (1, 2), "medium": (3, 5), "complex": (8, 16)},

    # Failure / rework
    "REPO_REWORK_PROB": 0.01,
    "PIPE_REWORK_PROB": 0.02,
    "REPO_REWORK_TIME": (1, 4),   # BUSINESS HOURS
    "PIPE_REWORK_TIME": (2, 6),   # BUSINESS HOURS

    # Triage + Escalations (BUSINESS HOURS)
    "TRIAGE_TIME_REPO": (1, 3),
    "TRIAGE_TIME_PIPE": (1, 3),
    "ESCALATION_PROB_COMPLEX_REPO": 0.25,
    "ESCALATION_PROB_COMPLEX_PIPE": 0.20,
    "SWAT_TIME_REPO": (1, 2),
    "SWAT_TIME_PIPE": (1, 2),

    # Security champion effect (faster triage)
    "SECURITY_CHAMPIONS_ENABLED": True,
    "TRIAGE_ACCEL_FACTOR": 0.9,  # triage 10% faster

    # Core automation baseline scalers (applied every wave, then improved)
    "DURATION_SCALER_REPO": 0.95,
    "DURATION_SCALER_PIPE": 0.94,
    "REWORK_SCALER_REPO": 0.85,
    "REWORK_SCALER_PIPE": 0.90,

    # Between-wave improvement model (default random 1–10%)
    "IMPR_MIN": 0.01,
    "IMPR_MAX": 0.10,
    # Optional hook to override improvement logic:
    #   Callable[[dict, int, random.Random, dict], dict]
    "IMPROVEMENT_HOOK": None,

    # Gate: standard CI templates availability (calendar day)
    "TEMPLATES_READY_DAY": 7,  # day 7 means wave 1 cannot start cohorts before day 7

    # Hypercare (BUSINESS HOURS workload)
    "HYPERCARE_ENABLED": True,
    "HYPERCARE_WEEKS": 1,          # ~1 workweek of hypercare
    "HYPERCARE_HOURS_PER_DAY": 2,  # per workday, consumed from triage pool

    # Business-hours calendar (pause nights/weekends)
    "BUSINESS_HOURS_ONLY": True,
    "WORKDAY_START_HOUR": 9,
    "WORKDAY_END_HOUR": 17,   # exclusive
    "WEEKENDS_OFF": True,

    # Random seed
    "SEED": 42,
}

# =======================
# ====== HELPERS ========
# =======================

def choose_type(dist: Dict[str, float], rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    for k, p in dist.items():
        acc += p
        if r < acc:
            return k
    return list(dist.keys())[-1]

def sample_time(bounds: Tuple[float, float], rng: random.Random) -> float:
    low, high = bounds
    return rng.uniform(low, high)

# ---- Business Hours Calendar ----

def _dow(day_index: int) -> int:
    return day_index % 7  # 0=Mon ... 6=Sun

def within_business(t: float, cfg: dict) -> bool:
    if not cfg["BUSINESS_HOURS_ONLY"]:
        return True
    day = int(t // CAL_HOURS_PER_DAY)
    hour = t % CAL_HOURS_PER_DAY
    if cfg["WEEKENDS_OFF"] and _dow(day) in (5, 6):  # Sat/Sun
        return False
    return cfg["WORKDAY_START_HOUR"] <= hour < cfg["WORKDAY_END_HOUR"]

def next_business_start(t: float, cfg: dict) -> float:
    if not cfg["BUSINESS_HOURS_ONLY"]:
        return t
    day = int(t // CAL_HOURS_PER_DAY)
    hour = t % CAL_HOURS_PER_DAY
    start = cfg["WORKDAY_START_HOUR"]
    end = cfg["WORKDAY_END_HOUR"]

    if (not cfg["WEEKENDS_OFF"]) or _dow(day) < 5:
        if hour < start:
            return day * CAL_HOURS_PER_DAY + start
        if start <= hour < end:
            return t

    d = day
    while True:
        d += 1
        if (not cfg["WEEKENDS_OFF"]) or _dow(d) < 5:
            return d * CAL_HOURS_PER_DAY + start

def end_of_business(t: float, cfg: dict) -> float:
    day = int(t // CAL_HOURS_PER_DAY)
    return day * CAL_HOURS_PER_DAY + cfg["WORKDAY_END_HOUR"]

def business_hours_between(t0: float, t1: float, cfg: dict) -> float:
    """Total BUSINESS-HOURS between calendar times t0 and t1."""
    if t1 <= t0:
        return 0.0
    if not cfg.get("BUSINESS_HOURS_ONLY", True):
        return t1 - t0
    t = t0
    total = 0.0
    tiny = 1e-9
    while t < t1 - tiny:
        if not within_business(t, cfg):
            t = next_business_start(t, cfg)
            if t >= t1: break
            continue
        eod = end_of_business(t, cfg)
        chunk_end = min(eod, t1)
        if chunk_end > t:
            total += (chunk_end - t)
            t = chunk_end
        else:
            t += tiny
    return total

def parse_engineer_id(eid: str):
    """
    Parse labels like: 'CI_3.2:7', 'Repo_1.3:10', 'Triage:2', 'SWAT:1'
    Returns: (crew, wave:int|None, cohort:int|None, idx:str)
    """
    if ":" not in eid:
        return (eid, None, None, "")
    left, idx = eid.split(":", 1)
    if "_" in left and "." in left:
        crew, wc = left.split("_", 1)
        w, c = wc.split(".", 1)
        return (crew, int(w), int(c), idx)
    else:
        # shared crews like Triage:2, SWAT:1
        return (left, None, None, idx)

def plan_allocation(total, per_cohort, waves, cohorts, mode="sequential"):
    """Return a list length waves*cohorts with the number of items to run in each cohort."""
    nslots = waves * cohorts
    if total is None:
        return [per_cohort] * nslots

    total = max(0, int(total))
    plan = [0] * nslots

    if mode == "even":
        base = total // nslots
        rem  = total % nslots
        for i in range(nslots):
            plan[i] = min(per_cohort, base + (1 if i < rem else 0))
    else:  # "sequential" (fill early cohorts first)
        remaining = total
        for i in range(nslots):
            take = min(per_cohort, remaining)
            plan[i] = max(0, take)
            remaining -= take

    return plan

# ==========================
# ===== USAGE TRACKING =====
# ==========================

class UsageTracker:
    """Collects per-engineer work segments and aggregates totals/monthly stats."""
    def __init__(self):
        self._segments: List[Dict[str, Any]] = []

    def record(self, crew: str, engineer_id: str, start: float, end: float):
        # Each segment is entirely within a business window; 'hours' == end-start
        if end <= start:
            return
        self._segments.append({
            "Crew": crew,
            "Engineer": engineer_id,
            "Start(h)": start,
            "End(h)": end,
            "Hours": end - start,  # BUSINESS hours consumed
        })

    def segments_df(self) -> pd.DataFrame:
        if not self._segments:
            return pd.DataFrame(columns=["Crew","Engineer","Start(h)","End(h)","Hours"])
        return pd.DataFrame(self._segments)

    def totals_df(self) -> pd.DataFrame:
        df = self.segments_df()
        if df.empty:
            return pd.DataFrame(columns=["Crew","Engineer","Hours","PersonDays"])
        tot = df.groupby(["Crew","Engineer"], as_index=False)["Hours"].sum()
        tot["PersonDays"] = tot["Hours"] / 8.0
        return tot.sort_values(["Crew","Hours"], ascending=[True, False]).reset_index(drop=True)

    def monthly_df(self) -> pd.DataFrame:
        """Split segments across month buckets (avg month length)."""
        df = self.segments_df()
        if df.empty:
            return pd.DataFrame(columns=["Month","Crew","Engineer","Hours","PersonDays"])
        rows = []
        month_len_h = DAYS_PER_MONTH * CAL_HOURS_PER_DAY

        def month_idx(t: float) -> int:
            return int(t // month_len_h)

        for _, row in df.iterrows():
            crew = row["Crew"]
            eng = row["Engineer"]
            start = row["Start(h)"]
            end   = row["End(h)"]
            s = start
            while s < end:
                idx = month_idx(s)
                next_boundary = (idx + 1) * month_len_h
                e = min(end, next_boundary)
                rows.append({
                    "Month": idx,
                    "Crew": crew,
                    "Engineer": eng,
                    "Hours": e - s
                })
                s = e

        m = pd.DataFrame(rows)
        m = m.groupby(["Month","Crew","Engineer"], as_index=False)["Hours"].sum()
        m["PersonDays"] = m["Hours"] / 8.0
        return m.sort_values(["Month","Crew","Hours"], ascending=[True, True, False]).reset_index(drop=True)

# ---------- tracked business-hours timeout ----------

def work_timeout_tracked(env: simpy.Environment,
                         hours_to_work: float,
                         cfg: dict,
                         tracker: Optional[UsageTracker] = None,
                         crew: Optional[str] = None,
                         engineer_id: Optional[str] = None):
    """
    Consume BUSINESS HOURS, skipping nights/weekends; also record segments per engineer.
    """
    if not cfg["BUSINESS_HOURS_ONLY"]:
        start = env.now
        yield env.timeout(hours_to_work)
        if tracker and crew and engineer_id:
            tracker.record(crew, engineer_id, start, env.now)
        return
    remaining = hours_to_work
    tiny = 1e-9
    while remaining > tiny:
        if not within_business(env.now, cfg):
            ns = next_business_start(env.now, cfg)
            yield env.timeout(ns - env.now)
            continue
        eod = end_of_business(env.now, cfg)
        chunk = min(remaining, max(0.0, eod - env.now))
        if chunk > tiny:
            start = env.now
            yield env.timeout(chunk)
            if tracker and crew and engineer_id:
                tracker.record(crew, engineer_id, start, start + chunk)
            remaining -= chunk
        else:
            yield env.timeout(0)

def wait_until_start(env: simpy.Environment, target_hour: float, cfg: dict):
    if env.now < target_hour:
        yield env.timeout(target_hour - env.now)
    if not within_business(env.now, cfg):
        ns = next_business_start(env.now, cfg)
        yield env.timeout(ns - env.now)

# =======================
# ====== DATA ===========
# =======================

# =======================
# ====== DATA ===========
# =======================

@dataclass
class Metrics:
    finishes_abs: List[float] = field(default_factory=list)
    reworks: int = 0
    escalations: int = 0
    triage_hours: float = 0.0
    swat_hours: float = 0.0
    main_hours: float = 0.0       # NEW: sum of main (first-pass) work hours
    rework_hours: float = 0.0     # NEW: sum of extra work hours after rework fires

    def summary_relative(self, offset_hour: float) -> Dict[str, float]:
        if not self.finishes_abs:
            return {}
        rel = [t - offset_hour for t in self.finishes_abs]
        rel.sort()
        p95 = statistics.quantiles(rel, n=100)[94] if len(rel) >= 100 else max(rel)
        return {"p50_hours": statistics.median(rel), "p95_hours": p95, "max_hours": max(rel)}

@dataclass
class CohortResult:
    wave_id: int
    cohort_id: int
    start_hour: float
    repo_summary: Dict[str, float]
    pipe_summary: Dict[str, float]
    finish_hour: float
    hypercare_finish_hour: Optional[float]
    repos_planned: int = 0      # <-- NEW
    pipes_planned: int = 0      # <-- NEW
    # NEW – repo stats
    repo_reworks: int = 0
    repo_escalations: int = 0
    repo_main_hours: float = 0.0
    repo_rework_hours: float = 0.0
    repo_triage_hours: float = 0.0
    repo_swat_hours: float = 0.0
    # NEW – pipeline stats
    pipe_reworks: int = 0
    pipe_escalations: int = 0
    pipe_main_hours: float = 0.0
    pipe_rework_hours: float = 0.0
    pipe_triage_hours: float = 0.0
    pipe_swat_hours: float = 0.0


# =======================
# == IMPROVEMENTS LOGIC =
# =======================

def default_improvement_hook(state: dict, wave_index: int, rng: random.Random, cfg: dict) -> dict:
    imp = rng.uniform(cfg["IMPR_MIN"], cfg["IMPR_MAX"])
    return {
        "dur_repo": max(0.3, state["dur_repo"] * (1.0 - imp)),
        "dur_pipe": max(0.3, state["dur_pipe"] * (1.0 - imp)),
        "rwrk_repo": max(0.05, state["rwrk_repo"] * (1.0 - 0.5 * imp)),
        "rwrk_pipe": max(0.05, state["rwrk_pipe"] * (1.0 - 0.5 * imp)),
    }

# =======================
# ===== PROCESSES =======
# =======================

def repo_task(env: simpy.Environment,
              repo_pool: simpy.Store,
              triage_pool: simpy.Store,
              swat_pool: simpy.Store,
              metrics: Metrics,
              cfg: dict,
              scalers: dict,
              rng: random.Random,
              tracker: UsageTracker):
    """One repository migration (may rework, triage, escalate)."""
    # Acquire a specific repo engineer
    eng_id = yield repo_pool.get()

    try:
        rtype = choose_type(cfg["REPO_DIST"], rng)
        main_dur = sample_time(cfg["REPO_TIMES"][rtype], rng) * scalers["dur_repo"]
        metrics.main_hours += main_dur

        # main work (tracked)
        yield from work_timeout_tracked(env, main_dur, cfg, tracker, "Repo", eng_id)

        # possible rework + triage + swat
        base_prob = cfg["REPO_REWORK_PROB"] * scalers["rwrk_repo"]
        if rng.random() < base_prob:
            metrics.reworks += 1

            ttime = sample_time(cfg["TRIAGE_TIME_REPO"], rng)
            if cfg["SECURITY_CHAMPIONS_ENABLED"]:
                ttime *= cfg["TRIAGE_ACCEL_FACTOR"]

            triage_id = yield triage_pool.get()
            try:
                yield from work_timeout_tracked(env, ttime, cfg, tracker, "Triage", triage_id)
            finally:
                yield triage_pool.put(triage_id)
            metrics.triage_hours += ttime

            if rtype == "complex" and rng.random() < cfg["ESCALATION_PROB_COMPLEX_REPO"]:
                metrics.escalations += 1
                stime = sample_time(cfg["SWAT_TIME_REPO"], rng)
                swat_id = yield swat_pool.get()
                try:
                    yield from work_timeout_tracked(env, stime, cfg, tracker, "SWAT", swat_id)
                finally:
                    yield swat_pool.put(swat_id)
                metrics.swat_hours += stime

            extra = sample_time(cfg["REPO_REWORK_TIME"], rng) * scalers["dur_repo"]
            metrics.rework_hours += extra
            yield from work_timeout_tracked(env, extra, cfg, tracker, "Repo", eng_id)

        metrics.finishes_abs.append(env.now)

    finally:
        # Release repo engineer
        yield repo_pool.put(eng_id)

def pipeline_task(env: simpy.Environment,
                  ci_pool: simpy.Store,
                  triage_pool: simpy.Store,
                  swat_pool: simpy.Store,
                  metrics: Metrics,
                  cfg: dict,
                  scalers: dict,
                  rng: random.Random,
                  tracker: UsageTracker):
    """One CI pipeline migration (may rework, triage, escalate)."""
    eng_id = yield ci_pool.get()
    try:
        ptype = choose_type(cfg["PIPE_DIST"], rng)
        main_dur = sample_time(cfg["PIPE_TIMES"][ptype], rng) * scalers["dur_pipe"]
        metrics.main_hours += main_dur

        # main work (tracked)
        yield from work_timeout_tracked(env, main_dur, cfg, tracker, "CI", eng_id)

        base_prob = cfg["PIPE_REWORK_PROB"] * scalers["rwrk_pipe"]
        if rng.random() < base_prob:
            metrics.reworks += 1

            ttime = sample_time(cfg["TRIAGE_TIME_PIPE"], rng)
            if cfg["SECURITY_CHAMPIONS_ENABLED"]:
                ttime *= cfg["TRIAGE_ACCEL_FACTOR"]
            triage_id = yield triage_pool.get()
            try:
                yield from work_timeout_tracked(env, ttime, cfg, tracker, "Triage", triage_id)
            finally:
                yield triage_pool.put(triage_id)
            metrics.triage_hours += ttime

            if ptype == "complex" and rng.random() < cfg["ESCALATION_PROB_COMPLEX_PIPE"]:
                metrics.escalations += 1
                stime = sample_time(cfg["SWAT_TIME_PIPE"], rng)
                swat_id = yield swat_pool.get()
                try:
                    yield from work_timeout_tracked(env, stime, cfg, tracker, "SWAT", swat_id)
                finally:
                    yield swat_pool.put(swat_id)
                metrics.swat_hours += stime

            extra = sample_time(cfg["PIPE_REWORK_TIME"], rng) * scalers["dur_pipe"]
            metrics.rework_hours += extra
            yield from work_timeout_tracked(env, extra, cfg, tracker, "CI", eng_id)

        metrics.finishes_abs.append(env.now)
    finally:
        yield ci_pool.put(eng_id)

def hypercare_process(env: simpy.Environment,
                      triage_pool: simpy.Store,
                      start_hour: float,
                      days: int,
                      hours_per_day: float,
                      cfg: dict,
                      tracker: UsageTracker):
    """Hypercare workload (BUSINESS HOURS) after cohort completion; tracked to triage engineers."""
    # One support session on each successive working day, never compressed.
    yield from wait_until_start(env, start_hour, cfg)
    for day in range(days):
        if cfg["BUSINESS_HOURS_ONLY"]:
            session_start = next_business_start(env.now, cfg)
            yield from wait_until_start(env, session_start, cfg)
        triage_id = yield triage_pool.get()
        try:
            yield from work_timeout_tracked(env, hours_per_day, cfg, tracker, "Triage", triage_id)
        finally:
            yield triage_pool.put(triage_id)
        if day < days - 1:
            next_day = (int(env.now // 24) + 1) * 24
            yield from wait_until_start(env, next_day, cfg)


def run_one_cohort(env: simpy.Environment,
                   wave_id: int,
                   cohort_id: int,
                   start_hour: float,
                   triage_pool: simpy.Store,
                   swat_pool: simpy.Store,
                   cfg: dict,
                   scalers: dict,
                   rng: random.Random,
                   tracker: UsageTracker,
                   repos_planned: int,
                   pipes_planned: int) -> CohortResult:
    """Launch a single cohort at start_hour; returns detailed results."""

    # Per-cohort pools for repo & CI (token-based to attribute workload)
    repo_pool = simpy.Store(env, capacity=cfg["REPO_ENGINEERS_PER_COHORT"])
    ci_pool   = simpy.Store(env, capacity=cfg["CI_ENGINEERS_PER_COHORT"])
    for i in range(cfg["REPO_ENGINEERS_PER_COHORT"]):
        yield repo_pool.put(f"Repo_{wave_id}.{cohort_id}:{i+1}")
    for i in range(cfg["CI_ENGINEERS_PER_COHORT"]):
        yield ci_pool.put(f"CI_{wave_id}.{cohort_id}:{i+1}")

    repo_metrics = Metrics()
    pipe_metrics = Metrics()

    # Gate
    gate_hour = cfg["TEMPLATES_READY_DAY"] * CAL_HOURS_PER_DAY
    planned_start = max(start_hour, gate_hour)
    yield from wait_until_start(env, planned_start, cfg)

    planned_start = env.now  # actual start after calendar and template gate

    # Spawn ONLY the planned number of tasks
    tasks = [env.process(repo_task(env, repo_pool, triage_pool, swat_pool,
                 repo_metrics, cfg, scalers, rng, tracker)) for _ in range(repos_planned)]
    tasks += [env.process(pipeline_task(env, ci_pool, triage_pool, swat_pool,
                  pipe_metrics, cfg, scalers, rng, tracker)) for _ in range(pipes_planned)]
    yield env.all_of(tasks)

    # If nothing planned, finish immediately at planned_start (and skip hypercare)
    if repos_planned + pipes_planned == 0:
        cohort_finish_abs = planned_start
        hypercare_finish = None
    else:
        cohort_finish_abs = max(
            (max(repo_metrics.finishes_abs) if repos_planned else planned_start),
            (max(pipe_metrics.finishes_abs) if pipes_planned else planned_start)
        )
        hypercare_finish = None
        if cfg["HYPERCARE_ENABLED"]:
            hc_days = int(cfg["HYPERCARE_WEEKS"] * 5)
            hc = env.process(hypercare_process(env, triage_pool, cohort_finish_abs, hc_days, cfg["HYPERCARE_HOURS_PER_DAY"], cfg, tracker))
            yield hc
            hypercare_finish = env.now

    repo_summary = repo_metrics.summary_relative(planned_start)
    pipe_summary = pipe_metrics.summary_relative(planned_start)

    return CohortResult(
        wave_id=wave_id,
        cohort_id=cohort_id,
        start_hour=planned_start,
        repo_summary=repo_summary,
        pipe_summary=pipe_summary,
        finish_hour=cohort_finish_abs,
        hypercare_finish_hour=hypercare_finish,
        repos_planned=repos_planned,
        pipes_planned=pipes_planned,
        repo_reworks=repo_metrics.reworks,
        repo_escalations=repo_metrics.escalations,
        repo_main_hours=repo_metrics.main_hours,
        repo_rework_hours=repo_metrics.rework_hours,
        repo_triage_hours=repo_metrics.triage_hours,
        repo_swat_hours=repo_metrics.swat_hours,
        pipe_reworks=pipe_metrics.reworks,
        pipe_escalations=pipe_metrics.escalations,
        pipe_main_hours=pipe_metrics.main_hours,
        pipe_rework_hours=pipe_metrics.rework_hours,
        pipe_triage_hours=pipe_metrics.triage_hours,
        pipe_swat_hours=pipe_metrics.swat_hours,
    )

# =======================
# ====== EXECUTION ======
# =======================

def peak_engineers(cfg: dict, results=None) -> int:
    """Peak assigned roster: overlapping migration crews plus shared support pools."""
    if results is None:
        results = run_full_program(cfg)["results"]
    events = []
    for r in results:
        crew = (cfg["REPO_ENGINEERS_PER_COHORT"] if r.repos_planned else 0)
        crew += cfg["CI_ENGINEERS_PER_COHORT"] if r.pipes_planned else 0
        if r.finish_hour > r.start_hour:
            events.extend([(r.start_hour, crew), (r.finish_hour, -crew)])
    active = peak = 0
    for _, delta in sorted(events):
        active += delta
        peak = max(peak, active)
    return peak + cfg["TRIAGE_ENGINEERS_SHARED"] + cfg["SWAT_CORE_CAPACITY"] if events else 0

def program_wave_summaries(results: List[CohortResult]) -> Tuple[float, float]:
    if not results:
        return 0.0, 0.0

    waves = sorted({r.wave_id for r in results})
    spans = []
    for w in waves:
        group = [r for r in results if r.wave_id == w]
        if not group:
            continue
        wave_start = min(r.start_hour for r in group)
        wave_end = max((r.hypercare_finish_hour or r.finish_hour) for r in group)
        spans.append((wave_start, wave_end))

    if not spans:
        return 0.0, 0.0

    wave_makespans_days = [(end - start) / CAL_HOURS_PER_DAY for start, end in spans]
    avg_wave_finish_days = round(sum(wave_makespans_days) / len(wave_makespans_days), 2)
    overall_finish_days = round(
        (max(end for _, end in spans) - min(start for start, _ in spans)) / CAL_HOURS_PER_DAY,
        2,
    )
    return avg_wave_finish_days, overall_finish_days

def build_waves_df(results):
    if not results:
        return pd.DataFrame(columns=["Wave","WaveStart(d)","WaveEnd(d)","WaveDuration(d)"])

    waves = sorted({r.wave_id for r in results})
    rows = []
    for w in waves:
        group = [r for r in results if r.wave_id == w]
        wave_start = min(r.start_hour for r in group)
        wave_end = max((r.hypercare_finish_hour or r.finish_hour) for r in group)
        rows.append({
            "Wave": w,
            "WaveStart(d)": round(wave_start / CAL_HOURS_PER_DAY, 2),
            "WaveEnd(d)": round(wave_end / CAL_HOURS_PER_DAY, 2),
            "WaveDuration(d)": round((wave_end - wave_start) / CAL_HOURS_PER_DAY, 2),
            "WaveDuration(mo)": round(days_to_months((wave_end - wave_start) / CAL_HOURS_PER_DAY), 2),
        })
    return pd.DataFrame(rows).sort_values("Wave").reset_index(drop=True)

def validate_config(cfg: dict):
    """Fail before starting if configuration can lose work or stall the calendar."""
    import math
    for key in ("WAVES", "COHORTS_PER_WAVE", "REPOS_PER_COHORT", "PIPES_PER_COHORT",
                "REPO_ENGINEERS_PER_COHORT", "CI_ENGINEERS_PER_COHORT",
                "TRIAGE_ENGINEERS_SHARED", "SWAT_CORE_CAPACITY"):
        if not isinstance(cfg[key], int) or isinstance(cfg[key], bool) or cfg[key] <= 0:
            raise ValueError(f"{key}: expected a positive integer")
    for key in ("TOTAL_REPOS", "TOTAL_PIPES"):
        value = cfg.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError(f"{key}: expected a nonnegative integer or None")
    if cfg["ALLOCATION_MODE"] not in ("sequential", "even"):
        raise ValueError("ALLOCATION_MODE: use sequential or even")
    if not 0 <= cfg["WORKDAY_START_HOUR"] < cfg["WORKDAY_END_HOUR"] <= 24:
        raise ValueError("Working hours must satisfy 0 <= start < end <= 24")
    for key in ("WAVE_SPACING_DAYS", "COHORT_SPACING_DAYS", "TEMPLATES_READY_DAY",
                "HYPERCARE_WEEKS", "HYPERCARE_HOURS_PER_DAY"):
        if not math.isfinite(cfg[key]) or cfg[key] < 0:
            raise ValueError(f"{key}: expected a finite nonnegative value")
    if cfg["HYPERCARE_ENABLED"]:
        days = cfg["HYPERCARE_WEEKS"] * 5
        if days != int(days):
            raise ValueError("HYPERCARE_WEEKS * 5 must be an integer")
        window = cfg["WORKDAY_END_HOUR"] - cfg["WORKDAY_START_HOUR"] if cfg["BUSINESS_HOURS_ONLY"] else 24
        if cfg["HYPERCARE_HOURS_PER_DAY"] > window:
            raise ValueError("Daily hypercare cannot exceed one working day")
    for kind in ("REPO", "PIPE"):
        dist = cfg[f"{kind}_DIST"]
        if not dist or any(not math.isfinite(p) or p < 0 for p in dist.values()) or not math.isclose(sum(dist.values()), 1):
            raise ValueError(f"{kind}_DIST probabilities must sum to 1")
        if not set(dist) <= cfg[f"{kind}_TIMES"].keys():
            raise ValueError(f"{kind}_TIMES must define every task type")
    for key, value in cfg.items():
        if key.endswith("_TIMES"):
            bounds_list = value.values()
        elif key.endswith("_TIME") or key.startswith(("TRIAGE_TIME_", "SWAT_TIME_")):
            bounds_list = [value]
        else:
            continue
        for low, high in bounds_list:
            if not (math.isfinite(low) and math.isfinite(high) and 0 <= low <= high):
                raise ValueError(f"{key}: expected finite 0 <= low <= high")
    for key in ("REPO_REWORK_PROB", "PIPE_REWORK_PROB", "ESCALATION_PROB_COMPLEX_REPO",
                "ESCALATION_PROB_COMPLEX_PIPE", "REWORK_SCALER_REPO", "REWORK_SCALER_PIPE",
                "TRIAGE_ACCEL_FACTOR", "IMPR_MIN", "IMPR_MAX"):
        if not 0 <= cfg[key] <= 1:
            raise ValueError(f"{key}: expected a value between 0 and 1")
    if cfg["IMPR_MIN"] > cfg["IMPR_MAX"]:
        raise ValueError("IMPR_MIN must be <= IMPR_MAX")
    for key in ("DURATION_SCALER_REPO", "DURATION_SCALER_PIPE"):
        if not math.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(f"{key}: expected a positive finite value")
    slots = cfg["WAVES"] * cfg["COHORTS_PER_WAVE"]
    for total, cap in (("TOTAL_REPOS", "REPOS_PER_COHORT"), ("TOTAL_PIPES", "PIPES_PER_COHORT")):
        if cfg.get(total) is not None and cfg[total] > slots * cfg[cap]:
            raise ValueError(f"{total} exceeds total cohort capacity; increase waves or cohort size")


def preview_plan(cfg: dict) -> pd.DataFrame:
    validate_config(cfg)
    args = (cfg["WAVES"], cfg["COHORTS_PER_WAVE"], cfg["ALLOCATION_MODE"])
    repos = plan_allocation(cfg.get("TOTAL_REPOS"), cfg["REPOS_PER_COHORT"], *args)
    pipes = plan_allocation(cfg.get("TOTAL_PIPES"), cfg["PIPES_PER_COHORT"], *args)
    rows = []
    for i, (r, p) in enumerate(zip(repos, pipes)):
        w, c = divmod(i, cfg["COHORTS_PER_WAVE"])
        planned = w * cfg["WAVE_SPACING_DAYS"] + c * cfg["COHORT_SPACING_DAYS"]
        start = next_business_start(max(planned, cfg["TEMPLATES_READY_DAY"]) * 24, cfg)
        rows.append({"Wave": w + 1, "Cohort": c + 1, "Repos": r, "Pipelines": p,
                     "Active": bool(r or p), "Start(d)": start / 24 if r or p else None,
                     "RepoEngineers": cfg["REPO_ENGINEERS_PER_COHORT"] if r else 0,
                     "CIEngineers": cfg["CI_ENGINEERS_PER_COHORT"] if p else 0})
    return pd.DataFrame(rows)


def workload_with_load(out: dict, cfg: dict) -> pd.DataFrame:
    df = out["usage_totals_df"].copy()
    windows = {(r.wave_id, r.cohort_id): (r.start_hour, r.finish_hour) for r in out["results"]}
    loads = []
    for row in df.itertuples(index=False):
        _, w, c, _ = parse_engineer_id(row.Engineer)
        t0, t1 = windows.get((w, c), (out["program_start_hour"], out["program_end_hour"]))
        available = business_hours_between(t0, t1, cfg)
        loads.append(100 * row.Hours / available if available else 0)
    df["LoadPct"] = loads
    return df.sort_values("LoadPct", ascending=False).reset_index(drop=True)


def run_full_program(cfg: dict, quiet: bool = True) -> Dict[str, Any]:
    """Calendar durations are measured from day 0; active span is reported separately."""
    plan = preview_plan(cfg)
    rng = random.Random(cfg["SEED"])
    env = simpy.Environment()
    tracker = UsageTracker()
    triage_pool = simpy.Store(env, capacity=cfg["TRIAGE_ENGINEERS_SHARED"])
    triage_pool.items.extend(f"Triage:{i+1}" for i in range(cfg["TRIAGE_ENGINEERS_SHARED"]))
    swat_pool = simpy.Store(env, capacity=cfg["SWAT_CORE_CAPACITY"])
    swat_pool.items.extend(f"SWAT:{i+1}" for i in range(cfg["SWAT_CORE_CAPACITY"]))
    scalers = {"dur_repo": cfg["DURATION_SCALER_REPO"], "dur_pipe": cfg["DURATION_SCALER_PIPE"],
               "rwrk_repo": cfg["REWORK_SCALER_REPO"], "rwrk_pipe": cfg["REWORK_SCALER_PIPE"]}
    hook = cfg["IMPROVEMENT_HOOK"] or default_improvement_hook
    results = []

    def runner(row, wave_scalers):
        result = yield env.process(run_one_cohort(
            env, row.Wave, row.Cohort, row.StartHour,
            triage_pool, swat_pool, cfg, wave_scalers, rng, tracker, row.Repos, row.Pipelines))
        results.append(result)

    for w in range(1, cfg["WAVES"] + 1):
        wave_scalers = dict(scalers)
        for row in plan.assign(StartHour=plan["Start(d)"] * 24).loc[lambda df: (df["Wave"] == w) & df["Active"]].itertuples(index=False):
            env.process(runner(row, wave_scalers))
        scalers = hook(scalers, w, rng, cfg)
    env.run()
    results.sort(key=lambda r: (r.wave_id, r.cohort_id))
    start = min((r.start_hour for r in results), default=0)
    migration_end = max((r.finish_hour for r in results), default=0)
    end = max((r.hypercare_finish_hour if r.hypercare_finish_hour is not None else r.finish_hour
               for r in results), default=0)
    avg_wave, _ = program_wave_summaries(results)
    out = {
        "results": results, "plan_df": plan, "waves_df": build_waves_df(results),
        "program_start_hour": start, "program_end_hour": end,
        "migration_finish_days": migration_end / 24, "overall_finish_days": end / 24,
        "active_span_days": (end - start) / 24, "avg_wave_finish_days": avg_wave,
        "avg_wave_finish_months": days_to_months(avg_wave), "overall_finish_months": days_to_months(end / 24),
        "worst_repo_p95_days": max((r.repo_summary.get("p95_hours", 0) for r in results), default=0) / 24,
        "worst_pipe_p95_days": max((r.pipe_summary.get("p95_hours", 0) for r in results), default=0) / 24,
        "processed_repos": sum(r.repos_planned for r in results),
        "processed_pipes": sum(r.pipes_planned for r in results),
        "usage_df": tracker.segments_df(), "usage_totals_df": tracker.totals_df(),
        "usage_monthly_df": tracker.monthly_df(),
    }
    out["peak_engineers"] = peak_engineers(cfg, results)
    out["usage_load_df"] = workload_with_load(out, cfg)
    out["rework_stats"] = {}
    for kind, prefix, count in (("repos", "repo", out["processed_repos"]), ("pipes", "pipe", out["processed_pipes"])):
        reworks = sum(getattr(r, f"{prefix}_reworks") for r in results)
        stats = {"count": reworks, "rate_pct": 100 * reworks / count if count else 0,
                 "escalations": sum(getattr(r, f"{prefix}_escalations") for r in results)}
        for metric in ("main_hours", "rework_hours", "triage_hours", "swat_hours"):
            stats[metric] = sum(getattr(r, f"{prefix}_{metric}") for r in results)
        out["rework_stats"][kind] = stats
    if not quiet:
        print(f"Repos: {out['processed_repos']}; pipelines: {out['processed_pipes']}; "
              f"migration: {migration_end / 24:.2f} d; with hypercare: {end / 24:.2f} d")
    return out


# =======================
# === SWEEP & PARETO ====
# =======================

def staffing_sweep(base_cfg: dict,
                   repo_eng_list: List[int],
                   ci_eng_list: List[int],
                   triage_shared_list: List[int],
                   name_prefix: str = "FullProgram",
                   suppress_txt_out: bool = True) -> pd.DataFrame:
    rows = []
    for re in repo_eng_list:
        for ci in ci_eng_list:
            for tr in triage_shared_list:
                sc = dict(base_cfg)
                sc["REPO_ENGINEERS_PER_COHORT"] = re
                sc["CI_ENGINEERS_PER_COHORT"] = ci
                sc["TRIAGE_ENGINEERS_SHARED"] = tr
                sc["name"] = f"{name_prefix}: REPO={re}, CI={ci}, TRIAGE={tr}"

                out = run_full_program(sc, quiet=suppress_txt_out)
                avg_wave_days = out["avg_wave_finish_days"]
                overall_days  = out["overall_finish_days"]

                rows.append({
                    "Scenario": sc["name"],
                    "Waves": sc["WAVES"],
                    "Cohorts/Wave": sc["COHORTS_PER_WAVE"],
                    "Spacing(d)": sc["COHORT_SPACING_DAYS"],
                    "WaveSpacing(d)": sc["WAVE_SPACING_DAYS"],
                    "TemplatesReady(d)": sc["TEMPLATES_READY_DAY"],
                    "RepoEng/Coh": re,
                    "CIEng/Coh": ci,
                    "Triage(shared)": tr,
                    "CoreSWAT": sc["SWAT_CORE_CAPACITY"],
                    "PeakEng": out["peak_engineers"],
                    "Repo P95(d)": out["worst_repo_p95_days"],
                    "Pipe P95(d)": out["worst_pipe_p95_days"],
                    "Avg Wave Finish(d)": avg_wave_days,
                    "Avg Wave Finish(mo)": days_to_months(avg_wave_days),
                    "Overall Finish(d)": overall_days,
                    "Overall Finish(mo)": days_to_months(overall_days),
                })

    df = pd.DataFrame(rows)
    cols = [
        "Scenario","Waves","Cohorts/Wave","Spacing(d)","WaveSpacing(d)","TemplatesReady(d)",
        "RepoEng/Coh","CIEng/Coh","Triage(shared)","CoreSWAT","PeakEng",
        "Repo P95(d)","Pipe P95(d)",
        "Avg Wave Finish(d)","Avg Wave Finish(mo)",
        "Overall Finish(d)","Overall Finish(mo)"
    ]
    return df[cols]

def pareto_frontier(df: pd.DataFrame,
                    x_col: str = "PeakEng",
                    y_col: str = "Overall Finish(d)") -> pd.DataFrame:
    mask = paretoset(df[[x_col, y_col]], sense=["min", "min"])
    frontier = df[mask].sort_values([y_col, x_col]).reset_index(drop=True)
    return frontier



def compare_scenarios(base_cfg: dict, scenarios: dict, seeds: list[int]) -> pd.DataFrame:
    """One simulation per scenario and seed; preserve raw rows for inspection."""
    from copy import deepcopy
    if not seeds:
        raise ValueError("Provide at least one seed")
    rows = []
    for name, overrides in scenarios.items():
        for seed in seeds:
            cfg = deepcopy(base_cfg)
            cfg.update(overrides)
            cfg["SEED"] = seed
            out = run_full_program(cfg)
            rows.append({"Scenario": name, "Seed": seed,
                         "MigrationDays": out["migration_finish_days"],
                         "FinishDays": out["overall_finish_days"], "PeakEng": out["peak_engineers"],
                         "Hours": out["usage_totals_df"]["Hours"].sum()})
    return pd.DataFrame(rows)


def summarize_scenarios(runs: pd.DataFrame) -> pd.DataFrame:
    summary = runs.groupby("Scenario", sort=False).agg(
        Runs=("Seed", "size"), PeakEng=("PeakEng", "max"),
        MigrationMedianDays=("MigrationDays", "median"),
        FinishMedianDays=("FinishDays", "median"),
        FinishP10Days=("FinishDays", lambda s: s.quantile(.1)),
        FinishP90Days=("FinishDays", lambda s: s.quantile(.9)),
        MeanHours=("Hours", "mean")).reset_index()
    summary["Pareto"] = paretoset(summary[["PeakEng", "FinishMedianDays"]], sense=["min", "min"])
    return summary
