"""会话日志配对解决方案（仅标准库）。

模块划分：
- model:      数据类与统一时刻区间的区间数学
- validation: 输入结构校验与错误码
- matching:   最小费用最大流、零缩减成本残量子图、SCC 可达性、
              Dulmage-Mendelsohn 字典序最小代表匹配
- pipeline:   单例/整份文档的装配与求解
"""

__all__ = ["model", "validation", "matching", "pipeline"]
