# SPDX-License-Identifier: Apache-2.0
"""Offline packaging/publishing controls; no compiler, network or hardware."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "ci/release.py"
SPEC = importlib.util.spec_from_file_location("maxion_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="maxion-release-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.build = self.base / "build"
        self.out = self.base / "assets"
        self.build.mkdir()
        self.tag = "maxion-v1.0.0"
        for name in (*release.COPIES.values(), "et/build.py", "et/.gitignore", "et/reference/fw_jump.bin",
                     "et/ci/release.py", "et/ci/publish-release.sh"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((release.ROOT / name).read_bytes())
        # Git commits/tags exist only in this disposable fixture, never the
        # working repository. Pin its non-et tree without weakening real pins.
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture source")
        fixture_tree = release.builder.filtered_root_tree(self.git("ls-tree", "-z", "HEAD"))
        build_script = self.root / "et/build.py"
        build_script.write_text(build_script.read_text().replace(
            'SOURCE_TREE = "' + release.builder.SOURCE_TREE + '"',
            'SOURCE_TREE = "' + fixture_tree + '"'))
        self.git("add", ".")
        self.git("commit", "-qm", "fixture recipe pin")
        self.git("tag", "-a", self.tag, "-m", "fixture annotated tag")
        tree_patch = patch.object(release.builder, "SOURCE_TREE", fixture_tree)
        tree_patch.start()
        self.addCleanup(tree_patch.stop)
        self.source = release.builder.verify_source(self.root, release.builder.safe_environment())
        reference = (self.root / "et/reference/fw_jump.bin").read_bytes()
        for name, data in {
            "fw_jump.bin": reference, "fw_jump.elf": b"mock diagnostic ELF\n",
            "build.log": b"mock successful build\n", "fw_jump.readelf.txt": b"mock ELF inspection\n",
        }.items():
            (self.build / name).write_bytes(data)
        pins = json.loads((self.root / "et/toolchain.json").read_text())
        self.receipt = {
            "status": "BIT-IDENTICAL-PASS", "make_exit_status": 0,
            "inputs": {
                "source": copy.deepcopy(self.source),
                "reference": release.reference_identity(),
                "support_sha256": {
                    name: release.sha((self.root / "et" / name).read_bytes())
                    for name in ("build.py", "toolchain.json")
                },
                "toolchain": {"cross_tools": pins["cross_tools"]},
            },
            "comparison": {**release.reference_identity(), "byte_comparison": "identical"},
            "output_sha256": {
                name: release.sha((self.build / name).read_bytes()) for name in release.OUTPUTS
            },
        }
        self.save_receipt()
        # In-process negative tests can alter just one source field. Subprocess
        # CLI/publisher tests use real Git and the disposable checkout above.
        for name, value in (("verify_source", self.source),
                            ("run", (self.source["commit"] + "\n").encode())):
            patcher = patch.object(release.builder, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, *args):
        result = subprocess.run(
            ["/usr/bin/git", "-c", "user.name=Offline Test",
             "-c", "user.email=offline@example.invalid", *args],
            cwd=self.root, env=release.builder.safe_environment(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return result.stdout

    def save_receipt(self):
        (self.build / "build-receipt.json").write_bytes(release.json_bytes(self.receipt))

    def package(self):
        return release.package(self.root, self.build, self.out, self.tag)

    def rejected(self, message):
        with self.assertRaisesRegex((release.ReleaseError, release.builder.BuildError), message):
            self.package()
        self.assertFalse(self.out.exists(), "Invalid input must not create a package")

    def test_positive_package_and_cli_verification(self):
        manifest = self.package()
        self.assertEqual(set(p.name for p in self.out.iterdir()), set(release.ASSETS))
        self.assertEqual(len(release.ASSETS), 14)
        for name in ("COPYING.BSD", "ThirdPartyNotices.md"):
            self.assertEqual((self.out / name).read_bytes(), (self.root / name).read_bytes())
        for name in (*release.OUTPUTS, "build-receipt.json"):
            self.assertEqual((self.out / name).read_bytes(), (self.build / name).read_bytes())
        self.assertEqual(manifest["commit"], self.source["commit"])
        self.assertEqual(manifest["source"]["full_tree"], self.source["full_tree"])
        self.assertEqual(manifest["receipt_sha256"],
                         release.sha((self.out / "build-receipt.json").read_bytes()))
        self.assertEqual(manifest["provenance_sha256"],
                         release.sha((self.out / "PROVENANCE.json").read_bytes()))
        for line in (self.out / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ")
            self.assertEqual(digest, release.sha((self.out / name).read_bytes()))
        notes = (self.out / "RELEASE-NOTES.md").read_text()
        self.assertIn("immutable pinned historical raw-byte baseline", notes)
        self.assertIn("not a new hardware boot", notes)
        result = subprocess.run([sys.executable, str(self.root / "et/ci/release.py"), "verify",
                                 "--assets", str(self.out), "--tag", self.tag],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_and_incomplete_build_receipts_rejected(self):
        for status in ("FAIL", "INCOMPLETE", "INPUTS-VERIFIED", None):
            with self.subTest(status=status):
                self.receipt["status"] = status
                self.save_receipt()
                self.rejected("not BIT-IDENTICAL-PASS")
        self.receipt["status"] = "BIT-IDENTICAL-PASS"
        self.receipt["make_exit_status"] = 42
        self.save_receipt()
        self.rejected("unsuccessful build")

    def test_each_output_tamper_and_missing_hash_rejected(self):
        for name in release.OUTPUTS:
            with self.subTest(name=name):
                original = (self.build / name).read_bytes()
                (self.build / name).write_bytes(original + b"tamper")
                self.rejected("baseline|output SHA256")
                (self.build / name).write_bytes(original)
        del self.receipt["output_sha256"]["build.log"]
        self.save_receipt()
        self.rejected("output SHA256")

    def test_wrong_candidate_even_with_rehashed_receipt_rejected(self):
        path = self.build / "fw_jump.bin"
        changed = bytearray(path.read_bytes())
        changed[-1] ^= 1
        path.write_bytes(changed)
        self.receipt["output_sha256"]["fw_jump.bin"] = release.sha(changed)
        self.save_receipt()
        self.rejected("immutable raw-byte baseline")

    def test_reference_cannot_be_replaced_with_candidate(self):
        reference = self.root / "et/reference/fw_jump.bin"
        reference.write_bytes(b"replacement")
        (self.build / "fw_jump.bin").write_bytes(b"replacement")
        with self.assertRaisesRegex(release.builder.BuildError, "reference INVALID"):
            self.package()
        self.assertFalse(self.out.exists())

    def test_stale_commit_tree_and_dirty_receipt_support_rejected(self):
        for key in ("commit", "full_tree", "source_tree_excluding_et"):
            with self.subTest(key=key):
                original = self.receipt["inputs"]["source"][key]
                self.receipt["inputs"]["source"][key] = "0" * 40
                self.save_receipt()
                self.rejected("Receipt source is stale")
                self.receipt["inputs"]["source"][key] = original
        self.receipt["inputs"]["source"]["support_status"] = " M et/build.py\n"
        self.save_receipt()
        self.rejected("Receipt support tree is dirty")

    def test_dirty_current_support_and_source_rejected(self):
        self.source["support_status"] = "?? et/unreviewed.py\n"
        self.rejected("Current support tree is dirty")
        self.source["support_status"] = ""
        with patch.object(release.builder, "verify_source",
                          side_effect=release.builder.BuildError("Dirty tracked source")):
            self.rejected("Dirty tracked source")

    def test_changed_support_recipe_or_toolchain_rejected(self):
        for name in ("build.py", "toolchain.json"):
            with self.subTest(name=name):
                path = self.root / "et" / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.rejected("support hashes differ")
                path.write_bytes(original)
        self.receipt["inputs"]["toolchain"]["cross_tools"]["gcc"]["sha256"] = "0" * 64
        self.save_receipt()
        self.rejected("pinned toolchain differs")

    def test_strict_tags_and_tag_commit_mismatch(self):
        for tag in ("v1.0.0", "maxion-v01.0.0", "maxion-v1.00.0", "maxion-v1.0.01",
                    "maxion-v1.0", "maxion-v1.0.0-rc1", "maxion-v1.0.0\n",
                    "maxion-v1.0.0/other", "--help"):
            with self.subTest(tag=tag):
                self.tag = tag
                self.rejected("Invalid downstream tag")
        self.tag = "maxion-v1.0.0"
        with patch.object(release.builder, "run", return_value=b"cccccccccccccccccccccccccccccccccccccccc\n"):
            self.rejected("Tag does not resolve to current HEAD")
        with patch.object(release.builder, "run",
                          side_effect=release.builder.BuildError("Missing tag")):
            self.rejected("Missing tag")

    def test_reused_directory_file_and_dangling_symlink_refused(self):
        for kind in ("dir", "file", "link"):
            with self.subTest(kind=kind):
                self.out = self.base / ("old-" + kind)
                if kind == "dir":
                    self.out.mkdir()
                elif kind == "file":
                    self.out.write_bytes(b"old evidence")
                else:
                    self.out.symlink_to(self.base / "absent")
                with self.assertRaisesRegex(release.ReleaseError, "already exists"):
                    self.package()
        self.assertEqual((self.base / "old-file").read_bytes(), b"old evidence")

    def test_missing_and_symlinked_assets_rejected(self):
        path = self.build / "fw_jump.elf"
        path.unlink()
        self.rejected("Missing regular file")
        path.symlink_to(self.root / "et/reference/fw_jump.bin")
        self.rejected("Missing regular file")

    def test_publish_verification_rejects_tag_tamper_extra_files_and_symlinks(self):
        self.package()
        with self.assertRaisesRegex(release.ReleaseError, "tag mismatch"):
            release.verify_package(self.out, "maxion-v2.0.0")
        extra = self.out / "unreviewed-asset"
        extra.write_bytes(b"arbitrary")
        with self.assertRaisesRegex(release.ReleaseError, "exactly"):
            release.verify_package(self.out, self.tag)
        extra.unlink()
        path = self.out / "build.log"
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(release.ReleaseError, "SHA256SUMS mismatch"):
            release.verify_package(self.out, self.tag)
        path.unlink()
        path.symlink_to(self.build / "build.log")
        with self.assertRaisesRegex(release.ReleaseError, "Missing regular file"):
            release.verify_package(self.out, self.tag)

    def reseal(self):
        """Model an internally consistent but potentially untrusted download."""
        manifest = json.loads((self.out / "release.json").read_text())
        manifest["assets_sha256"] = {
            name: release.sha((self.out / name).read_bytes()) for name in release.PAYLOADS
        }
        manifest["receipt_sha256"] = manifest["assets_sha256"]["build-receipt.json"]
        manifest["provenance_sha256"] = manifest["assets_sha256"]["PROVENANCE.json"]
        (self.out / "release.json").write_bytes(release.json_bytes(manifest))
        (self.out / "SHA256SUMS").write_text("".join(
            f"{release.sha((self.out / name).read_bytes())}  {name}\n"
            for name in sorted(set(release.ASSETS) - {"SHA256SUMS"})))

    def verify_cli(self):
        return subprocess.run(
            [sys.executable, str(self.root / "et/ci/release.py"), "verify",
             "--assets", str(self.out), "--tag", self.tag],
            capture_output=True, text=True)

    def test_cli_package_with_real_clean_annotated_tag_checkout(self):
        result = subprocess.run(
            [sys.executable, str(self.root / "et/ci/release.py"), "package",
             "--build", str(self.build), "--out", str(self.out), "--tag", self.tag],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.verify_cli().returncode, 0)

    def test_checkout_verification_rejects_resealed_wrong_manifest_commit(self):
        self.package()
        path = self.out / "release.json"
        manifest = json.loads(path.read_text())
        manifest["commit"] = manifest["tag_commit"] = "0" * 40
        path.write_bytes(release.json_bytes(manifest))
        self.reseal()
        release.verify_package(self.out, self.tag)  # Internally valid is insufficient.
        result = self.verify_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source differs from current checkout", result.stderr)

    def test_checkout_verification_rejects_resealed_stale_receipt(self):
        self.package()
        path = self.out / "build-receipt.json"
        receipt = json.loads(path.read_text())
        receipt["inputs"]["source"]["commit"] = "0" * 40
        path.write_bytes(release.json_bytes(receipt))
        self.reseal()
        release.verify_package(self.out, self.tag)
        result = self.verify_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Receipt source is stale", result.stderr)

    def test_checkout_verification_rejects_resealed_copied_files(self):
        self.package()
        for name in release.COPIES:
            with self.subTest(name=name):
                path = self.out / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.reseal()
                release.verify_package(self.out, self.tag)
                result = self.verify_cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("differs", result.stderr)
                path.write_bytes(original)
                self.reseal()

    def test_checkout_verification_rejects_dirty_support_source_and_moved_local_tag(self):
        self.package()
        for name in ("et/PROVENANCE.json", "COPYING.BSD"):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                result = self.verify_cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("dirty" if name.startswith("et/") else "Dirty", result.stderr)
                path.write_bytes(original)
        self.git("tag", "-f", self.tag, "HEAD~1")
        result = self.verify_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Tag does not resolve to current HEAD", result.stderr)

    def publisher(self, mode):
        self.package()
        bindir = self.base / "mock-bin"
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text("""#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["MOCK_GH_LOG"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
mode = os.environ["MOCK_GH_MODE"]
if args[:1] == ["api"]:
    moved = mode == "wrongremote" or (mode == "movedafterdraft"
        and pathlib.Path(os.environ["MOCK_GH_DRAFT"]).exists())
    print("0" * 40 if moved else os.environ["MOCK_GH_COMMIT"])
    sys.exit(0)
