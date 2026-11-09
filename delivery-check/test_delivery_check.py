"""Synthetic tests, not a model benchmark. python -B -m unittest -v"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from delivery_check import InputError, inspect, main, read_plan, summary, validate_filename

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="delivery-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = self.root / "plan.csv"
        self.out = self.root / "output"
        self.out.mkdir()
        self.plan.write_text("id,file\nA,a.txt\nB,b.txt\nC,c.txt\n", encoding="utf-8")
        for name in ("a.txt", "b.txt", "c.txt"):
            (self.out / name).write_text("synthetic example\n", encoding="utf-8")
    def run_check(self):
        return inspect(read_plan(self.plan), self.out)
    def test_complete_folder_passes(self):
        self.assertEqual(summary(self.run_check()), "PASS expected=3 ok=3 missing=0 empty=0 extra=0 blocked=0")
    def test_same_count_still_fails(self):
        (self.out / "b.txt").unlink()
        (self.out / "c.txt").write_bytes(b"")
        (self.out / "old.txt").write_text("old", encoding="utf-8")
        self.assertEqual(len(list(self.out.iterdir())), 3)
        self.assertEqual(summary(self.run_check()), "FAIL expected=3 ok=1 missing=1 empty=1 extra=1 blocked=0")
    def test_missing_names_report_id(self):
        (self.out / "b.txt").unlink()
        self.assertEqual(self.run_check()["missing"], [{"id": "B", "file": "b.txt"}])
    def test_empty_zero_bytes(self):
        (self.out / "b.txt").write_bytes(b"")
        self.assertEqual(self.run_check()["empty"], [{"id": "B", "file": "b.txt"}])
    def test_nonempty_nonsense_is_not_quality_checked(self):
        (self.out / "b.txt").write_text(" ", encoding="utf-8")
        self.assertEqual(self.run_check()["status"], "PASS")
    def test_extra_hidden_file_is_not_silently_ignored(self):
        (self.out / ".DS_Store").write_bytes(b"x")
        self.assertEqual(self.run_check()["extra"], [".DS_Store"])
    def test_subdirectory_blocks(self):
        (self.out / "nested").mkdir()
        self.assertEqual(self.run_check()["blocked"], ["nested"])
        self.assertEqual(self.run_check()["status"], "FAIL")
    def test_symlink_blocks_without_following(self):
        try:
            (self.out / "link.txt").symlink_to(self.root / "absent.txt")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available")
        self.assertEqual(self.run_check()["blocked"], ["link.txt"])
    def test_root_symlink_rejected(self):
        link = self.root / "alias"
        try:
            link.symlink_to(self.out, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available")
        with self.assertRaises(InputError):
            inspect(read_plan(self.plan), link)
    def test_missing_output_rejected(self):
        with self.assertRaises(InputError):
            inspect(read_plan(self.plan), self.root / "absent")
    def test_wrong_header_rejected(self):
        self.plan.write_text("id,file,extra\nA,a.txt,1\n", encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_empty_plan_rejected(self):
        self.plan.write_text("id,file\n", encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_duplicate_id_rejected(self):
        self.plan.write_text("id,file\nA,a.txt\nA,b.txt\n", encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_duplicate_filename_rejected(self):
        for second in ("a.txt", "A.txt"):
            with self.subTest(second=second):
                self.plan.write_text(f"id,file\nA,a.txt\nB,{second}\n", encoding="utf-8")
                with self.assertRaises(InputError):
                    read_plan(self.plan)
    def test_unicode_normalization_collision_rejected(self):
        self.plan.write_text("id,file\nA,café.txt\nB,cafe\u0301.txt\n", encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_unsafe_filenames_rejected(self):
        for name in ("../secret", "/absolute", "a/b", r"a\b", "C:note", "NUL.txt", "con", "COM1.log", "LPT².txt", "a.", " a", "a\n", ".", "..", ""):
            with self.subTest(name=name), self.assertRaises(InputError):
                validate_filename(name)
    def test_filename_byte_length_limit(self):
        validate_filename("中" * 58 + ".txt")
        with self.assertRaises(InputError):
            validate_filename("中" * 59 + ".txt")
    def test_malformed_csv_rejected(self):
        self.plan.write_text('id,file\nA,"unterminated\n', encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_invalid_id_rejected(self):
        self.plan.write_text("id,file\nA B,a.txt\n", encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_wrong_row_width_rejected(self):
        self.plan.write_text("id,file\nA,a.txt,extra\n", encoding="utf-8")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_invalid_utf8_rejected(self):
        self.plan.write_bytes(b"id,file\nA,\xff.txt\n")
        with self.assertRaises(InputError):
            read_plan(self.plan)
    def test_bom_crlf_and_quoted_comma(self):
        self.plan.write_bytes('\ufeffid,file\r\nA,"a,b.txt"\r\n'.encode("utf-8"))
        self.assertEqual(read_plan(self.plan), [{"id": "A", "file": "a,b.txt"}])
    def test_chinese_filename(self):
        self.plan.write_text("id,file\nA,说明.txt\n", encoding="utf-8")
        self.assertEqual(read_plan(self.plan)[0]["file"], "说明.txt")
    def test_permission_error_not_pass(self):
        with mock.patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            with self.assertRaises(InputError):
                self.run_check()
    def test_cli_codes_and_json(self):
        args = ["--plan", str(self.plan), "--output", str(self.out), "--json"]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(stream.getvalue())["status"], "PASS")
        (self.out / "b.txt").unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 1)
        self.plan.write_text("bad", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
    def test_check_does_not_change_file_bytes(self):
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        self.run_check()
        after = {p.name: p.read_bytes() for p in self.out.iterdir()}
        self.assertEqual(before, after)

if __name__ == "__main__":
    unittest.main()
