"""生成可重放的 cases.json（纯标准库、固定随机种子）。

用例构成：
- c01..c06：手工设计的小用例（歧义、none 边、阈值边界、分段偏移切换、
  左闭右开边界、不可覆盖未匹配、可覆盖未匹配）；
- c01_shuffled：c01 的乱序输入副本，输出必须逐字节语义一致；
- fuzz_*：固定种子随机小图（<=8x8），供枚举交叉验证；
- large_120x120：120 条/端的合成大用例（分 8 个连接键组），
  含偏移切换、none 候选边、some 歧异块、方向过滤与不可匹配事件；
- err_*：全部结构错误码各一例。
"""

from __future__ import annotations

import random


def _ev(event_id, join_key, endpoint, direction, local_time):
    return {
        "event_id": event_id,
        "join_key": join_key,
        "endpoint": endpoint,
        "direction": direction,
        "local_time": local_time,
    }


def _case_c01():
    """2x2 全零成本：两条最优匹配，四条候选边全部 some。"""
    return {
        "name": "c01_full_ambiguity",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 5,
        "calibration": {
            "C": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
            "S": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
        },
        "events": [
            _ev("L1", "k", "C", 0, 10),
            _ev("L2", "k", "C", 0, 10),
            _ev("R1", "k", "S", 1, 10),
            _ev("R2", "k", "S", 1, 10),
        ],
    }


def _case_c02():
    """唯一最优匹配 + 一条候选有效但不在任何最优解的 none 边。"""
    return {
        "name": "c02_none_edge",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 5,
        "calibration": {
            "C": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
            "S": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
        },
        "events": [
            _ev("L1", "k", "C", 0, 0),
            _ev("L2", "k", "C", 0, 4),
            _ev("R1", "k", "S", 1, 0),
            _ev("R2", "k", "S", 1, 4),
        ],
    }


def _case_c03():
    """阈值 <= 边界 + 偏移不确定区间：距离恰为阈值可连边。"""
    return {
        "name": "c03_threshold_boundary",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 2,
        "calibration": {
            # C: 统一区间 [t, t+2]
            "C": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 2}],
            # S: 统一区间 [t, t+1]
            "S": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 1}],
        },
        "events": [
            _ev("L1", "k", "C", 0, 0),    # [0,2]
            _ev("L2", "k", "C", 0, 10),   # [10,12]
            _ev("R1", "k", "S", 1, 3),    # [3,4]，与 L1 距离 1
            _ev("R2", "k", "S", 1, 14),   # [14,15]，与 L2 距离恰为 2（阈值内）
            _ev("R3", "k", "S", 1, 20),   # [20,21]，与 L2 距离 8（不可连）
        ],
    }


def _case_c04():
    """分段校准偏移切换 + 左闭右开边界（599 属段1、600 属段2）。"""
    return {
        "name": "c04_offset_switch",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 0,
        "calibration": {
            "C": [
                {"local_lo": 0, "local_hi": 600,
                 "offset_lo": 10, "offset_hi": 10},
                {"local_lo": 600, "local_hi": 1200,
                 "offset_lo": -10, "offset_hi": -10},
            ],
            "S": [
                {"local_lo": 0, "local_hi": 600,
                 "offset_lo": 0, "offset_hi": 0},
                {"local_lo": 600, "local_hi": 1200,
                 "offset_lo": 0, "offset_hi": 0},
            ],
        },
        "events": [
            _ev("L1", "k", "C", 0, 599),   # 统一 609（段1）
            _ev("L2", "k", "C", 0, 600),   # 统一 590（段2，左边界切换）
            _ev("R1", "k", "S", 1, 609),   # 统一 609 -> 配 L1
            _ev("R2", "k", "S", 1, 590),   # 统一 590 -> 配 L2
        ],
    }


def _case_c05():
    """永远无法匹配的未匹配事件：方向相同 + 超出阈值。"""
    return {
        "name": "c05_unmatchable",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 1,
        "calibration": {
            "C": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
            "S": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
        },
        "events": [
            _ev("L1", "k", "C", 0, 0),
            _ev("L2", "k", "C", 0, 100),    # 方向相同且距离 100
            _ev("R1", "k", "S", 1, 0),
            _ev("R2", "k", "S", 0, 100),    # 与 L2 同方向，互补失败
        ],
    }


