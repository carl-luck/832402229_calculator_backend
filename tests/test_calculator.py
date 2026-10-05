"""计算核心单元测试（只依赖标准库 unittest）。

运行：
    python tests/test_calculator.py
    pytest -q                       # 若已安装 pytest
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calculator import CalculationError, evaluate  # noqa: E402


class CalculatorTestCase(unittest.TestCase):
    def assertEval(self, expression, expected):
        self.assertAlmostEqual(evaluate(expression), expected, places=9, msg=expression)

    def assertRejected(self, expression):
        with self.assertRaises(CalculationError, msg=f"{expression!r} 应该被拒绝"):
            evaluate(expression)

    # 四则运算
    def test_basic(self):
        self.assertEval("12+8", 20)
        self.assertEval("12-8", 4)
        self.assertEval("12*8", 96)
        self.assertEval("12/8", 1.5)

    # 优先级与括号
    def test_precedence_and_parentheses(self):
        self.assertEval("1+2*3", 7)
        self.assertEval("(1+2)*3", 9)
        self.assertEval("10/2+7", 12)
        self.assertEval("8-3*2", 2)
        self.assertEval("1-2-3", -4)

    # 一元正负号与小数
    def test_unary_and_decimal(self):
        self.assertEval("-5+8", 3)
        self.assertEval("3*-2", -6)
        self.assertEval("1.5+2.25", 3.75)
        self.assertEval("0.1+0.2", 0.3)

    # 异常：除零 / 语法错误 / 括号不匹配 / 空表达式
    def test_errors(self):
        for expression in ["1/0", "10/(5-5)", "1+", "*3", "(1+2", "1+2)", "", "   ", "abc(3)"]:
            self.assertRejected(expression)


if __name__ == "__main__":
    unittest.main(verbosity=2)
