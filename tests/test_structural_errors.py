"""结构错误码测试：cases.json 中每个 err_* 用例必须命中预期错误码，
且错误用例不产生正常结果。
"""

from __future__ import annotations

import json
import os
import unittest

from solution.__main__ import run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_PATH = os.path.join(ROOT, "cases.json")

EXPECTED_CODES = {
    "err_duplicate_id": "E_DUPLICATE_EVENT_ID",
    "err_calibration_gap": "E_CALIBRATION_GAP",
    "err_calibration_overlap": "E_CALIBRATION_OVERLAP",
    "err_event_outside_calibration": "E_EVENT_OUTSIDE_CALIBRATION",
    "err_unknown_endpoint": "E_UNKNOWN_ENDPOINT",
    "err_malformed_direction": "E_MALFORMED_INPUT",
    "err_boolean_as_int": "E_MALFORMED_INPUT",
    "err_missing_calibration": "E_CALIBRATION_GAP",
    "err_group_limit": "E_GROUP_LIMIT",
}


class StructuralErrorTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(CASES_PATH, "r", encoding="utf-8") as f:
            cls.document = json.load(f)

    def test_each_error_case_hits_expected_code(self):
        result = run(self.document)
        by_case = {r["case"]: r for r in result["results"]}
        for name, expected_code in EXPECTED_CODES.items():
            with self.subTest(case=name):
                self.assertIn(name, by_case)
                r = by_case[name]
                self.assertEqual(r["status"], "structural_error")
                codes = [e["code"] for e in r["errors"]]
                self.assertIn(expected_code, codes)

    def test_error_cases_have_no_ok_result(self):
        result = run(self.document)
        for r in result["results"]:
            if r["case"] in EXPECTED_CODES:
                self.assertEqual(r["status"], "structural_error")

    def test_top_level_malformed_document(self):
        result = run(["not", "an", "object"])
        self.assertEqual(result["results"][0]["status"], "structural_error")
        self.assertEqual(result["results"][0]["errors"][0]["code"],
                         "E_MALFORMED_INPUT")

    def test_gap_and_overlap_are_distinct_codes(self):
        # 独立构造：缺口与重叠必须区分，而不是合并为同一错误
        base_seg = [{"local_lo": 0, "local_hi": 100,
                     "offset_lo": 0, "offset_hi": 0}]
        common = {
            "endpoint_a": "C", "endpoint_b": "S", "threshold": 1,
            "events": [
                {"event_id": "L1", "join_key": "k", "endpoint": "C",
                 "direction": 0, "local_time": 10},
                {"event_id": "R1", "join_key": "k", "endpoint": "S",
                 "direction": 1, "local_time": 10},
            ],
        }
        gap = dict(common, name="gap", calibration={
            "C": base_seg + [{"local_lo": 200, "local_hi": 300,
                              "offset_lo": 0, "offset_hi": 0}],
            "S": [{"local_lo": 0, "local_hi": 400,
                   "offset_lo": 0, "offset_hi": 0}]})
        overlap = dict(common, name="overlap", calibration={
            "C": [
                {"local_lo": 0, "local_hi": 150,
                 "offset_lo": 0, "offset_hi": 0},
                {"local_lo": 100, "local_hi": 300,
                 "offset_lo": 0, "offset_hi": 0},
            ],
            "S": [{"local_lo": 0, "local_hi": 400,
                   "offset_lo": 0, "offset_hi": 0}]})
        from solution.validation import validate_case
        _, e_gap = validate_case(gap)
        _, e_over = validate_case(overlap)
        self.assertIn("E_CALIBRATION_GAP", [e.code for e in e_gap])
        self.assertIn("E_CALIBRATION_OVERLAP",
                      [e.code for e in e_over])


if __name__ == "__main__":
    unittest.main()