def _case_c06():
    """可在别的同优解被匹配的未匹配事件（代表解下未匹配但可覆盖）。"""
    return {
        "name": "c06_coverable_unmatched",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 5,
        "calibration": {
            "C": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
            "S": [{"local_lo": 0, "local_hi": 1000,
                   "offset_lo": 0, "offset_hi": 0}],
        },
        "events": [
            # k 组：L1 同时零成本可达 R1/R2，代表解取 (L1,R1)，R2 未匹配但可覆盖
            _ev("L1", "k", "C", 0, 10),
            _ev("R1", "k", "S", 1, 10),
            _ev("R2", "k", "S", 1, 10),
            # g 组：L2/L3 争 R3，代表字典序 L2-R3，L3 未匹配但可覆盖
            _ev("L2", "g", "C", 0, 20),
            _ev("L3", "g", "C", 0, 20),
            _ev("R3", "g", "S", 1, 20),
        ],
    }


def _fuzz_cases(seed=20261119, count=24):
    """固定种子随机小图（每组 <=6 条/端），覆盖随机校准与阈值。

    为产生非平凡匹配，右侧事件围绕左侧时刻生成，方向按互补概率取；
    同时保留少量完全随机事件制造 none 边与未匹配。
    """
    rng = random.Random(seed)
    cases = []
    for idx in range(count):
        n_groups = rng.randint(1, 3)
        cut = rng.randint(200, 800)
        two_segments = rng.random() < 0.5
        cal_c, cal_s = [], []
        for ep_cal in (cal_c, cal_s):
            lo1 = rng.randint(-4, 4)
            ep_cal.append({
                "local_lo": 0,
                "local_hi": cut if two_segments else 2000,
                "offset_lo": lo1,
                "offset_hi": lo1 + rng.randint(0, 6),
            })
            if two_segments:
                lo2 = rng.randint(-4, 4)
                ep_cal.append({
                    "local_lo": cut, "local_hi": 2000,
                    "offset_lo": lo2,
                    "offset_hi": lo2 + rng.randint(0, 6),
                })
        events = []
        eid = 0
        for g in range(n_groups):
            key = f"g{g}"
            n_l = rng.randint(2, 6)
            n_r = rng.randint(2, 6)
            left_times = [rng.randint(100, 1900) for _ in range(n_l)]
            for t in left_times:
                events.append(_ev(f"E{eid:03d}", key, "C",
                                  rng.choice((0, 0, 1)), t))
                eid += 1
            for j in range(n_r):
                # 70% 围绕某个左时刻抖动，30% 完全随机
                if rng.random() < 0.7:
                    t = rng.choice(left_times) + rng.randint(-8, 8)
                else:
                    t = rng.randint(0, 1999)
                t = max(0, min(1999, t))
                events.append(_ev(f"E{eid:03d}", key, "S",
                                  rng.choice((0, 1, 1)), t))
                eid += 1
        cases.append({
            "name": f"fuzz_{idx:02d}",
            "endpoint_a": "C",
            "endpoint_b": "S",
            "threshold": rng.randint(0, 10),
            "calibration": {"C": cal_c, "S": cal_s},
            "events": events,
        })
    return cases


def _large_case():
    """120 条/端的合成大用例，分 8 个连接键组。"""
    rng = random.Random(424242)
    switch_c, switch_s = 5000, 5000
    cal = {
        "C": [
            {"local_lo": 0, "local_hi": switch_c,
             "offset_lo": 100, "offset_hi": 100},
            {"local_lo": switch_c, "local_hi": 20000,
             "offset_lo": -20, "offset_hi": -20},
        ],
        "S": [
            {"local_lo": 0, "local_hi": switch_s,
             "offset_lo": 100, "offset_hi": 100},
            {"local_lo": switch_s, "local_hi": 20000,
             "offset_lo": -20, "offset_hi": -20},
        ],
    }
    events = []
    # 8 组，每组 15 对 -> 120 条/端
    for g in range(8):
        key = f"K{g}"
        for i in range(15):
            base = g * 1000 + i * 30
            local = base if g < 4 else base + 5200  # 后四组落段2
            events.append(_ev(f"C{g}_{i:02d}", key, "C", 0, local))
            events.append(_ev(f"S{g}_{i:02d}", key, "S", 1, local))

    # some 歧义块：K1 的前两对本地时刻相同 -> 2x2 零成本完全块
    for i in (0, 1):
        for ev in events:
            if ev["event_id"] in (f"C1_{i:02d}", f"S1_{i:02d}"):
                ev["local_time"] = 1100

    # none 候选边：K0 增加一个右端点，与 C0_00 距离 5（阈值 25 内），
    # 但 C0_00 已有零成本配对，该边不在任何最优解中。
    events.append(_ev("S0_X", "K0", "S", 1,
                      next(e["local_time"] for e in events
                           if e["event_id"] == "C0_00") + 5))

    # 方向过滤：同方向事件不产生候选边
    events.append(_ev("C_DIR", "K0", "C", 1, 42))
    events.append(_ev("S_DIR", "K0", "S", 1, 42))

    # 不可匹配事件（各 6 条，加入 K0..K5）：统一时刻相距很远，无候选边
    for i in range(6):
        events.append(_ev(f"C_DEAD_{i}", f"K{i}", "C", 0, 15000 + i))
        events.append(_ev(f"S_DEAD_{i}", f"K{i}", "S", 1, 100 + i))

    rng.shuffle(events)  # 大样例本身也乱序输入
    return {
        "name": "large_120x120",
        "endpoint_a": "C",
        "endpoint_b": "S",
        "threshold": 25,
        "calibration": cal,
        "events": events,
    }