if args[:2] == ["release", "view"]:
    sys.exit(0 if mode == "existing" else 1)
if args[:2] == ["release", "create"]:
    pathlib.Path(os.environ["MOCK_GH_DRAFT"]).write_text("draft")
    sys.exit(1 if mode == "createfail" else 0)
if args[:2] == ["release", "edit"]:
    if mode == "editfail":
        sys.exit(1)
    pathlib.Path(os.environ["MOCK_GH_DRAFT"]).write_text("published")
    sys.exit(0)
sys.exit(9)
""")
        gh.chmod(0o755)
        log = self.base / "gh.log"
        state = self.base / "gh.state"
        result = subprocess.run(
            ["bash", str(self.root / "et/ci/publish-release.sh"), self.tag, str(self.out)],
            env={**os.environ, "PATH": str(bindir) + ":" + os.environ["PATH"],
                 "GH_REPO": "offline/example", "MOCK_GH_LOG": str(log),
                 "MOCK_GH_MODE": mode, "MOCK_GH_DRAFT": str(state),
                 "MOCK_GH_COMMIT": self.source["commit"]},
            capture_output=True, text=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return result, calls, state

    def test_publish_explicit_verified_assets_draft_then_publish(self):
        result, calls, state = self.publisher("success")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in calls],
                         ["api", "release", "release", "api", "release"])
        expected_api = ["api", "repos/offline/example/commits/" + self.tag, "--jq", ".sha"]
        self.assertEqual(calls[0], expected_api)
        self.assertEqual(calls[3], expected_api)
        create = calls[2]
        self.assertIn("--verify-tag", create)
        self.assertIn("--draft", create)
        self.assertEqual(create[create.index("--notes-file") + 1],
                         str(self.out / "RELEASE-NOTES.md"))
        self.assertEqual(set(create[create.index("--notes-file") + 2:]),
                         {str(self.out / name) for name in release.ASSETS})
        self.assertEqual(calls[4], ["release", "edit", self.tag, "--draft=false"])
        self.assertEqual(state.read_text(), "published")

    def test_existing_release_never_replaced(self):
        result, calls, state = self.publisher("existing")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertFalse(state.exists())

    def test_failed_create_does_not_publish_or_delete_draft(self):
        result, calls, state = self.publisher("createfail")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(state.read_text(), "draft")

    def test_failed_edit_leaves_draft_and_does_not_retry_or_delete(self):
        result, calls, state = self.publisher("editfail")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 5)
        self.assertEqual(state.read_text(), "draft")

    def test_wrong_remote_tag_never_creates_release(self):
        result, calls, state = self.publisher("wrongremote")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("Remote tag differs", result.stderr)
        self.assertFalse(state.exists())

    def test_remote_tag_moved_after_upload_leaves_draft(self):
        result, calls, state = self.publisher("movedafterdraft")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 4)
        self.assertEqual(state.read_text(), "draft")


if __name__ == "__main__":
    unittest.main()
