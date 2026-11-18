"""输入结构校验。

错误码（README 同步维护）：
- E_MALFORMED_INPUT             类型/字段缺失/取值非法（布尔冒充整数等）
- E_DUPLICATE_EVENT_ID          同一用例内事件 ID 重复
- E_CALIBRATION_GAP             校准段之间存在缺口，或端点完全没有校准
- E_CALIBRATION_OVERLAP         校准段相互重叠（未严格首尾相接）
- E_EVENT_OUTSIDE_CALIBRATION   事件本地时刻不被任何左闭右开校准段覆盖
- E_UNKNOWN_ENDPOINT            事件/校准引用了未约定的端点
- E_GROUP_LIMIT                 同一连接键的事件数超过 120
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import CalibrationSegment, Event

# 任务书：一组连接键最多各 120 条事件
MAX_EVENTS_PER_JOIN_KEY = 120


@dataclass
class ParsedCase:
    name: str
    endpoint_a: str
    endpoint_b: str
    threshold: int
    # endpoint -> 按本地时间升序、首尾相接的校准段
    calibration: dict[str, list[CalibrationSegment]]
    events: list[Event] = field(default_factory=list)


@dataclass
class StructuralError(Exception):
    code: str
    message: str
    detail: dict

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


def _is_strict_int(x) -> bool:
    """bool 是 int 的子类，任务要求整数，显式拒绝布尔。"""
    return isinstance(x, int) and not isinstance(x, bool)


def _is_nonempty_str(x) -> bool:
    return isinstance(x, str) and len(x) > 0


def _err(code: str, message: str, **detail) -> StructuralError:
    return StructuralError(code, message, detail)


def validate_case(raw: object) -> tuple[ParsedCase | None, list[StructuralError]]:
    """校验单个用例；返回 (解析结果, 错误列表)。有错时解析结果为 None。"""
    errors: list[StructuralError] = []

    if not isinstance(raw, dict):
        return None, [_err("E_MALFORMED_INPUT", "用例必须是 JSON 对象", got=type(raw).__name__)]

    name = raw.get("name")
    if not _is_nonempty_str(name):
        errors.append(_err("E_MALFORMED_INPUT", "name 必须是非空字符串"))

    endpoint_a = raw.get("endpoint_a")
    endpoint_b = raw.get("endpoint_b")
    if not _is_nonempty_str(endpoint_a):
        errors.append(_err("E_MALFORMED_INPUT", "endpoint_a 必须是非空字符串"))
    if not _is_nonempty_str(endpoint_b):
        errors.append(_err("E_MALFORMED_INPUT", "endpoint_b 必须是非空字符串"))
    if (
        _is_nonempty_str(endpoint_a)
        and _is_nonempty_str(endpoint_b)
        and endpoint_a == endpoint_b
    ):
        errors.append(_err("E_MALFORMED_INPUT", "两个约定端点必须不同",
                           endpoint=endpoint_a))

    threshold = raw.get("threshold")
    if not _is_strict_int(threshold) or threshold < 0:
        errors.append(_err("E_MALFORMED_INPUT",
                           "threshold 必须是非负整数（比较采用 <="))

    known_endpoints = {endpoint_a, endpoint_b} - {None}
    calibration: dict[str, list[CalibrationSegment]] = {}

    raw_cal = raw.get("calibration")
    if not isinstance(raw_cal, dict):
        errors.append(_err("E_MALFORMED_INPUT", "calibration 必须是对象"))
        raw_cal = {}

    for ep, segs in raw_cal.items():
        if not _is_nonempty_str(ep) or ep not in known_endpoints:
            errors.append(_err("E_UNKNOWN_ENDPOINT",
                               "校准引用了未约定的端点", endpoint=str(ep)))
            continue
        if not isinstance(segs, list) or len(segs) == 0:
            errors.append(_err("E_MALFORMED_INPUT",
                               "校准段列表必须是非空数组", endpoint=ep))
            continue
        parsed_segs: list[CalibrationSegment] = []
        for idx, seg in enumerate(segs):
            if not isinstance(seg, dict):
                errors.append(_err("E_MALFORMED_INPUT",
                                   "校准段必须是对象", endpoint=ep, index=idx))
                continue
            lo = seg.get("local_lo")
            hi = seg.get("local_hi")
            off_lo = seg.get("offset_lo")
            off_hi = seg.get("offset_hi")
            ints_ok = all(_is_strict_int(v) for v in (lo, hi, off_lo, off_hi))
            if not ints_ok:
                errors.append(_err("E_MALFORMED_INPUT",
                                   "校准段四个端点必须都是整数",
                                   endpoint=ep, index=idx))
                continue
            if lo >= hi:
                errors.append(_err("E_MALFORMED_INPUT",
                                   "校准本地区间必须左闭右开且 lo < hi",
                                   endpoint=ep, index=idx, local_lo=lo, local_hi=hi))
                continue
            if off_lo > off_hi:
                errors.append(_err("E_MALFORMED_INPUT",
                                   "偏移不确定区间必须 offset_lo <= offset_hi",
                                   endpoint=ep, index=idx))
                continue
            parsed_segs.append(CalibrationSegment(lo, hi, off_lo, off_hi))

        # 排序后检查缺口/重叠：合法的分段必须严格首尾相接
        parsed_segs.sort(key=lambda s: s.local_lo)
        for prev, cur in zip(parsed_segs, parsed_segs[1:]):
            if cur.local_lo < prev.local_hi:
                errors.append(_err("E_CALIBRATION_OVERLAP",
                                   "校准段相互重叠",
                                   endpoint=ep,
                                   prev_hi=prev.local_hi, cur_lo=cur.local_lo))
            elif cur.local_lo > prev.local_hi:
                errors.append(_err("E_CALIBRATION_GAP",
                                   "校准段之间存在缺口（本地时间未覆盖）",
                                   endpoint=ep,
                                   prev_hi=prev.local_hi, cur_lo=cur.local_lo))
        if parsed_segs:
            calibration[ep] = parsed_segs

    # 两个约定端点都必须有校准
    for ep in known_endpoints:
        if ep not in calibration:
            errors.append(_err("E_CALIBRATION_GAP",
                               "约定端点缺少任何校准段", endpoint=ep))

    events: list[Event] = []
    seen_ids: set[str] = set()
    raw_events = raw.get("events")
    if not isinstance(raw_events, list):
        errors.append(_err("E_MALFORMED_INPUT", "events 必须是数组"))
        raw_events = []

    for idx, ev in enumerate(raw_events):
        if not isinstance(ev, dict):
            errors.append(_err("E_MALFORMED_INPUT",
                               "事件必须是对象", index=idx))
            continue
        event_id = ev.get("event_id")
        join_key = ev.get("join_key")
        endpoint = ev.get("endpoint")
        direction = ev.get("direction")
        local_time = ev.get("local_time")

        bad = False
        if not _is_nonempty_str(event_id):
            errors.append(_err("E_MALFORMED_INPUT",
                               "event_id 必须是非空字符串", index=idx))
            bad = True
        elif event_id in seen_ids:
            errors.append(_err("E_DUPLICATE_EVENT_ID",
                               "事件 ID 在用例内重复", event_id=event_id))
            bad = True
        if not _is_nonempty_str(join_key):
            errors.append(_err("E_MALFORMED_INPUT",
                               "join_key 必须是非空字符串", index=idx))
            bad = True
        if not _is_nonempty_str(endpoint) or endpoint not in known_endpoints:
            errors.append(_err("E_UNKNOWN_ENDPOINT",
                               "事件引用了未约定的端点",
                               index=idx, endpoint=str(endpoint)))
            bad = True
        if direction not in (0, 1):
            errors.append(_err("E_MALFORMED_INPUT",
                               "direction 只允许 0 或 1（互补即取值不同）",
                               index=idx, direction=direction))
            bad = True
        if not _is_strict_int(local_time):
            errors.append(_err("E_MALFORMED_INPUT",
                               "local_time 必须是整数", index=idx))
            bad = True
        if bad:
            continue
        seen_ids.add(event_id)
        events.append(Event(event_id, join_key, endpoint, direction, local_time))

    # 事件本地时刻必须被某段 [lo, hi) 覆盖
    if not errors:
        group_sizes: dict[str, int] = {}
        for ev in events:
            segs = calibration.get(ev.endpoint, ())
            covering = [s for s in segs if s.contains(ev.local_time)]
            if not covering:
                errors.append(_err("E_EVENT_OUTSIDE_CALIBRATION",
                                   "事件本地时刻不在任何左闭右开校准段内",
                                   event_id=ev.event_id,
                                   endpoint=ev.endpoint,
                                   local_time=ev.local_time))
            group_sizes[ev.join_key] = group_sizes.get(ev.join_key, 0) + 1
        for key, size in group_sizes.items():
            if size > MAX_EVENTS_PER_JOIN_KEY:
                errors.append(_err("E_GROUP_LIMIT",
                                   "同一连接键事件数超过 120",
                                   join_key=key, size=size))

    if errors:
        return None, errors

    return (
        ParsedCase(name, endpoint_a, endpoint_b, threshold, calibration, events),
        [],
    )


def validate_document(raw: object) -> tuple[list[ParsedCase], list[dict]]:
    """校验整份文档。结构错误按用例收集，不阻断其他用例。"""
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        malformed = _err("E_MALFORMED_INPUT",
                         "顶层文档必须是含 cases 数组的对象")
        return [], [{"case": None, "errors": [malformed.to_dict()]}]

    parsed_cases: list[ParsedCase] = []
    doc_errors: list[dict] = []
    for idx, raw_case in enumerate(raw["cases"]):
        parsed, errors = validate_case(raw_case)
        if errors:
            case_name = raw_case.get("name") if isinstance(raw_case, dict) else None
            doc_errors.append({
                "case": case_name if _is_nonempty_str(case_name) else f"#{idx}",
                "errors": [e.to_dict() for e in errors],
            })
        if parsed is not None:
            parsed_cases.append(parsed)
    return parsed_cases, doc_errors
