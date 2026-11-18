"""命令行入口：

    python -m solution --input cases.json --output result.json

输入文件视为不可信数据：以 UTF-8 读取，仅用 json 标准库解析；
解析失败或顶层结构非法时输出 E_MALFORMED_INPUT 结构错误而不是抛栈。
"""

from __future__ import annotations

import argparse
import json
import sys

from .pipeline import solve_case
from .validation import validate_document


def run(raw: object) -> dict:
    parsed_cases, doc_errors = validate_document(raw)
    results = []
    for case in parsed_cases:
        results.append(solve_case(case))
    for err in doc_errors:
        results.append({
            "case": err["case"],
            "status": "structural_error",
            "errors": err["errors"],
        })
    return {"results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="合成安全审计日志的会话两端匹配与歧义分析")
    parser.add_argument("--input", required=True, help="输入 cases.json 路径")
    parser.add_argument("--output", required=True, help="输出 result.json 路径")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        payload = {
            "results": [{
                "case": None,
                "status": "structural_error",
                "errors": [{
                    "code": "E_MALFORMED_INPUT",
                    "message": "输入文件无法读取或不是合法 JSON",
                    "detail": {"reason": str(exc)},
                }],
            }]
        }
    else:
        payload = run(raw)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
