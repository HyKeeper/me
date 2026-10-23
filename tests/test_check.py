"""check.py 规则测试：每条规则都要有「能抓到」+「不误报」两个方向。"""

from __future__ import annotations

import unittest

from helpers import Lib, doc, entry  # noqa: E402  (helpers 负责把 scripts/ 加进 sys.path)

import check  # noqa: E402


def levels(results):
    return [r[0] for r in results]


def messages(results):
    return [r[2] for r in results]


class TestStructure(unittest.TestCase):
    def run_structure(self, files):
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        return check.check_structure(items)

    def test_two_actives_in_current_is_error(self):
        r = self.run_structure({"work/salary.md": doc("月薪", entry("salary-001"), entry("salary-002"))})
        self.assertIn("ERROR", levels(r))
        self.assertTrue(any("current 区有 2 条" in m for m in messages(r)))

    def test_missing_time_field_is_error(self):
        bad = "- [id: x-001] [spoken_at: 2026-01-01T00:00:00+08:00] [valid_from: 2026-01-01]\n  内容\n  > evidence: \"x\""
        r = self.run_structure({"a/x.md": doc("X", bad)})
        self.assertTrue(any("recorded_at" in m for m in messages(r)))

    def test_missing_evidence_is_error(self):
        r = self.run_structure({"a/x.md": doc("X", entry("x-001", evidence=None))})
        self.assertTrue(any("evidence" in m for m in messages(r)))

    def test_duplicate_id_is_error(self):
        r = self.run_structure({
            "a/x.md": doc("X", entry("dup-001")),
            "b/y.md": doc("Y", entry("dup-001")),
        })
        self.assertTrue(any("id 重复" in m for m in messages(r)))

    def test_valid_from_after_valid_until_is_error(self):
        r = self.run_structure({"a/x.md": doc("X", entry("x-001", vf="2026-05-01", vu="2026-01-01"))})
        self.assertTrue(any("晚于 valid_until" in m for m in messages(r)))

    def test_bad_time_format_is_error(self):
        r = self.run_structure({"a/x.md": doc("X", entry("x-001", vf="去年"))})
        self.assertTrue(any("四档语法" in m for m in messages(r)))

    def test_bad_iso_timestamp_is_error(self):
        r = self.run_structure({"a/x.md": doc("X", entry("x-001", spoken="2026-01-01 00:00"))})
        self.assertTrue(any("ISO 时间戳" in m for m in messages(r)))

    def test_clean_lib_has_no_error(self):
        """防误报：完全合规的库必须零错误。"""
        r = self.run_structure({"work/salary.md": doc("月薪", entry("salary-001"))})
        self.assertNotIn("ERROR", levels(r))

    def test_le_prefixed_time_is_accepted(self):
        """`<= 2026-10-23` 是 §3 四档之一，不能报错。"""
        r = self.run_structure({"work/x.md": doc("X", entry("x-001", vf="<= 2026-10-23"))})
        self.assertNotIn("ERROR", levels(r))

    def test_fuzzy_time_is_accepted(self):
        r = self.run_structure({"work/x.md": doc("X", entry("x-001", vf="~2023-03"))})
        self.assertNotIn("ERROR", levels(r))


class TestContent(unittest.TestCase):
    def run_content(self, files):
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        return check.check_content(items)

    def test_hardcoded_age_is_error(self):
        r = self.run_content({"people/a/birth.md": doc("出生", entry("birth-001", body="出生于 1990-01-01，现年 30 岁。"))})
        self.assertTrue(any("派生值" in m for m in messages(r)))

    def test_unknown_valid_from_is_warn(self):
        r = self.run_content({"work/x.md": doc("X", entry("x-001", vf="unknown"))})
        self.assertTrue(any("unknown" in m for m in messages(r)))

    def test_vague_word_is_warn(self):
        r = self.run_content({"work/x.md": doc("X", entry("x-001", body="待遇还不错，压力大。"))})
        self.assertTrue(any("定性词" in m for m in messages(r)))

    def test_vague_resolved_is_not_warned(self):
        r = self.run_content({"work/x.md": doc("X", entry("x-001", body="都是满额。", extra="[vague: resolved]"))})
        self.assertFalse(any("定性词" in m for m in messages(r)))

    def test_expired_param_is_error(self):
        e = entry("p-001", vf="2025-01-01", vu="2025-12-31", body="政策参数。")
        r = self.run_content({"misc/p.md": doc("参数", e)})
        self.assertTrue(any("过期" in m for m in messages(r)))

    def test_history_entry_not_checked_for_expiry(self):
        """history 是存档，过期不应报错。"""
        e = entry("p-000", vf="2024-01-01", vu="2024-12-31", status="superseded", body="旧参数。")
        r = self.run_content({"misc/p.md": doc("参数", entry("p-001"), history=(e,))})
        self.assertFalse(any("过期" in m for m in messages(r)))


class TestTimeline(unittest.TestCase):
    def run_timeline(self, content):
        lib = Lib({"timeline/events.md": content})
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        return check.check_timeline([])

    def test_broken_format_is_error(self):
        r = self.run_timeline("# 事件时间线\n\n- - 2026-01-01  [x-001] spoken：坏行\n")
        self.assertTrue(any("格式非法" in m for m in messages(r)))

    def test_out_of_order_is_error(self):
        r = self.run_timeline("# 事件时间线\n\n- 2026-05-01  [a-001] spoken：后\n- 2026-01-01  [b-001] spoken：前\n")
        self.assertTrue(any("乱序" in m for m in messages(r)))

    def test_ordered_timeline_ok(self):
        r = self.run_timeline("# 事件时间线\n\n- 2026-01-01  [a-001] spoken：前\n- 2026-05-01  [b-001] spoken：后\n")
        self.assertNotIn("ERROR", levels(r))


