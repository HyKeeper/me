"""export.py 测试：十层归类、覆盖度、空洞检测、语言指纹。"""

from __future__ import annotations

import unittest
from datetime import date

from helpers import Lib, doc, entry  # noqa: E402

import export  # noqa: E402


class TestLayerOf(unittest.TestCase):
    def setUp(self):
        # 本人目录名来自私有配置 _config.md，测试必须自带一份，
        # 否则既依赖真实配置、也把真实姓名钉进了代码。
        self._orig = export.SELF_DIR
        export.SELF_DIR = "甲"
        self.addCleanup(lambda: setattr(export, "SELF_DIR", self._orig))

    def test_self_attributes_are_identity(self):
        self.assertEqual(export.layer_of("people/甲/name.md", "name-001", ""), 1)

    def test_other_person_is_network(self):
        self.assertEqual(export.layer_of("people/乙/occupation.md", "spousejob-001", ""), 5)

    def test_employer_and_role_are_identity(self):
        self.assertEqual(export.layer_of("work/employer.md", "emp-001", ""), 1)
        self.assertEqual(export.layer_of("work/role.md", "role-001", ""), 1)

    def test_compensation_is_resource(self):
        self.assertEqual(export.layer_of("work/salary.md", "salary-001", ""), 4)

    def test_preferences_is_decision(self):
        self.assertEqual(export.layer_of("preferences/career.md", "pref-001", "怎么选工作"), 2)

    def test_redline_is_layer3(self):
        self.assertEqual(export.layer_of("preferences/红线.md", "red-001", "绝对不行"), 3)

    def test_projects_is_goal(self):
        self.assertEqual(export.layer_of("projects/blog.md", "proj-001", ""), 7)

    def test_unknown_path_falls_to_facts(self):
        self.assertEqual(export.layer_of("somewhere/else.md", "x-001", ""), 10)


class TestGaps(unittest.TestCase):
    def _gaps(self, files):
        export.SELF_DIR = "甲"
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(export)
        items = export.parse_entries()
        return export.detect_gaps(items, date(2026, 10, 23))

    def test_empty_layers_reported(self):
        gaps = self._gaps({"people/甲/name.md": doc("姓名", entry("name-001", body="甲。"))})
        text = " ".join(gaps)
        self.assertIn("决策函数", text)
        self.assertIn("红线", text)

    def test_unknown_valid_from_reported(self):
        gaps = self._gaps({"work/x.md": doc("X", entry("x-001", vf="unknown"))})
        self.assertTrue(any("unknown" in g for g in gaps))

    def test_no_gap_on_filled_layers(self):
        gaps = self._gaps({"people/甲/name.md": doc("姓名", entry("name-001", body="甲。"))})
        self.assertNotIn("第 1 层", " ".join(gaps))


class TestVoiceFingerprint(unittest.TestCase):
    def test_extracts_from_evidence(self):
        files = {"a/x.md": doc("X", entry("x-001", evidence='"我不用句号 就这样说"'))}
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(export)
        stats, obs = export.voice_fingerprint(export.parse_entries())
        self.assertEqual(stats["n"], 1)
        self.assertGreater(stats["chars"], 0)

    def test_no_period_detected(self):
        files = {"a/x.md": doc("X",
                               entry("x-001", evidence='"第一句 第二句 都没有句号"'),
                               entry("x-002", evidence='"第三句 也没有"'),
                               entry("x-003", evidence='"第四句"'))}
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(export)
        stats, obs = export.voice_fingerprint(export.parse_entries())
        self.assertEqual(stats["period"], 0)
        self.assertTrue(any("句号" in o for o in obs))

    def test_empty_evidence_no_crash(self):
        files = {"a/x.md": doc("X", entry("x-001", evidence=None))}
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(export)
        stats, obs = export.voice_fingerprint(export.parse_entries())
        self.assertEqual(stats["n"], 0)


class TestParseEntries(unittest.TestCase):
    def test_history_not_included_in_current(self):
        files = {"work/x.md": doc("X", entry("x-002"),
                                  history=(entry("x-001", status="superseded", body="旧值。"),))}
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(export)
        items = export.parse_entries()
        self.assertEqual([i["id"] for i in items], ["x-002"])

    def test_notes_kept(self):
        files = {"a/x.md": doc("X", entry("x-001", evidence='"原话"'))}
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(export)
        items = export.parse_entries()
        self.assertTrue(any(n.startswith("evidence:") for n in items[0]["notes"]))


if __name__ == "__main__":
    unittest.main()
