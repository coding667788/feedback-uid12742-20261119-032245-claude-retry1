"""数据模型与区间数学。

时间约定（任务书）：
- 校准区间按单端本地时间 **左闭右开** [lo, hi)，整数端点，且必须 lo < hi。
- 每段校准给出偏移不确定区间 [off_lo, off_hi]（两个整数端点，闭区间）。
- 事件本地时刻 t 落入某段后，其统一时刻区间为 [t+off_lo, t+off_hi]（闭区间）。
- 两条事件连边的代价 = 两个统一时刻闭区间的最小绝对距离；
  区间相交/相切时距离为 0。
- 阈值采用 **小于或等于**：距离 <= threshold 即候选边。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationSegment:
    """一段校准：本地时间 [local_lo, local_hi) 内适用偏移 [off_lo, off_hi]。"""

    local_lo: int
    local_hi: int
    off_lo: int
    off_hi: int

    def contains(self, local_time: int) -> bool:
        return self.local_lo <= local_time < self.local_hi


@dataclass(frozen=True)
class Event:
    """一条安全审计事件。"""

    event_id: str
    join_key: str
    endpoint: str
    direction: int  # 0 / 1，互补即方向不同
    local_time: int


@dataclass(frozen=True)
class UnifiedInterval:
    """事件经校准映射后的统一时刻闭区间 [lo, hi]。"""

    lo: int
    hi: int


@dataclass(frozen=True)
class CalibrationSource:
    """事件使用的校准来源（逐段可追溯）。"""

    local_lo: int
    local_hi: int
    off_lo: int
    off_hi: int
    unified_lo: int
    unified_hi: int

    def to_dict(self) -> dict:
        return {
            "calibration_local_lo": self.local_lo,
            "calibration_local_hi": self.local_hi,
            "offset_lo": self.off_lo,
            "offset_hi": self.off_hi,
            "unified_lo": self.unified_lo,
            "unified_hi": self.unified_hi,
        }


def interval_distance(a: UnifiedInterval, b: UnifiedInterval) -> int:
    """两个闭区间的最小绝对距离（相交或相切为 0）。"""
    if b.lo > a.hi:
        return b.lo - a.hi
    if a.lo > b.hi:
        return a.lo - b.hi
    return 0


def unified_interval(event: Event, seg: CalibrationSegment) -> UnifiedInterval:
    """本地时刻 + 偏移不确定区间 -> 统一时刻闭区间。"""
    return UnifiedInterval(event.local_time + seg.off_lo,
                           event.local_time + seg.off_hi)
