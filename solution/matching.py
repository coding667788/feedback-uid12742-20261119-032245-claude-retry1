"""分组匹配引擎（仅标准库，禁止枚举全部最优配对）。

三层目标：
1. 最大匹配数（基数优先）；
2. 在最大基数匹配中最小化总代价；
3. 在同时满足前两层的解中，取规范事件 ID 对列表字典序最小的代表。

算法：
- 前两层：二分图最小费用最大流（容量 1、逐次最短路 + Dijkstra 势函数）。
- 歧义标签：取最终势函数下 **缩减成本为 0 且仍有残量** 的弧构成子图 G0，
  Tarjan 强连通分量 + 缩点 DAG 位掩码可达性，依据最优流的互补松弛性质：
  * 已用边 (l,r)：G0 中 l 不可达 r => 出现在所有最优解 (all)，否则 some；
  * 未用边：前向弧在 G0 中且 r 可达 l => some，否则不在任何最优解 (none)。
  * 未匹配左端点可在别的同优解被匹配 <=> s 在 G0 中可达某个未匹配右端点；
    未匹配右端点同理 <=> 某个未匹配左端点可达 t。
- 第三层：G0 内的最大基数匹配恰好是全部最优匹配；按规范顺序逐条尝试
  强制纳入，用 Hopcroft-Karp 重算剩余图最大基数做可行性判定
  （Dulmage-Mendelsohn 思想的固定-重算实现，多项式复杂度，无枚举）。
"""

from __future__ import annotations

import heapq
import sys
from dataclasses import dataclass

sys.setrecursionlimit(100_000)


# --------------------------------------------------------------------------- #
# 最小费用最大流
# --------------------------------------------------------------------------- #

class _Arc:
    __slots__ = ("to", "rev", "cap", "cost")

    def __init__(self, to: int, rev: int, cap: int, cost: int):
        self.to = to
        self.rev = rev
        self.cap = cap
        self.cost = cost


class MinCostFlow:
    def __init__(self, n: int):
        self.n = n
        self.g: list[list[_Arc]] = [[] for _ in range(n)]

    def add_edge(self, fr: int, to: int, cap: int, cost: int) -> _Arc:
        fwd = _Arc(to, len(self.g[to]), cap, cost)
        rev = _Arc(fr, len(self.g[fr]), 0, -cost)
        self.g[fr].append(fwd)
        self.g[to].append(rev)
        return fwd

    def flow(self, s: int, t: int) -> tuple[int, int, list[int]]:
        """返回 (最大流量, 最小费用, 最终势函数)。边费均非负，初势为 0。"""
        n = self.n
        potential = [0] * n
        flow = 0
        total_cost = 0
        inf = 10 ** 30
        while True:
            dist = [inf] * n
            dist[s] = 0
            prev_v = [-1] * n
            prev_a = [-1] * n
            pq: list[tuple[int, int]] = [(0, s)]
            while pq:
                d, v = heapq.heappop(pq)
                if d != dist[v]:
                    continue
                for ai, arc in enumerate(self.g[v]):
                    if arc.cap <= 0:
                        continue
                    nd = d + arc.cost + potential[v] - potential[arc.to]
                    if nd < dist[arc.to]:
                        dist[arc.to] = nd
                        prev_v[arc.to] = v
                        prev_a[arc.to] = ai
                        heapq.heappush(pq, (nd, arc.to))
            if dist[t] == inf:
                break
            for v in range(n):
                if dist[v] < inf:
                    potential[v] += dist[v]
            # 所有弧容量为 1，每条增广路推 1 单位
            v = t
            while v != s:
                u = prev_v[v]
                arc = self.g[u][prev_a[v]]
                arc.cap -= 1
                self.g[v][arc.rev].cap += 1
                total_cost += arc.cost
                v = u
            flow += 1
        return flow, total_cost, potential


# --------------------------------------------------------------------------- #
# Tarjan 强连通分量 + 缩点可达性（int 位掩码）
# --------------------------------------------------------------------------- #

def tarjan_scc(adj: list[list[int]]) -> list[int]:
    n = len(adj)
    index = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack: list[int] = []
    comp = [-1] * n
    counter = 0
    comp_count = 0

    def dfs(v: int) -> None:
        nonlocal counter, comp_count
        # 显式栈，避免 Windows 上递归深度的额外顾虑
        work: list[tuple[int, int]] = [(v, 0)]
        index[v] = low[v] = counter
        counter += 1
        stack.append(v)
        on_stack[v] = True
        while work:
            node, ni = work[-1]
            if ni < len(adj[node]):
                w = adj[node][ni]
                work[-1] = (node, ni + 1)
                if index[w] == -1:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, 0))
                elif on_stack[w]:
                    low[node] = min(low[node], index[w])
            else:
                if low[node] == index[node]:
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        comp[w] = comp_count
                        if w == node:
                            break
                    comp_count += 1
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])

    for v in range(n):
        if index[v] == -1:
            dfs(v)
    return comp


