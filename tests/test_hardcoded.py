"""手工设计用例的硬编码断言。

期望值全部由人工独立推导（见每个方法注释中的推导），
不从被测实现的输出反推。
"""

from __future__ import annotations

import unittest

from solution.validation import validate_case
from solution.pipeline import solve_case


def _solve(raw_case: dict) -> dict:
    parsed, errors = validate_case(raw_case)
    assert not errors, [e.to_dict() for e in errors]
    return solve_case(parsed)


def _ev(event_id, join_key, endpoint, direction, local_time):
    return {"event_id": event_id, "join_key": join_key, "endpoint": endpoint,
            "direction": direction, "local_time": local_time}


ZERO_CAL = {
    "C": [{"local_lo": 0, "local_hi": 10000,
           "offset_lo": 0, "offset_hi": 0}],
    "S": [{"local_lo": 0, "local_hi": 10000,
           "offset_lo": 0, "offset_hi": 0}],
}


class HardcodedExpectationsTest(unittest.TestCase):

    def test_c01_full_ambiguity_all_edges_some(self):
        # 2x2 完全图、零费用、阈值内。最优匹配有两个：
        # {(L1,R1),(L2,R2)} 与 {(L1,R2),(L2,R1)}；
        # 每条边恰好出现在一个最优解中 -> some；代表解字典序最小
        # 取 (L1,R1),(L2,R2)。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 5, "calibration": ZERO_CAL,
            "events": [
                _ev("L1", "k", "C", 0, 10), _ev("L2", "k", "C", 0, 10),
                _ev("R1", "k", "S", 1, 10), _ev("R2", "k", "S", 1, 10),
            ],
        }
        out = _solve(raw)
        g = out["groups"][0]
        self.assertEqual(g["matching_count"], 2)
        self.assertEqual(g["matching_cost"], 0)
        self.assertEqual(
            [(p["left_event_id"], p["right_event_id"])
             for p in g["representative_pairs"]],
            [("L1", "R1"), ("L2", "R2")],
        )
        self.assertEqual(
            {e["left_event_id"] + e["right_event_id"]: e["ambiguity"]
             for e in g["candidate_edges"]},
            {"L1R1": "some", "L1R2": "some",
             "L2R1": "some", "L2R2": "some"},
        )
        self.assertEqual(out["total_matching_count"], 2)

    def test_c02_none_edge_and_all_edge(self):
        # L1(t=0),L2(t=4); R1(t=0),R2(t=4)，阈值 5。
        # 最大基数 2 的唯一零费用匹配：(L1,R1),(L2,R2)。
        # 交叉边 (L1,R2) 费用 4、(L2,R1) 费用 4：候选有效，
        # 但任何含交叉边的基数 2 匹配被迫同时取另一条交叉边，费用 8 > 0，
        # 故两条交叉边均为 none；两条直边为 all。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 5, "calibration": ZERO_CAL,
            "events": [
                _ev("L1", "k", "C", 0, 0), _ev("L2", "k", "C", 0, 4),
                _ev("R1", "k", "S", 1, 0), _ev("R2", "k", "S", 1, 4),
            ],
        }
        out = _solve(raw)
        g = out["groups"][0]
        labels = {e["left_event_id"] + e["right_event_id"]: e["ambiguity"]
                  for e in g["candidate_edges"]}
        self.assertEqual(labels, {
            "L1R1": "all", "L1R2": "none",
            "L2R1": "none", "L2R2": "all",
        })
        self.assertEqual(
            [(p["left_event_id"], p["right_event_id"])
             for p in g["representative_pairs"]],
            [("L1", "R1"), ("L2", "R2")],
        )

    def test_c03_threshold_uses_less_or_equal(self):
        # L2 区间 [10,12]，R2 区间 [14,15]，距离恰为阈值 2 -> 可连边；
        # R3 [20,21] 距离 8 -> 无候选边。L1-R1 距离 1。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 2,
            "calibration": {
                "C": [{"local_lo": 0, "local_hi": 10000,
                       "offset_lo": 0, "offset_hi": 2}],
                "S": [{"local_lo": 0, "local_hi": 10000,
                       "offset_lo": 0, "offset_hi": 1}],
            },
            "events": [
                _ev("L1", "k", "C", 0, 0), _ev("L2", "k", "C", 0, 10),
                _ev("R1", "k", "S", 1, 3), _ev("R2", "k", "S", 1, 14),
                _ev("R3", "k", "S", 1, 20),
            ],
        }
        out = _solve(raw)
        g = out["groups"][0]
        edge_ids = {(e["left_event_id"], e["right_event_id"])
                    for e in g["candidate_edges"]}
        self.assertIn(("L2", "R2"), edge_ids)   # 距离 == 阈值，<= 生效
        self.assertNotIn(("L2", "R3"), edge_ids)
        self.assertEqual(g["matching_count"], 2)
        # 费用：L1-R1 = 1（[0,2] vs [3,4]），L2-R2 = 2
        self.assertEqual(g["matching_cost"], 3)
        # R3 永远无法被覆盖
        r3 = next(u for u in g["unmatched_events"]
                  if u["event_id"] == "R3")
        self.assertFalse(r3["coverable_elsewhere"])

    def test_c04_half_open_boundary_and_offset_switch(self):
        # C 段1 [0,600) 偏移 +10；段2 [600,1200) 偏移 -10。
        # L1 本地 599 -> 统一 609；L2 本地 600 -> 统一 590。
        # 阈值 0：只有完全对齐可配，验证左闭右开切换。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 0,
            "calibration": {
                "C": [
                    {"local_lo": 0, "local_hi": 600,
                     "offset_lo": 10, "offset_hi": 10},
                    {"local_lo": 600, "local_hi": 1200,
                     "offset_lo": -10, "offset_hi": -10},
                ],
                "S": [{"local_lo": 0, "local_hi": 1200,
                       "offset_lo": 0, "offset_hi": 0}],
            },
            "events": [
                _ev("L1", "k", "C", 0, 599), _ev("L2", "k", "C", 0, 600),
                _ev("R1", "k", "S", 1, 609), _ev("R2", "k", "S", 1, 590),
            ],
        }
        out = _solve(raw)
        g = out["groups"][0]
        self.assertEqual(
            sorted((p["left_event_id"], p["right_event_id"])
                   for p in g["representative_pairs"]),
            [("L1", "R1"), ("L2", "R2")],
        )
        self.assertEqual(g["matching_cost"], 0)
        src_l1 = out["calibration_sources"]["L1"]
        src_l2 = out["calibration_sources"]["L2"]
        self.assertEqual((src_l1["calibration_local_lo"],
                          src_l1["calibration_local_hi"]), (0, 600))
        self.assertEqual((src_l2["calibration_local_lo"],
                          src_l2["calibration_local_hi"]), (600, 1200))
        self.assertEqual((src_l1["unified_lo"], src_l1["unified_hi"]),
                         (609, 609))
        self.assertEqual((src_l2["unified_lo"], src_l2["unified_hi"]),
                         (590, 590))

    def test_c05_direction_filter_and_unmatchable(self):
        # L2/R2 同方向（互补失败），L1/R1 唯一可配。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 1, "calibration": ZERO_CAL,
            "events": [
                _ev("L1", "k", "C", 0, 0), _ev("L2", "k", "C", 0, 100),
                _ev("R1", "k", "S", 1, 0), _ev("R2", "k", "S", 0, 100),
            ],
        }
        out = _solve(raw)
        g = out["groups"][0]
        self.assertEqual(g["matching_count"], 1)
        self.assertEqual(
            [(p["left_event_id"], p["right_event_id"])
             for p in g["representative_pairs"]], [("L1", "R1")])
        unmatched = {u["event_id"]: u["coverable_elsewhere"]
                     for u in g["unmatched_events"]}
        self.assertEqual(unmatched, {"L2": False, "R2": False})
        # 唯一候选边标签为 all
        self.assertEqual(len(g["candidate_edges"]), 1)
        self.assertEqual(g["candidate_edges"][0]["ambiguity"], "all")

    def test_c06_coverable_unmatched_events(self):
        # k 组：L1 同时零成本可达 R1,R2 -> 代表取 R1，R2 未匹配但可覆盖；
        # g 组：L2,L3 同时刻争 R3 -> 代表取 L2，L3 未匹配但可覆盖。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 5, "calibration": ZERO_CAL,
            "events": [
                _ev("L1", "k", "C", 0, 10),
                _ev("R1", "k", "S", 1, 10), _ev("R2", "k", "S", 1, 10),
                _ev("L2", "g", "C", 0, 20), _ev("L3", "g", "C", 0, 20),
                _ev("R3", "g", "S", 1, 20),
            ],
        }
        out = _solve(raw)
        groups = {g["join_key"]: g for g in out["groups"]}
        k_unmatched = {u["event_id"]: u["coverable_elsewhere"]
                       for u in groups["k"]["unmatched_events"]}
        g_unmatched = {u["event_id"]: u["coverable_elsewhere"]
                       for u in groups["g"]["unmatched_events"]}
        self.assertEqual(k_unmatched, {"R2": True})
        self.assertEqual(g_unmatched, {"L3": True})
        # 歧义块内边均为 some
        self.assertTrue(all(e["ambiguity"] == "some"
                            for e in groups["k"]["candidate_edges"]))

    def test_interval_touch_distance_zero(self):
        # 区间相切：C [0,2]、S [2,3]，距离 0，阈值 0 即可连边。
        raw = {
            "name": "t", "endpoint_a": "C", "endpoint_b": "S",
            "threshold": 0,
            "calibration": {
                "C": [{"local_lo": 0, "local_hi": 100,
                       "offset_lo": 0, "offset_hi": 2}],
                "S": [{"local_lo": 0, "local_hi": 100,
                       "offset_lo": 2, "offset_hi": 3}],
            },
            "events": [_ev("L1", "k", "C", 0, 0),
                       _ev("R1", "k", "S", 1, 0)],
        }
        out = _solve(raw)
        g = out["groups"][0]
        self.assertEqual(g["matching_count"], 1)
        self.assertEqual(g["matching_cost"], 0)


if __name__ == "__main__":
    unittest.main()
