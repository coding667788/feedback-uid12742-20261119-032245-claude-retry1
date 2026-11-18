"""测试包：sys.path 引导，保证从项目根运行 unittest discover 时
既能导入被测 solution 包，也能导入同目录的独立枚举参考 ref_enum。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
