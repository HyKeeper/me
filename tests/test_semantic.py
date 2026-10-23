"""semantic.py 测试：切词、同义词归一、检索排序、候选对生成。"""

from __future__ import annotations

import unittest

from helpers import Lib, doc, entry  # noqa: E402

import semantic  # noqa: E402


class TestTokenize(unittest.TestCase):
    def setUp(self):
        # 隔离真实库的同义词表，否则「月薪」会被归一成「§薪资」
        self._saved = semantic._SYN
        semantic._SYN = {}

    def tearDown(self):
        semantic._SYN = self._saved

    def test_chinese_bigram(self):
        toks = semantic.tokenize("月薪四万")
        self.assertIn("月薪", toks)
        self.assertIn("四万", toks)

    def test_english_and_number_kept_whole(self):
        toks = semantic.tokenize("用 Milvus 做 30000 的检索")
        self.assertIn("milvus", toks)
        self.assertIn("30000", toks)

    def test_no_bigram_across_punctuation(self):
        """标点必须切断，否则会造出「天在」这种假词。"""
        toks = semantic.tokenize("今天，在地铁")
        self.assertIn("今天", toks)
        self.assertNotIn("天在", toks)

    def test_synonym_folds_variants(self):
        lib = Lib({"_synonyms.md": "| 概念 | 同义词 |\n|---|---|\n| 社保 | 五险一金 / 医保 / 社保 |\n"})
        self.addCleanup(lib.cleanup)
        lib.bind(semantic)
        semantic.Index([])  # 触发同义词加载
        self.assertIn("§社保", semantic.tokenize("医保扣多少"))
        self.assertIn("§社保", semantic.tokenize("五险一金怎么样"))


class TestIndex(unittest.TestCase):
    def _lib(self):
        files = {
            "_synonyms.md": "| 概念 | 同义词 |\n|---|---|\n| 社保 | 五险一金 / 医保 |\n| 薪资 | 月薪 / 工资 |\n",
            "work/salary.md": doc("月薪", entry("salary-001", body="月薪 30,000 元人民币，每月税前。")),
            "work/insurance.md": doc("社保", entry("insur-001", body="五险一金齐全，都是满额缴纳。")),
        }
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(semantic)
        return lib

    def test_query_ranks_relevant_first(self):
        self._lib()
        idx = semantic.Index(semantic.parse_docs())
        res = idx.query("医保要扣多少钱", k=2)
        self.assertEqual(res[0][1]["id"], "insur-001")

    def test_query_salary(self):
        self._lib()
        idx = semantic.Index(semantic.parse_docs())
        res = idx.query("现在工资多少", k=2)
        self.assertEqual(res[0][1]["id"], "salary-001")

    def test_pairs_skip_same_file(self):
        self._lib()
        idx = semantic.Index(semantic.parse_docs())
        for _sim, a, b in idx.pairs(0.0):
            self.assertNotEqual(a["path"], b["path"])

    def test_empty_corpus_does_not_crash(self):
        lib = Lib({})
        self.addCleanup(lib.cleanup)
        lib.bind(semantic)
        idx = semantic.Index([])
        self.assertEqual(idx.query("任何问题"), [])
        self.assertEqual(idx.pairs(0.1), [])

    def test_history_entries_excluded(self):
        """history 是存档，不应参与当前相似度比较。"""
        files = {
            "work/salary.md": doc("月薪", entry("salary-002", body="现在 30000。"),
                                  history=(entry("salary-001", vf="2020-01-01", vu="2022-01-01", status="superseded", body="以前 20000。"),)),
        }
        lib = Lib(files)
        self.addCleanup(lib.cleanup)
        lib.bind(semantic)
        docs = semantic.parse_docs()
        self.assertEqual([d["id"] for d in docs], ["salary-002"])


if __name__ == "__main__":
    unittest.main()
