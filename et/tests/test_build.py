# SPDX-License-Identifier: Apache-2.0
"""Fast offline controls. No compiler invocation, network or hardware access."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "build.py"
SPEC = importlib.util.spec_from_file_location("maxion_builder", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="maxion-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, data=b"test"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def git(self, *args):
        return builder.run(
            [builder.prerequisite("git"), "-c", "user.name=Offline Test",
             "-c", "user.email=offline@example.invalid", *args],
            self.root, builder.safe_environment())

    def source_repo(self):
        self.git("init", "-q")
        self.file("Makefile")
        self.git("add", "Makefile")
        self.git("commit", "-qm", "fixture")
        expected = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.tree_patch = patch.object(builder, "SOURCE_TREE", expected)
        self.tree_patch.start()
        self.addCleanup(self.tree_patch.stop)

    def test_source_tree_hash_matches_git_and_excludes_only_et(self):
        self.source_repo()
        before = builder.verify_source(self.root, builder.safe_environment())
        self.file("et/README.md")
        self.git("add", "et")
        self.git("commit", "-qm", "support")
        after = builder.verify_source(self.root, builder.safe_environment())
        self.assertEqual(before["source_tree_excluding_et"],
                         after["source_tree_excluding_et"])
        self.assertNotEqual(before["full_tree"], after["full_tree"])
        self.assertNotEqual(before["commit"], after["commit"])

    def test_dirty_tracked_source_unstaged_staged_and_deleted_rejected(self):
        self.source_repo()
        path = self.file("Makefile", b"modified")
        with self.assertRaisesRegex(builder.BuildError, "Dirty tracked source"):
            builder.verify_source(self.root, builder.safe_environment())
        self.git("add", "Makefile")
        with self.assertRaisesRegex(builder.BuildError, "Dirty tracked source"):
            builder.verify_source(self.root, builder.safe_environment())
        self.git("reset", "--hard", "-q", "HEAD")
        path.unlink()
        with self.assertRaisesRegex(builder.BuildError, "Dirty tracked source"):
            builder.verify_source(self.root, builder.safe_environment())

    def test_committed_source_change_rejected(self):
        self.source_repo()
        self.file("Makefile", b"new source")
        self.git("add", "Makefile")
        self.git("commit", "-qm", "wrong source")
        with self.assertRaisesRegex(builder.BuildError, "fingerprint mismatch"):
            builder.verify_source(self.root, builder.safe_environment())

    def test_uncommitted_support_allowed_and_reported(self):
        self.source_repo()
        self.file("et/build.py")
        receipt = builder.verify_source(self.root, builder.safe_environment())
        self.assertIn("et/build.py", receipt["support_status"])

    def test_missing_modified_truncated_and_symlink_reference_rejected(self):
        path = self.root / "missing.bin"
        with self.assertRaisesRegex(builder.BuildError, "Missing independent"):
            builder.verify_reference(path)
        self.file("bad.bin", b"\0" * builder.REFERENCE_SIZE)
        with self.assertRaisesRegex(builder.BuildError, "reference INVALID"):
            builder.verify_reference(self.root / "bad.bin")
        self.file("short.bin", b"\0")
        with self.assertRaisesRegex(builder.BuildError, "reference INVALID"):
            builder.verify_reference(self.root / "short.bin")
        link = self.root / "reference-link.bin"
        link.symlink_to(SCRIPT.parent / "reference/fw_jump.bin")
        with self.assertRaisesRegex(builder.BuildError, "Missing independent"):
            builder.verify_reference(link)

    def test_independent_reference_and_byte_comparison(self):
        reference = builder.verify_reference(SCRIPT.parent / "reference/fw_jump.bin")
        candidate = self.file("candidate.bin", reference)
        self.assertEqual(builder.compare_candidate(candidate, reference)["size"],
                         builder.REFERENCE_SIZE)
        # Same length, one changed byte: cannot bless candidate by editing a manifest.
        changed = bytearray(reference)
        changed[-1] ^= 1
        candidate.write_bytes(changed)
        with self.assertRaisesRegex(builder.BuildError, "BIT-IDENTICAL-FAIL"):
            builder.compare_candidate(candidate, reference)
        # Even a valid hash cannot substitute for the explicit byte comparison.
        candidate.write_bytes(reference)
        with self.assertRaisesRegex(builder.BuildError, "BIT-IDENTICAL-FAIL"):
            builder.compare_candidate(candidate, bytes(changed))

    def test_output_refuses_existing_directory_file_and_dangling_symlink(self):
        for name in ("directory", "file", "link"):
            path = self.root / name
            if name == "directory":
                path.mkdir()
            elif name == "file":
                path.write_bytes(b"old evidence")
            else:
                path.symlink_to(self.root / "absent")
            with self.assertRaises(FileExistsError):
                builder.new_output(self.root, str(path))
        self.assertEqual((self.root / "file").read_bytes(), b"old evidence")

    def test_unique_default_outputs(self):
        one = builder.new_output(self.root, None)
        two = builder.new_output(self.root, None)
        self.assertNotEqual(one, two)
        self.assertTrue(one.name.startswith("run-"))
        self.assertTrue(two.is_dir())

    def test_make_and_shell_metacharacters_and_spaces_rejected(self):
        for value in ("has space", "line\nbreak", "a#b", "a$b", "a%b",
                      "a;b", "a'b", "a`b", "a*b", "a\\b", "a=b", "a:b"):
            with self.subTest(path=value):
                with self.assertRaises(builder.BuildError):
                    builder.safe_path(value)
        builder.safe_path("/tmp/a-normal_path.1+suffix")

    def test_environment_does_not_inherit_build_or_loader_overrides(self):
        hostile = {"MAKEFLAGS": "-e", "CFLAGS": "-O0", "FW_FDT_PATH": "/bad",
                   "FW_JUMP_ADDR": "0", "CROSS_COMPILE": "wrong-",
                   "GCC_EXEC_PREFIX": "/bad", "PYTHONPATH": "/bad",
                   "BASH_ENV": "/bad", "LD_PRELOAD": "/bad", "PATH": "/bad",
                   "GIT_DIR": "/bad", "KCONFIG_CONFIG": "/bad"}
        with patch.dict(os.environ, hostile):
            env = builder.safe_environment()
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        self.assertEqual(env["SOURCE_DATE_EPOCH"], builder.EPOCH)
        self.assertFalse((set(hostile) - {"PATH"}) & set(env))

    def test_missing_prerequisite_is_actionable(self):
        with self.assertRaisesRegex(builder.BuildError, "Missing prerequisite.*never installs"):
            builder.prerequisite("not-a-real-maxion-build-command-123")

    def test_toolchain_binary_mismatch_fails(self):
        pins = json.loads((SCRIPT.parent / "toolchain.json").read_text())
        expected = pins["cross_tools"]["gcc"]
        altered = {**expected, "sha256": "0" * 64}
        with patch.object(builder, "prerequisite", return_value="/fake/tool"), \
                patch.object(builder, "run", return_value=b"/fake/tool\n"), \
                patch.object(builder, "tool_record", return_value=altered):
            with self.assertRaisesRegex(builder.BuildError, "Toolchain fingerprint mismatch"):
                builder.verify_toolchain(SCRIPT.parent, builder.safe_environment())

    def test_package_inventory_missing_packages_is_informational(self):
        result = subprocess.CompletedProcess(["dpkg-query"], 1,
                                             stdout=b"make\t4.3\n",
                                             stderr=b"no packages found: unused-dev\n")
        with patch.object(builder.shutil, "which", return_value="/usr/bin/dpkg-query"), \
                patch.object(builder.subprocess, "run", return_value=result):
            report = builder.package_inventory(["make", "unused-dev"], self.root,
                                               builder.safe_environment())
        self.assertEqual(report["exit_status"], 1)
        self.assertIn("make\t4.3", report["stdout"])
        self.assertIn("unused-dev", report["stderr"])
        self.assertIn("warning", report)

    def test_package_inventory_missing_dpkg_is_informational(self):
        with patch.object(builder.shutil, "which", return_value=None):
            report = builder.package_inventory(["unused-dev"], self.root,
                                               builder.safe_environment())
        self.assertIsNone(report["exit_status"])
        self.assertIn("dpkg-query unavailable", report["warning"])

    def test_package_inventory_execution_failure_is_informational(self):
        with patch.object(builder.shutil, "which", return_value="/usr/bin/dpkg-query"), \
                patch.object(builder.subprocess, "run", side_effect=OSError("unavailable")):
            report = builder.package_inventory(["unused-dev"], self.root,
                                               builder.safe_environment())
        self.assertIsNone(report["exit_status"])
        self.assertEqual(report["stderr"], "unavailable")
        self.assertIn("warning", report)

    def test_archive_traversal_links_and_special_files_rejected(self):
        for name, kind in (("../escape", tarfile.REGTYPE),
                           ("/absolute", tarfile.REGTYPE),
                           ("link", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE),
                           ("device", tarfile.CHRTYPE)):
            with self.subTest(name=name):
                archive = self.root / "source.tar"
                with tarfile.open(archive, "w") as stream:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/outside"
                    stream.addfile(member)
                target = self.root / ("extract-" + str(len(list(self.root.iterdir()))))
                with self.assertRaisesRegex(builder.BuildError, "Unsafe git archive"):
                    builder.extract_source(archive, target)

    def test_make_failure_retains_log_and_failed_receipt(self):
        out = self.root / "output"
        out.mkdir()

        def fake_run(command, **kwargs):
            if "archive" in command:
                with tarfile.open(fileobj=kwargs["stdout"], mode="w") as stream:
                    member = tarfile.TarInfo("Makefile")
                    member.size = 1
                    stream.addfile(member, io.BytesIO(b"x"))
                return subprocess.CompletedProcess(command, 0, stderr=b"")
            kwargs["stdout"].write(b"intentional make failure\n")
            return subprocess.CompletedProcess(command, 42)

        with patch.object(builder.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(builder.BuildError, "make failed with exit 42"):
                builder.build(self.root, SCRIPT.parent, out, builder.safe_environment(),
                              {"source": {"commit": "fixture"}}, b"", 2)
        receipt = json.loads((out / "build-receipt.json").read_text())
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["make_exit_status"], 42)
        self.assertIn(b"intentional make failure", (out / "build.log").read_bytes())
        self.assertTrue((out / "source.tar").is_file())

    def test_binary_mismatch_retains_outputs_and_failed_receipt(self):
        out = self.root / "mismatch-output"
        out.mkdir()
        reference = builder.verify_reference(SCRIPT.parent / "reference/fw_jump.bin")
        changed = bytearray(reference)
        changed[0] ^= 1

        def fake_run(command, **kwargs):
            if "archive" in command:
                with tarfile.open(fileobj=kwargs["stdout"], mode="w"):
                    pass
                return subprocess.CompletedProcess(command, 0, stderr=b"")
            firmware = out / "objects/platform/generic/firmware"
            firmware.mkdir(parents=True)
            (firmware / "fw_jump.bin").write_bytes(changed)
            (firmware / "fw_jump.elf").write_bytes(b"mock ELF")
            kwargs["stdout"].write(b"make exited successfully, binary is wrong\n")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(builder.subprocess, "run", side_effect=fake_run), \
                patch.object(builder, "run", return_value=b"mock ELF headers\n"):
            with self.assertRaisesRegex(builder.BuildError, "BIT-IDENTICAL-FAIL"):
                builder.build(self.root, SCRIPT.parent, out, builder.safe_environment(),
                              {"source": {"commit": "fixture"}}, reference, 2)
        receipt = json.loads((out / "build-receipt.json").read_text())
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["make_exit_status"], 0)
        self.assertEqual((out / "fw_jump.bin").read_bytes(), changed)
        self.assertTrue((out / "fw_jump.elf").is_file())
        self.assertTrue((out / "OUTPUT-SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()
