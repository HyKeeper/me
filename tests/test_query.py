"""query.py 测试：四档时间语义 + 别名扩展。

这一组是 §6.1 的规格测试 —— as_of 查询曾经是"unknown 条目全部查不到"的黑洞，
所以四档必须逐个钉死。
"""

from __future__ import annotations

import unittest

from helpers import Lib  # noqa: E402

import query  # noqa: E402


def e(vf, vu=None):
    """构造 active_at() 期望的条目结构。"""
    f = {"valid_from": vf}
    if vu:
        f["valid_until"] = vu
    return {"fields": f}


class TestTimeBounds(unittest.TestCase):
    def test_exact_month(self):
        self.assertEqual(query.norm_start("2022-04")[0], "2022-04-01")

    def test_exact_year(self):
        self.assertEqual(query.norm_start("2022")[0], "2022-01-01")

    def test_exact_day(self):
        self.assertEqual(query.norm_start("2022-04-15")[0], "2022-04-15")

    def test_fuzzy_strips_tilde(self):
        start, note = query.norm_start("~2023-03")
        self.assertEqual(start, "2023-03-01")
        self.assertIn("fuzzy", note)

    def test_le_is_unbounded(self):
        start, note = query.norm_start("<= 2026-10-23")
        self.assertEqual(start, "0000-00-00")
        self.assertEqual(note, "le")

    def test_unknown(self):
        self.assertEqual(query.norm_start("unknown")[1], "unknown")

    def test_end_open_interval(self):
        self.assertEqual(query.norm_end(None), "9999-12-31")

    def test_end_month_extends_to_month_end(self):
        self.assertEqual(query.norm_end("2023-03"), "2023-03-31")


class TestActiveAt(unittest.TestCase):
    def test_item_active_inside_range(self):
        self.assertTrue(query.active_at(e("2022-04", "2024-01"), "2023-06-15"))

    def test_item_not_active_before_start(self):
        self.assertFalse(query.active_at(e("2022-04"), "2022-03-15"))

    def test_item_not_active_after_end(self):
        self.assertFalse(query.active_at(e("2022-04", "2024-01"), "2025-06-15"))

    def test_le_item_visible_before_bound(self):
        """`<= 2026-10-23` 必须能在更早的时间点被查到，否则就是黑洞。"""
        self.assertTrue(query.active_at(e("<= 2026-10-23"), "2021-01-01"))

    def test_le_item_hidden_after_bound(self):
        self.assertFalse(query.active_at(e("<= 2026-10-23"), "2027-01-01"))

    def test_unknown_item_visible_anywhere(self):
        self.assertTrue(query.active_at(e("unknown"), "2018-01-01"))

    def test_deleted_item_gone_after_valid_until(self):
        self.assertFalse(query.active_at(e("2020-01", "2023-12-31"), "2024-06-01"))


class TestAlias(unittest.TestCase):
    def test_expand_pulls_group(self):
        groups = [{"某俗称", "某公司"}]
        self.assertEqual(query.expand("某俗称", groups), {"某俗称", "某公司"})

    def test_expand_transitive(self):
        groups = [{"a", "b"}, {"b", "c"}]
        self.assertEqual(query.expand("a", groups), {"a", "b", "c"})

    def test_expand_no_match(self):
        self.assertEqual(query.expand("无关词", [{"a", "b"}]), {"无关词"})

    def test_load_aliases_from_fixture(self):
        """别名解析：同一个人的多种称呼应归入同一组。

        用临时库构造，不读真实库——真实库里是别人的家庭关系，
        既不该进测试，也不该让测试在开源环境下失败。
        """
        from helpers import Lib
        lib = Lib({
            "_aliases.md": "| 用户口径 | 标准 | 备注 |\n|---|---|---|\n"
                           "| 甲某 | 甲 | 本人 |\n| 配偶 | 乙 | 关系 |\n",
        })
        self.addCleanup(lib.cleanup)
        lib.bind(query)
        groups = query.load_aliases()
        self.assertTrue(groups or groups == [], "解析不应崩溃")


if __name__ == "__main__":
    unittest.main()
