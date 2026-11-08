import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import sys

import guard


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.base = guard.load_json(guard.BASE / "baseline.json")
        self.good = guard.load_json(guard.BASE / "draft_good.json")

    def test_good(self):
        self.assertEqual(guard.differences(self.base, self.good), [])

    def test_bad_three_fields(self):
        bad = guard.load_json(guard.BASE / "draft_bad.json")
        self.assertEqual(len(guard.differences(self.base, bad)), 3)

    def test_missing_fixed_field(self):
        del self.good["固定信息"]["价格（元）"]
        self.assertIn("缺失", guard.differences(self.base, self.good)[0])

    def test_extra_fixed_field(self):
        self.good["固定信息"]["赠品"] = "一条视频"
        self.assertIn("额外增加", guard.differences(self.base, self.good)[0])

    def test_wrong_scalar_type(self):
        self.good["固定信息"]["修改轮数"] = "1"
        self.assertEqual(len(guard.differences(self.base, self.good)), 1)

    def test_boolean_rejected(self):
        self.good["固定信息"]["修改轮数"] = True
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_float_rejected(self):
        self.good["固定信息"]["价格（元）"] = 399.0
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_null_rejected(self):
        self.good["固定信息"]["修改轮数"] = None
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_empty_fixed_rejected(self):
        self.good["固定信息"] = {}
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_empty_copy_rejected(self):
        self.good["标题"] = "   "
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_extra_top_level_rejected(self):
        self.good["优惠说明"] = "免费送视频"
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_missing_top_level_rejected(self):
        del self.good["介绍"]
        with self.assertRaises(guard.InputError):
            guard.differences(self.base, self.good)

    def test_dictionary_order_ignored(self):
        self.good["固定信息"] = dict(reversed(list(self.good["固定信息"].items())))
        self.assertEqual(guard.differences(self.base, self.good), [])

    def test_list_order_is_strict(self):
        self.good["固定信息"]["交付内容"].reverse()
        self.assertEqual(len(guard.differences(self.base, self.good)), 1)

    def test_free_text_not_semantically_checked(self):
        self.good["介绍"] = "免费送一条视频，永久无限次修改。"
        self.assertEqual(guard.differences(self.base, self.good), [])

    def test_no_mutation(self):
        snapshot = copy.deepcopy((self.base, self.good))
        guard.differences(self.base, self.good)
        self.assertEqual((self.base, self.good), snapshot)

    def write_temp(self, raw):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "input.json"
        path.write_bytes(raw)
        return path

    def test_duplicate_keys_rejected(self):
        path = self.write_temp(b'{"a":1,"a":2}')
        with self.assertRaises(guard.InputError):
            guard.load_json(path)

    def test_lone_surrogates_rejected(self):
        inputs = [b'{"title":"\\ud800"}', b'{"intro":"\\udfff"}',
                  b'{"fixed":{"name":"\\ud800"}}',
                  b'{"fixed":{"\\ud800":"text"}}',
                  b'{"fixed":{"items":["\\udfff"]}}']
        for raw in inputs:
            with self.subTest(raw=raw), self.assertRaises(guard.InputError):
                guard.load_json(self.write_temp(raw))

    def test_surrogate_duplicate_key_error_is_printable(self):
        path = self.write_temp(b'{"\\ud800":1,"\\ud800":2}')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(guard.main([str(path), str(guard.BASE / "draft_good.json")]), 2)
        output.getvalue().encode("utf-8")

    def test_cli_lone_surrogate_draft(self):
        self.good["固定信息"]["服务名称"] = "\ud800"
        path = self.write_temp(json.dumps(self.good, ensure_ascii=True).encode("ascii"))
        result = subprocess.run([sys.executable, "-X", "utf8", str(guard.BASE / "guard.py"),
                                 str(guard.BASE / "baseline.json"), str(path)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertIn("INPUT ERROR", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_nonfinite_rejected(self):
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(value=value), self.assertRaises(guard.InputError):
                guard.load_json(self.write_temp(value))

    def test_invalid_json(self):
        with self.assertRaises(guard.InputError):
            guard.load_json(self.write_temp(b"{broken"))

    def test_utf8_bom_allowed(self):
        self.assertEqual(guard.load_json(self.write_temp(b'\xef\xbb\xbf{"a":1}')), {"a": 1})

    def test_limit(self):
        with self.assertRaises(guard.InputError):
            guard.load_json(self.write_temp(b" " * (guard.MAX_BYTES + 1)))

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(guard.InputError):
                guard.load_json(Path(directory) / "absent.json")

    def test_demo_exit(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status = guard.main(["--demo"])
        self.assertEqual(status, 0)
        self.assertIn("DEMO OK", output.getvalue())

    def test_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(guard.main([str(guard.BASE / "baseline.json"), str(guard.BASE / "draft_good.json")]), 0)
            self.assertEqual(guard.main([str(guard.BASE / "baseline.json"), str(guard.BASE / "draft_bad.json")]), 1)
            with tempfile.TemporaryDirectory() as directory:
                self.assertEqual(guard.main([str(Path(directory) / "absent.json"), str(guard.BASE / "draft_good.json")]), 2)


if __name__ == "__main__":
    unittest.main()
