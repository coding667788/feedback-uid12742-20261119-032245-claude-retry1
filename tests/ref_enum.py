"""独立枚举参考实现（仅供测试，禁止用于大样例）。

与被测 solution 包完全隔离：不 import solution 任何模块，区间数学、
连边规则、最优分层、字典序代表、歧义标签全部在此重新实现一遍，
通过回溯穷举所有二分匹配，作为小图（<=8x8）的独立判定真值。
"""

from __future__ import annotations


def _iv_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """闭区间最小绝对距离，独立于 solution.model 重写。"""
    if b[0] > a[1]:
        return b[0] - a[1]
    if a[0] > b[1]:
        return a[0] - b[1]
    return 0


def _covering_segment(segments, local_time):
    for seg in segments:  # 左闭右开，线性扫描（小数据）
        if seg[0] <= local_time < seg[1]:
            return seg
    return None


def enumerate_reference(case: dict) -> dict:
    """输入为 cases.json 中单个原始用例 dict，返回独立判定的期望值。

    返回结构键：
      groups: {join_key: {matching_count, matching_cost,
                          representative_pairs, edge_labels,
                          coverable}}
      total_matching_count, total_matching_cost
    """
    ep_a, ep_b = case["endpoint_a"], case["endpoint_b"]
    threshold = case["threshold"]

    # 端点 -> [(local_lo, local_hi, off_lo, off_hi)]
    cal = {}
    for ep, segs in case["calibration"].items():
        cal[ep] = [(s["local_lo"], s["local_hi"],
                    s["offset_lo"], s["offset_hi"]) for s in segs]

    # 事件 -> 统一时刻闭区间
    unified = {}
    for ev in case["events"]:
        seg = _covering_segment(cal[ev["endpoint"]], ev["local_time"])
        if seg is None:
            raise AssertionError("枚举参考只接受已通过结构校验的用例")
        unified[ev["event_id"]] = (ev["local_time"] + seg[2],
                                   ev["local_time"] + seg[3])

    by_key: dict[str, list[dict]] = {}
    for ev in case["events"]:
        by_key.setdefault(ev["join_key"], []).append(ev)

    out_groups = {}
    total_k = total_c = 0

    for key, members in by_key.items():
        left = sorted((e for e in members if e["endpoint"] == ep_a),
                      key=lambda e: e["event_id"])
        right = sorted((e for e in members if e["endpoint"] == ep_b),
                       key=lambda e: e["event_id"])

        # 独立重建候选边（连接键已由分组保证；异端点由左右划分保证）
        cost = {}
        for li, le in enumerate(left):
            for ri, re in enumerate(right):
                if le["direction"] == re["direction"]:
                    continue
                d = _iv_distance(unified[le["event_id"]],
                                 unified[re["event_id"]])
                if d <= threshold:  # 阈值 <=
                    cost[(li, ri)] = d

        # 回溯穷举全部匹配（每左点至多一条、每右点至多一条）
        all_matchings: list[frozenset[tuple[int, int]]] = []

        def backtrack(li: int, chosen: frozenset, used_r: frozenset) -> None:
            if li == len(left):
                all_matchings.append(chosen)
                return
            backtrack(li + 1, chosen, used_r)  # 左点留空
            for ri in range(len(right)):
                if ri in used_r:
                    continue
                if (li, ri) in cost:
                    backtrack(li + 1,
                              chosen | {(li, ri)},
                              used_r | {ri})

        backtrack(0, frozenset(), frozenset())
        if len(left) > 8 or len(right) > 8:
            raise AssertionError("枚举参考仅允许 8x8 以下小图")

        # 第一层：最大基数；第二层：最小总代价
        best_k = max(len(m) for m in all_matchings)
        best_c = min(sum(cost[p] for p in m)
                     for m in all_matchings if len(m) == best_k)
        optimal = [m for m in all_matchings
                   if len(m) == best_k and
                   sum(cost[p] for p in m) == best_c]

        # 第三层：规范 ID 对列表字典序最小
        def canonical_pairs(matching):
            return sorted(
                ((left[li]["event_id"], right[ri]["event_id"])
                 for li, ri in matching),
            )

        rep = min(optimal, key=canonical_pairs)

        # 边标签：all / some / none
        labels = {}
        for pair in cost:
            appearances = sum(1 for m in optimal if pair in m)
            if appearances == len(optimal):
                labels[pair] = "all"
            elif appearances == 0:
                labels[pair] = "none"
            else:
                labels[pair] = "some"

        # 未匹配事件能否在别的同优解中被匹配
        rep_left = {li for li, _ in rep}
        rep_right = {ri for _, ri in rep}
        coverable = set()
        for li, le in enumerate(left):
            if li not in rep_left and any(li in {p[0] for p in m}
                                          for m in optimal):
                coverable.add(le["event_id"])
        for ri, re in enumerate(right):
            if ri not in rep_right and any(ri in {p[1] for p in m}
                                           for m in optimal):
                coverable.add(re["event_id"])

        out_groups[key] = {
            "matching_count": best_k,
            "matching_cost": best_c,
            "representative_pairs": canonical_pairs(rep),
            "edge_labels": {
                (left[li]["event_id"], right[ri]["event_id"]): lab
                for (li, ri), lab in labels.items()
            },
            "coverable": coverable,
        }
        total_k += best_k
        total_c += best_c

    return {
        "groups": out_groups,
        "total_matching_count": total_k,
        "total_matching_cost": total_c,
    }