def _error_cases():
    base_cal = [{"local_lo": 0, "local_hi": 1000,
                 "offset_lo": 0, "offset_hi": 0}]
    return [
        {
            "name": "err_duplicate_id",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {"C": base_cal, "S": base_cal},
            "events": [
                _ev("DUP", "k", "C", 0, 1),
                _ev("DUP", "k", "S", 1, 1),
            ],
        },
        {
            "name": "err_calibration_gap",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {
                "C": [
                    {"local_lo": 0, "local_hi": 100,
                     "offset_lo": 0, "offset_hi": 0},
                    {"local_lo": 200, "local_hi": 300,
                     "offset_lo": 0, "offset_hi": 0},
                ],
                "S": base_cal,
            },
            "events": [_ev("L1", "k", "C", 0, 50),
                       _ev("R1", "k", "S", 1, 50)],
        },
        {
            "name": "err_calibration_overlap",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {
                "C": [
                    {"local_lo": 0, "local_hi": 150,
                     "offset_lo": 0, "offset_hi": 0},
                    {"local_lo": 100, "local_hi": 300,
                     "offset_lo": 0, "offset_hi": 0},
                ],
                "S": base_cal,
            },
            "events": [_ev("L1", "k", "C", 0, 120),
                       _ev("R1", "k", "S", 1, 50)],
        },
        {
            "name": "err_event_outside_calibration",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {
                "C": [{"local_lo": 0, "local_hi": 100,
                       "offset_lo": 0, "offset_hi": 0}],
                "S": base_cal,
            },
            "events": [_ev("L1", "k", "C", 0, 100),  # 100 不在 [0,100)
                       _ev("R1", "k", "S", 1, 50)],
        },
        {
            "name": "err_unknown_endpoint",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {"C": base_cal, "S": base_cal},
            "events": [_ev("X1", "k", "Z", 0, 10),
                       _ev("R1", "k", "S", 1, 10)],
        },
        {
            "name": "err_malformed_direction",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {"C": base_cal, "S": base_cal},
            "events": [_ev("L1", "k", "C", 2, 10),
                       _ev("R1", "k", "S", 1, 10)],
        },
        {
            "name": "err_boolean_as_int",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {"C": base_cal, "S": base_cal},
            "events": [{
                "event_id": "L1", "join_key": "k", "endpoint": "C",
                "direction": 0, "local_time": True,
            }, _ev("R1", "k", "S", 1, 10)],
        },
        {
            "name": "err_missing_calibration",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {"C": base_cal},
            "events": [_ev("L1", "k", "C", 0, 10),
                       _ev("R1", "k", "S", 1, 10)],
        },
        {
            "name": "err_group_limit",
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "calibration": {"C": base_cal, "S": base_cal},
            "events": [_ev(f"E{i:03d}", "k",
                           "C" if i % 2 == 0 else "S", i % 2, i)
                       for i in range(121)],
        },
    ]


def build_document() -> dict:
    small = [_case_c01(), _case_c02(), _case_c03(), _case_c04(),
             _case_c05(), _case_c06()]
    shuffled = _case_c01()
    shuffled["name"] = "c01_shuffled"
    import random as _r
    _r.Random(7).shuffle(shuffled["events"])
    cases = small + [shuffled] + _fuzz_cases() + [_large_case()] + _error_cases()
    return {"schema_version": 1, "cases": cases}


if __name__ == "__main__":
    import json
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "cases.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build_document(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {out}")
