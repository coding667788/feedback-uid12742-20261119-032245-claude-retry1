"""从解析后的用例装配分组、建边、求解并组装输出。"""

from __future__ import annotations

from bisect import bisect_right

from .matching import FeasibleEdge, solve_group
from .model import (CalibrationSegment, CalibrationSource, Event,
                    UnifiedInterval, interval_distance, unified_interval)
from .validation import ParsedCase


def _find_segment(segs: list[CalibrationSegment],
                  local_time: int) -> CalibrationSegment | None:
    """段已按 local_lo 升序且首尾相接；二分定位覆盖 local_time 的段。"""
    keys = [s.local_lo for s in segs]
    idx = bisect_right(keys, local_time) - 1
    if idx >= 0 and segs[idx].contains(local_time):
        return segs[idx]
    return None


def _event_calibration(case: ParsedCase, ev: Event) -> CalibrationSource:
    seg = _find_segment(case.calibration[ev.endpoint], ev.local_time)
    # 校验阶段已保证覆盖，seg 必非空
    assert seg is not None
    ui = unified_interval(ev, seg)
    return CalibrationSource(seg.local_lo, seg.local_hi, seg.off_lo, seg.off_hi,
                             ui.lo, ui.hi)


def solve_case(case: ParsedCase) -> dict:
    sources = {ev.event_id: _event_calibration(case, ev) for ev in case.events}
    intervals: dict[str, UnifiedInterval] = {
        eid: UnifiedInterval(src.unified_lo, src.unified_hi)
        for eid, src in sources.items()
    }

    # 按连接键分组；配对只发生在约定两端之间
    groups: dict[str, list[Event]] = {}
    for ev in case.events:
        groups.setdefault(ev.join_key, []).append(ev)

    total_cardinality = 0
    total_cost = 0
    group_outputs: list[dict] = []

    for join_key in sorted(groups):
        members = groups[join_key]
        left_events = [e for e in members if e.endpoint == case.endpoint_a]
        right_events = [e for e in members if e.endpoint == case.endpoint_b]
        left_events.sort(key=lambda e: e.event_id)
        right_events.sort(key=lambda e: e.event_id)
        n_left, n_right = len(left_events), len(right_events)

        feasible: list[FeasibleEdge] = []
        cost_lookup: dict[tuple[int, int], int] = {}
        for li, le in enumerate(left_events):
            for ri, re in enumerate(right_events):
                # 方向必须互补（0/1 取值不同）
                if le.direction == re.direction:
                    continue
                d = interval_distance(intervals[le.event_id],
                                      intervals[re.event_id])
                # 阈值采用 <=
                if d <= case.threshold:
                    feasible.append(FeasibleEdge(li, ri, d))
                    cost_lookup[(li, ri)] = d

        # 规范顺序：先按左侧事件 ID、再按右侧事件 ID 的字典序
        canonical_order = sorted(
            ((e.left_index, e.right_index) for e in feasible),
            key=lambda p: (left_events[p[0]].event_id,
                           right_events[p[1]].event_id),
        )

        sol = solve_group(n_left, n_right, feasible, canonical_order)
        total_cardinality += sol.cardinality
        total_cost += sol.total_cost

        pairs_out = []
        for li, ri in sorted(
            sol.matching.items(),
            key=lambda p: (left_events[p[0]].event_id,
                           right_events[p[1]].event_id),
        ):
            le, re = left_events[li], right_events[ri]
            pairs_out.append({
                "left_event_id": le.event_id,
                "right_event_id": re.event_id,
                "left_endpoint": case.endpoint_a,
                "right_endpoint": case.endpoint_b,
                "cost": cost_lookup[(li, ri)],
                "left_unified": [intervals[le.event_id].lo,
                                 intervals[le.event_id].hi],
                "right_unified": [intervals[re.event_id].lo,
                                  intervals[re.event_id].hi],
            })

        edges_out = []
        for li, ri in canonical_order:
            le, re = left_events[li], right_events[ri]
            edges_out.append({
                "left_event_id": le.event_id,
                "right_event_id": re.event_id,
                "cost": cost_lookup[(li, ri)],
                "ambiguity": sol.edge_labels[(li, ri)],
            })

        unmatched_out = []
        matched_left = set(sol.matching)
        matched_right = set(sol.matching.values())
        for li, le in enumerate(left_events):
            if li not in matched_left:
                unmatched_out.append({
                    "event_id": le.event_id,
                    "endpoint": le.endpoint,
                    "coverable_elsewhere": li in
                    sol.coverable_unmatched_left,
                })
        for ri, re in enumerate(right_events):
            if ri not in matched_right:
                unmatched_out.append({
                    "event_id": re.event_id,
                    "endpoint": re.endpoint,
                    "coverable_elsewhere": ri in
                    sol.coverable_unmatched_right,
                })
        unmatched_out.sort(key=lambda x: x["event_id"])

        group_outputs.append({
            "join_key": join_key,
            "left_size": n_left,
            "right_size": n_right,
            "matching_count": sol.cardinality,
            "matching_cost": sol.total_cost,
            "representative_pairs": pairs_out,
            "candidate_edges": edges_out,
            "unmatched_events": unmatched_out,
        })

    return {
        "case": case.name,
        "status": "ok",
        "threshold": case.threshold,
        "endpoint_a": case.endpoint_a,
        "endpoint_b": case.endpoint_b,
        "total_matching_count": total_cardinality,
        "total_matching_cost": total_cost,
        "calibration_sources": {
            eid: src.to_dict() for eid, src in sorted(sources.items())
        },
        "groups": group_outputs,
    }
