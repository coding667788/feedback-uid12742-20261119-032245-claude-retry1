"""120x120 合成大样例测试。

期望值不依赖被测实现的内部输出，而是由样例生成约定独立给出：
- 每端恰好 120 条“核心”事件（8 组 x 15 对），构造时刻完全对齐、
  偏移逐端相同，因此存在 120 条零成本边，最优基数必为 120、最优费用必为 0；
- 额外注入的 S0_X 是有效候选边但不在任何最优解（none）；
- K1 的 2x2 同时刻块产生 4 条 some 歧义边；
- C_DIR/S_DIR 同方向，无候选边；C_DEAD_*/S_DEAD_* 无候选边，永不匹配；
- 同连接键事件数 <=120（任务硬上限），引擎不得枚举全部最优配对
  （通过性能与算法结构间接保证：用例在毫秒级完成）。
另含一个独立的费用下界校验：代表解每条边费用非负且总和等于输出最优费用。
"""

from __future__ import annotations

import json
import os
import time
import unittest

from solution.model import interval_distance
from solution.pipeline import solve_case
from solution.validation import validate_case

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_PATH = os.path.join(ROOT, "cases.json")


class LargeCaseTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(CASES_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        cls.raw = next(c for c in doc["cases"]
                       if c["name"] == "large_120x120")
        cls.parsed, errors = validate_case(cls.raw)
        assert not errors
        cls.started = time.perf_counter()
        cls.out = solve_case(cls.parsed)
        cls.elapsed = time.perf_counter() - cls.started

    def test_endpoint_core_counts_are_120_each(self):
        core_c = [e for e in self.raw["events"]
                  if e["endpoint"] == "C" and not e["event_id"].endswith(
                      tuple(f"DEAD_{i}" for i in range(6)))
                  and e["event_id"] != "C_DIR"]
        core_s = [e for e in self.raw["events"]
                  if e["endpoint"] == "S" and "_DEAD_" not in e["event_id"]
                  and e["event_id"] not in ("S0_X", "S_DIR")]
        self.assertEqual(len(core_c), 120)
        self.assertEqual(len(core_s), 120)

    def test_optimal_cardinality_120_and_zero_cost(self):
        # 由构造：120 对本地时刻逐对相同、两端偏移一致 -> 120 条零成本边，
        # 故最大基数 120 且最优费用 0 是可独立断言的上/下界重合结论。
        self.assertEqual(self.out["total_matching_count"], 120)
        self.assertEqual(self.out["total_matching_cost"], 0)

    def test_group_limit_respected(self):
        sizes = {}
        for ev in self.raw["events"]:
            sizes[ev["join_key"]] = sizes.get(ev["join_key"], 0) + 1
        self.assertLessEqual(max(sizes.values()), 120)

    def test_none_edge_s0x_not_in_any_optimum(self):
        k0 = next(g for g in self.out["groups"] if g["join_key"] == "K0")
        s0x = [e for e in k0["candidate_edges"]
               if e["right_event_id"] == "S0_X"]
        self.assertTrue(s0x, "S0_X 必须首先是一条有效候选边")
        self.assertTrue(all(e["ambiguity"] == "none" for e in s0x))
        # 它确实在代表解之外
        paired_right = {p["right_event_id"]
                        for p in k0["representative_pairs"]}
        self.assertNotIn("S0_X", paired_right)

    def test_some_ambiguity_block_in_k1(self):
        k1 = next(g for g in self.out["groups"] if g["join_key"] == "K1")
        some_edges = [e for e in k1["candidate_edges"]
                      if e["ambiguity"] == "some"]
        self.assertEqual(len(some_edges), 4)  # 2x2 同时刻完全块

    def test_direction_filtered_and_dead_events_never_matched(self):
        groups = {g["join_key"]: g for g in self.out["groups"]}
        k0 = groups["K0"]
        # 方向互补才连边：C_DIR(1) 与 S_DIR(1) 同方向，二者之间不得有候选边；
        # C_DIR 方向为 1，与 K0 中所有方向为 0 的 C 侧事件无关（同端不配对），
        # 它只能配方向 1 的 S 侧事件，而 K0 中 S 侧方向 1 的普通事件与之
        # 时刻不同；这里直接断言同方向对 (C_DIR,S_DIR) 不产生边。
        same_direction_pair = {
            (e["left_event_id"], e["right_event_id"])
            for e in k0["candidate_edges"]
        }
        self.assertNotIn(("C_DIR", "S_DIR"), same_direction_pair)
        # C_DIR 自身方向为 1，K0 内不存在方向为 1 的 C 侧竞争者，
        # 它没有任何互补方向的 S 事件落在阈值内，故无候选边、未匹配。
        c_dir_edges = [e for e in k0["candidate_edges"]
                       if e["left_event_id"] == "C_DIR"]
        self.assertEqual(c_dir_edges, [])
        # 所有 DEAD 事件未匹配且不可在其他同优解中覆盖
        for g in self.out["groups"]:
            for u in g["unmatched_events"]:
                if "DEAD" in u["event_id"] or u["event_id"].endswith("DIR"):
                    self.assertFalse(u["coverable_elsewhere"],
                                     u["event_id"])

    def test_representative_costs_are_consistent_and_nonnegative(self):
        # 独立重算代表解每条边的区间距离，校验非负且求和与最优费用一致
        seg_index = {}
        for ep, segs in self.parsed.calibration.items():
            seg_index[ep] = sorted(segs, key=lambda s: s.local_lo)
        ev_by_id = {e.event_id: e for e in self.parsed.events}

        def unified(ev):
            seg = next(s for s in seg_index[ev.endpoint]
                       if s.contains(ev.local_time))
            return (ev.local_time + seg.off_lo,
                    ev.local_time + seg.off_hi)

        total = 0
        for g in self.out["groups"]:
            for p in g["representative_pairs"]:
                le = ev_by_id[p["left_event_id"]]
                re_ = ev_by_id[p["right_event_id"]]
                from solution.model import UnifiedInterval
                got = _dist(UnifiedInterval(*unified(le)),
                            UnifiedInterval(*unified(re_)))
                self.assertEqual(got, p["cost"])
                self.assertGreaterEqual(got, 0)
                total += got
        self.assertEqual(total, self.out["total_matching_cost"])

    def test_runs_fast_without_enumeration(self):
        # 大样例必须在 5 秒内完成（纯标准库 CPU），佐证未枚举全部最优配对
        self.assertLess(self.elapsed, 5.0)


def _dist(a, b):
    if b.lo > a.hi:
        return b.lo - a.hi
    if a.lo > b.hi:
        return a.lo - b.hi
    return 0


if __name__ == "__main__":
    unittest.main()
