"""memconfig / init 测试：配置解析、默认值回落、初始化幂等。"""

from __future__ import annotations

import subprocess
import sys
import unittest

from helpers import PROJECT, Lib  # noqa: E402

import memconfig  # noqa: E402


class TestConfigParse(unittest.TestCase):
    def test_table_parsed(self):
        cfg = memconfig._parse_table("| 键 | 值 | 说明 |\n|---|---|---|\n| user_name | 张三 | 名字 |\n")
        self.assertEqual(cfg["user_name"], "张三")

    def test_header_row_skipped(self):
        cfg = memconfig._parse_table("| 键 | 值 |\n|---|---|\n")
        self.assertNotIn("键", cfg)

    def test_separator_row_skipped(self):
        cfg = memconfig._parse_table("|---|---|\n")
        self.assertEqual(cfg, {})

    def test_defaults_present(self):
        lib = Lib({})  # 没有任何配置文件
        self.addCleanup(lib.cleanup)
        lib.bind(memconfig)
        cfg = memconfig.load()
        self.assertEqual(cfg["user_name"], "本人")
        self.assertEqual(cfg["payroll_enabled"], "false")
        self.assertEqual(cfg["semantic_threshold"], "0.30")

    def test_bool_and_float(self):
        self.assertTrue(memconfig.get_bool({"x": "true"}, "x"))
        self.assertTrue(memconfig.get_bool({"x": "YES"}, "x"))
        self.assertFalse(memconfig.get_bool({"x": "false"}, "x"))
        self.assertFalse(memconfig.get_bool({}, "missing"))
        self.assertAlmostEqual(memconfig.get_float({"t": "0.42"}, "t"), 0.42)
        self.assertEqual(memconfig.get_float({"t": "bad"}, "t"), 0.0)


class TestSelfDirDetect(unittest.TestCase):
    def test_single_dir_detected(self):
        lib = Lib({"people/李四/name.md": "x"})
        self.addCleanup(lib.cleanup)
        lib.bind(memconfig)
        self.assertEqual(memconfig.detect_self_dir(), "李四")

    def test_no_dirs_fallback(self):
        lib = Lib({})
        self.addCleanup(lib.cleanup)
        lib.bind(memconfig)
        self.assertEqual(memconfig.detect_self_dir(), "本人")

    def test_config_overrides_detection(self):
        lib = Lib({
            "people/甲/name.md": "x",
            "people/乙/name.md": "x",
            "_config.md": "| 键 | 值 |\n|---|---|\n| self_dir | 乙 |\n",
        })
        self.addCleanup(lib.cleanup)
        lib.bind(memconfig)
        self.assertEqual(memconfig.load()["self_dir"], "乙")


class TestInit(unittest.TestCase):
    def _run(self, root, *args):
        return subprocess.run(
            [sys.executable, str(PROJECT / "scripts" / "init.py"), "--root", str(root), *args],
            capture_output=True, text=True,
        )

    def test_python_version_gate_blocks_old_interpreter(self):
        """环境门槛只拦初始化。把 MIN_PY 调高模拟旧解释器，不依赖本机真实版本。"""
        import init

        orig = init.MIN_PY
        try:
            init.MIN_PY = (99, 0)
            with self.assertRaises(SystemExit) as cm:
                init.main()
            # sys.exit("文本") 会把文本作为 code，不是数字
            self.assertIn("需要 Python 99.0", str(cm.exception.code))
        finally:
            init.MIN_PY = orig

    def test_current_python_meets_declared_floor(self):
        """README 与 pyproject 声称 >= 3.9，跑测试的解释器必须真的满足。"""
        import init

        self.assertGreaterEqual(
            tuple(sys.version_info[:2]), init.MIN_PY,
            "当前 Python 低于声明的下限，README 与 pyproject.toml 需同步修正",
        )
    def test_creates_skeleton(self):
        lib = Lib({})
        self.addCleanup(lib.cleanup)
        r = self._run(lib.tmp, "--name", "王五")
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in ("memory/_config.md", "memory/people/_index.md", "memory/timeline/events.md"):
            self.assertTrue((lib.tmp / rel).exists(), rel)
        self.assertTrue((lib.tmp / "memory" / "people" / "王五").is_dir())

    def test_idempotent_and_no_overwrite(self):
        lib = Lib({})
        self.addCleanup(lib.cleanup)
        self._run(lib.tmp, "--name", "王五")
        cfg = lib.tmp / "memory" / "_config.md"
        cfg.write_text("| 键 | 值 |\n|---|---|\n| user_name | 已改过 |\n", encoding="utf-8")
        self._run(lib.tmp, "--name", "王五")
        self.assertIn("已改过", cfg.read_text(encoding="utf-8"))

    def test_name_goes_into_config(self):
        lib = Lib({})
        self.addCleanup(lib.cleanup)
        self._run(lib.tmp, "--name", "赵六")
        text = (lib.tmp / "memory" / "_config.md").read_text(encoding="utf-8")
        self.assertIn("赵六", text)


if __name__ == "__main__":
    unittest.main()
