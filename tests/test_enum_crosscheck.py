"""独立枚举交叉验证。

对 cases.json 中所有 <=8x8 的合法小用例：
- 用 tests/ref_enum.py（与 solution 零共享代码的回溯枚举）独立得到
  最优基数、最优费用、字典序最小代表、全部边标签与未匹配可覆盖性；
- 与 solution 流水线输出逐字段比对。
另含乱序输入不变性：c01 与其乱序副本的结果必须语义一致。
"""

from __future__ import annotations

import json
import os
import unittest

from solution.pipeline import solve_case
from solution.validation import validate_case

from tests.ref_enum import enumerate_reference

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_PATH = os.path.join(ROOT, "cases.json")


def _load_raw_cases() -> list[dict]:
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def _engine_output(raw_case: dict) -> dict:
    parsed, errors = validate_case(raw_case)
    assert not errors
    return solve_case(parsed)


class EnumerationCrossCheckTest(unittest.TestCase):

    def test_all_small_cases_match_brute_force(self):
        raw_cases = _load_raw_cases()
        checked = 0
        for raw in raw_cases:
            name = raw["name"]
            if name.startswith("err_") or name.startswith("large"):
                continue
            # 枚举器内部会对 >8x8 直接断言失败，这里再做一次显式门槛
            if any(len([e for e in raw["events"]
                        if e["join_key"] == k and e["endpoint"]
                        == raw["endpoint_a"]]) > 8
                   or len([e for e in raw["events"]
                           if e["join_key"] == k
                           and e["endpoint"] == raw["endpoint_b"]]) > 8
                   for k in {e["join_key"] for e in raw["events"]}):
                continue

            expected = enumerate_reference(raw)
            actual = _engine_output(raw)

            self.assertEqual(
                actual["total_matching_count"],
                expected["total_matching_count"], name)
            self.assertEqual(
                actual["total_matching_cost"],
                expected["total_matching_cost"], name)

            actual_groups = {g["join_key"]: g for g in actual["groups"]}
            for key, exp in expected["groups"].items():
                got = actual_groups[key]
                self.assertEqual(got["matching_count"],
                                 exp["matching_count"], f"{name}/{key}")
                self.assertEqual(got["matching_cost"],
                                 exp["matching_cost"], f"{name}/{key}")
                # 字典序最小代表
                got_pairs = [(p["left_event_id"], p["right_event_id"])
                             for p in got["representative_pairs"]]
                self.assertEqual(got_pairs, exp["representative_pairs"],
                                 f"{name}/{key}")
                # 边标签 all/some/none
                got_labels = {
                    (e["left_event_id"], e["right_event_id"]):
                        e["ambiguity"]
                    for e in got["candidate_edges"]
                }
                self.assertEqual(got_labels, exp["edge_labels"],
                                 f"{name}/{key}")
                # 未匹配可覆盖性
                got_cover = {u["event_id"]: u["coverable_elsewhere"]
                             for u in got["unmatched_events"]}
                for eid, flag in got_cover.items():
                    self.assertEqual(flag, eid in exp["coverable"],
                                     f"{name}/{key}/{eid}")
            checked += 1
        self.assertGreaterEqual(checked, 20,
                                "应至少交叉验证 20 个小用例")

    def test_shuffled_input_gives_identical_semantics(self):
        raw_cases = {c["name"]: c for c in _load_raw_cases()}
        base = _engine_output(raw_cases["c01_full_ambiguity"])
        shuffled = _engine_output(raw_cases["c01_shuffled"])
        # 代表解、标签、可覆盖性等全部语义字段一致（用例名除外）
        base = dict(base)
        shuffled = dict(shuffled)
        base.pop("case")
        shuffled.pop("case")
        self.assertEqual(base, shuffled)


if __name__ == "__main__":
    unittest.main()