class TestDomainRules(unittest.TestCase):
    def _lib(self):
        files = {
            "work/salary.md": doc("月薪", entry("salary-001", body="月薪 40,000 元人民币。")),
            "work/housing-fund.md": doc("公积金", entry("hf-001", body="**住房公积金月缴存额 8,724 元/月（个人 + 单位合计）**")),
            "misc/params.md": doc("参数", entry("bjparam-001", body="2026 年度：月缴存基数上限 **36,348 元**")),
        }
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        return lib

    def _cfg(self, enabled=True):
        return {"payroll_enabled": "true" if enabled else "false",
                "payroll_salary_id": "salary-001", "payroll_fund_id": "hf-001",
                "payroll_param_id": "bjparam-001", "birth_id_keyword": "birth"}

    def test_payroll_reconciles(self):
        self._lib()
        check.CFG = self._cfg()
        items, _ = check.parse_all()
        r = check.check_payroll(items)
        self.assertTrue(any("互洽通过" in m for m in messages(r)))

    def test_payroll_mismatch_is_error(self):
        lib = Lib({
            "work/salary.md": doc("月薪", entry("salary-001", body="月薪 20,000 元。")),
            "work/housing-fund.md": doc("公积金", entry("hf-001", body="月缴存额 8,724 元/月")),
            "misc/params.md": doc("参数", entry("bjparam-001", body="基数上限 **36,348 元**")),
        })
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        check.CFG = self._cfg()
        items, _ = check.parse_all()
        r = check.check_payroll(items)
        self.assertTrue(any("不自洽" in m for m in messages(r)))

    def test_payroll_disabled_skips(self):
        self._lib()
        check.CFG = self._cfg(enabled=False)
        items, _ = check.parse_all()
        self.assertEqual(check.check_payroll(items), [])


class TestExternalGaps(unittest.TestCase):
    """§3.3 的自动检测：该自己查的东西，不许用「未说明」糊过去。"""

    def _run(self, files, rule):
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        return rule(items)

    def test_public_gap_warns_on_unchecked_office(self):
        files = {"work/employer.md": doc("雇主", entry("emp-001", body="在某公司上班。具体办公地点未说明。"))}
        r = self._run(files, check.check_public_gap)
        self.assertTrue(any("可查属性" in m for _, _, m in r))

    def test_public_gap_skips_private_detail(self):
        """私人信息（落户细节）不是"可查"，不该报。"""
        files = {"people/x/hukou.md": doc("户籍", entry("hk-001", body="持北京户口。随父还是随母落户未说明。"))}
        r = self._run(files, check.check_public_gap)
        self.assertFalse(any("可查属性" in m for _, _, m in r))

    def test_location_pair_warns_without_geo(self):
        files = {
            "work/employer.md": doc("雇主", entry("emp-001", body="在某公司上班。")),
            "people/我/location.md": doc("常驻", entry("loc-001", body="在北京工作。")),
        }
        r = self._run(files, check.check_location_pairs)
        self.assertTrue(any("通勤" in m for _, _, m in r))

    def test_location_pair_ok_when_geo_entry_exists(self):
        files = {
            "work/employer.md": doc("雇主", entry("emp-001", body="在某公司上班。")),
            "people/我/location.md": doc("常驻", entry("loc-001", body="在北京工作。")),
            "misc/北京地理参数.md": doc("地理参数", entry("geo-001", body="某远郊到市区单程 1.5 小时。")),
        }
        r = self._run(files, check.check_location_pairs)
        self.assertFalse(any("通勤" in m for _, _, m in r))

    def test_alias_group_with_no_record_warns(self):
        files = {
            "_aliases.md": "| 用户口径 | 标准 | 备注 |\n|---|---|---|\n| 字节跳动 | ByteDance | 测试 |\n",
            "work/employer.md": doc("雇主", entry("emp-001", body="在某公司上班。")),
        }
        r = self._run(files, check.check_entity_coverage)
        self.assertTrue(any("别名组" in m for _, _, m in r))

    def test_alias_variant_does_not_warn(self):
        """别名组里只要有一个叫法出现过就算覆盖。"""
        files = {
            "_aliases.md": "| 用户口径 | 标准 | 备注 |\n|---|---|---|\n| 某俗称 | 某公司 | 测试 |\n",
            "work/employer.md": doc("雇主", entry("emp-001", body="在某公司上班。")),
        }
        r = self._run(files, check.check_entity_coverage)
        self.assertFalse(any("别名组" in m for _, _, m in r))


class TestRealLibrary(unittest.TestCase):
    """对真实库跑一遍：必须零 ERROR（这是最重要的回归测试）。"""

    def test_real_library_is_clean(self):
        import importlib
        importlib.reload(check)
        items, _ = check.parse_all()
        results = []
        for fn in check.CHECKS:
            results.extend(fn(items))
        errors = [r for r in results if r[0] == "ERROR"]
        self.assertEqual(errors, [], f"真实库存在错误：{errors}")


if __name__ == "__main__":
    unittest.main()
