"""术语同一性 / 证据忠实性 / 团体奖项 三条规则的测试。

存在理由：
    断言句里被写入了原话中没有的技术名词——
    例如原话只有某个泛指的赛题名，却被补成具体的技术栈，
    并据此推翻了已经校准过的裁决。

    事后写了四篇 lesson，错误照样会发生——因为 lesson 是文字，不是机制。
    这个文件的作用是：把那次错误**变成一条会永久运行的断言**。

    每条规则都必须有「能抓到」+「不误报」两个方向，
    否则规则要么是装饰品，要么是噪音源。
"""

from __future__ import annotations

import unittest

from helpers import Lib, doc, entry  # noqa: E402

import check  # noqa: E402


AMBIGUOUS_MD = """# 歧义术语表

| 词 | 常见义项 | 判别依据 |
|---|---|---|
| **调度** | ① OS ② K8s Pod ③ 分时调度 | 对象是什么？空间还是时间？ |
| **平台** | ① 技术平台 ② 组织 | 管什么？ |
"""


def levels(results):
    return [r[0] for r in results]


def messages(results):
    return " ".join(r[2] for r in results)


class TestEvidenceFidelity(unittest.TestCase):
    """断言句里的技术名词，必须是 evidence 原文里有的。"""

    def run_rule(self, body, evidence, files=None):
        f = {"work/x.md": doc("测试", entry("x-001", body=body, evidence=evidence))}
        f.update(files or {})
        lib = Lib(f)
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        return check.check_evidence_fidelity(items)

    def test_catches_the_real_mistake_from_2026_10_23(self):
        """原话只有一个泛指词，正文却补上了具体技术栈 → 应报警。"""
        r = self.run_rule(
            body="这道题的题目直指 K8s 调度器改造，可作为其调度能力的证据。",
            evidence='"题目：某调度赛题"',
        )
        self.assertIn("WARN", levels(r))
        self.assertIn("K8s", messages(r))

    def test_no_warn_when_term_present_in_evidence(self):
        """技术名词本来就在原话里 → 不该报警。"""
        r = self.run_rule(
            body="这条足以说明其具备 Sidecar 优化能力。",
            evidence='"针对 Sidecar 模式下的服务网格数据面 QPS 和延时优化"',
        )
        self.assertNotIn("WARN", levels(r))

    def test_no_warn_without_inference_marker(self):
        """纯描述、无断言动词 → 不报警（外部补全允许存在，不能一刀切）。"""
        r = self.run_rule(
            body="这道题与 K8s 调度无关。",
            evidence='"题目：某调度赛题"',
        )
        self.assertNotIn("WARN", levels(r))

    def test_no_warn_when_no_evidence_at_all(self):
        """没有 evidence 行的条目由 check_content 负责，本规则不重复报。"""
        r = self.run_rule(body="题目直指 K8s。", evidence=None)
        self.assertNotIn("WARN", levels(r))


class TestTermHomonym(unittest.TestCase):
    """歧义词出现在断言句里，必须显式标注义项。"""

    def run_rule(self, body, extra="", files=None):
        f = {
            "work/x.md": doc("测试", entry("x-001", body=body, extra=extra)),
            "_ambiguous-terms.md": AMBIGUOUS_MD,
        }
        f.update(files or {})
        lib = Lib(f)
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        return check.check_term_homonym(items)

    def test_catches_ambiguous_term_in_assertion(self):
        r = self.run_rule(body="这道题直指调度能力，是硬证据。")
        self.assertIn("WARN", levels(r))
        self.assertIn("调度", messages(r))

    def test_no_warn_when_term_annotated(self):
        """标了 [term: ...] 就放行。"""
        r = self.run_rule(body="这道题直指调度能力。", extra="[term: 时间维度的资源分配]")
        self.assertNotIn("WARN", levels(r))

    def test_no_warn_without_inference_marker(self):
        r = self.run_rule(body="题目叫某分时调度，我参加过。")
        self.assertNotIn("WARN", levels(r))

    def test_no_terms_file_no_crash(self):
        """库里没有 _ambiguous-terms.md 时应当安静返回，不崩。"""
        lib = Lib({"work/x.md": doc("测试", entry("x-001", body="直指调度能力。"))})
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        self.assertEqual(check.check_term_homonym(items), [])


class TestAwardTeam(unittest.TestCase):
    """奖项必须标明团队赛还是个人赛。"""

    def run_rule(self, body):
        lib = Lib({"work/x.md": doc("测试", entry("x-001", body=body))})
        self.addCleanup(lib.cleanup)
        lib.bind(check)
        items, _ = check.parse_all()
        return check.check_award_team(items)

    def test_catches_award_without_team_flag(self):
        r = self.run_rule(body="某编程挑战赛获得季军。")
        self.assertIn("WARN", levels(r))

    def test_no_warn_when_team_mentioned(self):
        r = self.run_rule(body="某编程挑战赛季军（组队赛，1-3 人）。")
        self.assertNotIn("WARN", levels(r))

    def test_no_warn_for_non_award_content(self):
        r = self.run_rule(body="月薪 30,000 元，税前。")
        self.assertNotIn("WARN", levels(r))


if __name__ == "__main__":
    unittest.main()