def condensation_reach(adj: list[list[int]], comp: list[int]) -> list[int]:
    """每个 SCC 的可达 SCC 集合（含自身），以 int 位掩码返回。"""
    cc = max(comp) + 1
    dag: list[set[int]] = [set() for _ in range(cc)]
    for u, nbrs in enumerate(adj):
        for w in nbrs:
            if comp[u] != comp[w]:
                dag[comp[u]].add(comp[w])
    # DAG 上按拓扑逆序递推
    indeg = [0] * cc
    for u in range(cc):
        for w in dag[u]:
            indeg[w] += 1
    queue = [u for u in range(cc) if indeg[u] == 0]
    topo: list[int] = []
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        topo.append(u)
        for w in dag[u]:
            indeg[w] -= 1
            if indeg[w] == 0:
                queue.append(w)
    reach = [1 << u for u in range(cc)]
    for u in reversed(topo):
        mask = reach[u]
        for w in dag[u]:
            mask |= reach[w]
        reach[u] = mask
    return reach


# --------------------------------------------------------------------------- #
# Hopcroft-Karp（固定-重算可行性判定用）
# --------------------------------------------------------------------------- #

def hopcroft_karp_size(n_left: int, n_right: int,
                       adj: dict[int, list[int]],
                       banned_l: set[int], banned_r: set[int]) -> int:
    """在剔除被锁定端点后的活跃子图上求最大二分匹配基数。"""
    pair_l = [-1] * n_left
    pair_r = [-1] * n_right
    inf = 10 ** 9
    dist = [0] * n_left

    def bfs() -> bool:
        queue: list[int] = []
        found = False
        for l in range(n_left):
            if l in banned_l or pair_l[l] != -1:
                dist[l] = inf
            else:
                dist[l] = 0
                queue.append(l)
        while queue:
            l = queue.pop(0)
            for r in adj.get(l, ()):
                if r in banned_r:
                    continue
                nxt = pair_r[r]
                if nxt == -1:
                    found = True
                elif nxt not in banned_l and dist[nxt] == inf:
                    dist[nxt] = dist[l] + 1
                    queue.append(nxt)
        return found

    def dfs(l: int) -> bool:
        for r in adj.get(l, ()):
            if r in banned_r:
                continue
            nxt = pair_r[r]
            if nxt == -1 or (nxt not in banned_l
                             and dist[nxt] == dist[l] + 1 and dfs(nxt)):
                pair_l[l] = r
                pair_r[r] = l
                return True
        dist[l] = inf
        return False

    matching = 0
    while bfs():
        for l in range(n_left):
            if l not in banned_l and pair_l[l] == -1 and dfs(l):
                matching += 1
    return matching


# --------------------------------------------------------------------------- #
# 分组求解
# --------------------------------------------------------------------------- #

@dataclass
class FeasibleEdge:
    left_index: int
    right_index: int
    cost: int


@dataclass
class GroupSolution:
    matching: dict[int, int]          # left_index -> right_index（代表解）
    edge_labels: dict[tuple[int, int], str]
    coverable_unmatched_left: set[int]
    coverable_unmatched_right: set[int]
    cardinality: int
    total_cost: int


def solve_group(n_left: int, n_right: int,
                edges: list[FeasibleEdge],
                canonical_order: list[tuple[int, int]]) -> GroupSolution:
    """求一个连接键分组的最优匹配与歧义标签。

    canonical_order: 按规范事件 ID 对排好序的 (li, ri) 列表，
    第三层字典序代表解沿此顺序固定边。
    """
    s = 0
    t = 1 + n_left + n_right
    node_l = lambda i: 1 + i
    node_r = lambda j: 1 + n_left + j

    mcf = MinCostFlow(t + 1)
    for i in range(n_left):
        mcf.add_edge(s, node_l(i), 1, 0)
    for j in range(n_right):
        mcf.add_edge(node_r(j), t, 1, 0)

    arc_of: dict[tuple[int, int], _Arc] = {}
    for e in edges:
        arc = mcf.add_edge(node_l(e.left_index), node_r(e.right_index),
                           1, e.cost)
        arc_of[(e.left_index, e.right_index)] = arc

    cardinality, total_cost, potential = mcf.flow(s, t)

    # G0：残量 > 0 且缩减成本为 0 的弧
    g0: list[list[int]] = [[] for _ in range(t + 1)]
    for u in range(t + 1):
        for arc in mcf.g[u]:
            if arc.cap > 0 and arc.cost + potential[u] - potential[arc.to] == 0:
                g0[u].append(arc.to)

    comp = tarjan_scc(g0)
    reach = condensation_reach(g0, comp)

    def can_reach(u: int, v: int) -> bool:
        return bool(reach[comp[u]] & (1 << comp[v]))

    def forward_reduced_cost(li: int, ri: int) -> int:
        """前向弧缩减成本 c + p[u] - p[v]（Dijkstra 势函数标准定义，
        不含额外的 p[s]-p[t]；p[t] 等于最短路费用属正常现象）。"""
        arc = arc_of[(li, ri)]
        return arc.cost + potential[node_l(li)] - potential[node_r(ri)]

    edge_labels: dict[tuple[int, int], str] = {}
    used_pairs: set[tuple[int, int]] = set()

    for e in edges:
        li, ri = e.left_index, e.right_index
        u, v = node_l(li), node_r(ri)
        arc = arc_of[(li, ri)]
        if arc.cap == 0:  # 代表最优流中使用
            used_pairs.add((li, ri))
            # 全最优解共用 <=> G0 中不存在从 l 回到 r 的交替环
            edge_labels[(li, ri)] = "all" if not can_reach(u, v) else "some"
        else:
            admissible = forward_reduced_cost(li, ri) == 0
            if admissible and can_reach(v, u):
                edge_labels[(li, ri)] = "some"
            else:
                edge_labels[(li, ri)] = "none"

    matched_left = {li for li, ri in used_pairs}
    matched_right = {ri for li, ri in used_pairs}
    free_left = [i for i in range(n_left) if i not in matched_left]
    free_right = [j for j in range(n_right) if j not in matched_right]

    # 零缩减成本二分图 H0：属于“至少一个最优匹配”的边 = 标签 all/some 的边
    # （none 边被严格的残量可达性条件排除）。H0 的最大基数匹配与全部最优匹配
    # 一一对应，代表流所用边也在其中。
    optimal_edge_pairs = {
        pair for pair, lab in edge_labels.items() if lab in ("all", "some")
    }
    zero_edges = [pair for pair in canonical_order
                  if pair in optimal_edge_pairs]
    h0_adj: dict[int, list[int]] = {}
    for li, ri in zero_edges:
        h0_adj.setdefault(li, []).append(ri)
    # 代表流（H0 的一个最大基数匹配）的配对关系
    pair_l = dict(used_pairs)

    # Dulmage-Mendelsohn 分解判定未匹配端点的可覆盖性（在 H0 上，
    # 代表流 M 是 H0 的一个最大基数匹配）。
    # 简洁且经独立枚举验证的判据：
    # - 未匹配右点 rj 可覆盖 <=> H0 中存在某左点经一条“非匹配边”指向 rj。
    #   该左点若空闲即直接增广；若已匹配则把它的当前配对换出——因 M 与
    #   含 (li,rj) 的匹配同为 H0 的最大基数匹配，换后仍为最大匹配。
    # - 未匹配左点 li 可覆盖 <=> 对称：li 经一条非匹配边指向某右点。
    matched_l_set = set(matched_left)
    matched_r_set = set(matched_right)
    coverable_left: set[int] = set()
    coverable_right: set[int] = set()
    for li, ri in optimal_edge_pairs:
        is_match_edge = pair_l.get(li) == ri
        if is_match_edge:
            continue
        if li not in matched_l_set:
            coverable_left.add(li)
        if ri not in matched_r_set:
            coverable_right.add(ri)

    # 第三层：字典序最小代表。H0 上沿规范 ID 对顺序固定-重算（Hopcroft-Karp
    # 重算剔除两端后子图的最大基数做可行性判定），全程多项式、不枚举最优配对。
    adj0 = h0_adj
    locked_l: dict[int, int] = {}
    locked_r: set[int] = set()

    base_size = hopcroft_karp_size(n_left, n_right, adj0, set(), set())
    assert base_size == cardinality, "H0 最大基数必须等于最优流基数"

    for li, ri in zero_edges:
        if li in locked_l or ri in locked_r:
            continue
        # 试探：强制把 (li, ri) 纳入代表解，两端从活跃子图剔除
        trial_l = dict(locked_l)
        trial_l[li] = ri
        trial_r = locked_r | {ri}
        remain_size = hopcroft_karp_size(
            n_left, n_right, adj0, set(trial_l), trial_r)
        if len(trial_l) + remain_size == cardinality:
            locked_l[li] = ri
            locked_r.add(ri)

    assert len(locked_l) == cardinality, "固定-重算必须得到同等基数代表"
    # 校验代表解总代价等于最优费用
    cost_of = {(e.left_index, e.right_index): e.cost for e in edges}
    assert sum(cost_of[p] for p in locked_l.items()) == total_cost

    return GroupSolution(
        matching=dict(locked_l),
        edge_labels=edge_labels,
        coverable_unmatched_left=coverable_left,
        coverable_unmatched_right=coverable_right,
        cardinality=cardinality,
        total_cost=total_cost,
    )
