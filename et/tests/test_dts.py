# SPDX-License-Identifier: Apache-2.0
"""Offline host-only DT contracts, pins, provenance and publishing checks."""
import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "dts/build.py"
SPEC = importlib.util.spec_from_file_location("maxion_dts", SCRIPT)
dts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dts)


class ToolPins(unittest.TestCase):
    def setUp(self):
        self.sources = dts.source_files(dts.ROOT)
        self.pins = dts.load_pins(self.sources)

    def test_missing_tool(self):
        with patch.object(dts.os, "access", return_value=False):
            with self.assertRaisesRegex(ValueError, "missing or not executable"):
                dts.check_tools(self.pins)

    def test_wrong_tool_hash_before_execution(self):
        pins = copy.deepcopy(self.pins)
        pins["dtc"]["sha256"] = "0" * 64
        with patch.object(dts.subprocess, "check_output", side_effect=AssertionError("must not execute")):
            with self.assertRaisesRegex(ValueError, "executable hash mismatch"):
                dts.check_tools(pins)

    def test_wrong_version_or_package(self):
        for wrong in ((b"Version: DTC 9\n", b"1.6.1-1"),
                      (b"Version: DTC 1.6.1\n", b"1.6.1-2")):
            with self.subTest(wrong=wrong), patch.object(dts.subprocess, "check_output", side_effect=wrong):
                with self.assertRaisesRegex(ValueError, "version/package mismatch"):
                    dts.check_tools(self.pins)

    def test_historical_reference_pins(self):
        for name in json.loads(self.sources["PROVENANCE.json"])["reference_sha256"]:
            damaged = dict(self.sources)
            damaged[name] += b"tamper"
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "historical reference hash mismatch"):
                dts.load_pins(damaged)

    def test_reference_contract_without_tools(self):
        with patch.object(dts.subprocess, "run", side_effect=AssertionError("no tools")), \
             patch.object(dts.subprocess, "check_output", side_effect=AssertionError("no tools")):
            dts.validate_profile(self.sources["reference/maxion-9front-original.dtb"], "9front")
            dts.validate_profile(self.sources["reference/maxion-linux-public-base.dtb"], "linux")


class DeviceTrees(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path("/usr/bin/dtc").is_file():
            raise unittest.SkipTest("pinned native dtc not installed; tool-free contracts still run")
        cls.temp = tempfile.TemporaryDirectory(prefix="maxion-dts-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.out = cls.base / "build-1"
        cls.receipt = dts.build(cls.out)
        cls.files = {name: (cls.out / name).read_bytes() for name in dts.ASSETS}

    def clone(self, parent):
        root = parent / "dts"
        shutil.copytree(dts.ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
        return root

    def test_reproducible_all_four_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            other = Path(temp) / "elsewhere"
            with patch.dict(dts.os.environ, {"DTC_FLAGS": "--bad", "CPATH": "/missing",
                                             "CPPFLAGS": "-DBOOTARGS=private", "LC_ALL": "not-a-locale"}):
                dts.build(other)
            self.assertEqual(self.files, {name: (other / name).read_bytes() for name in dts.ASSETS})

    def test_output_cannot_be_reused(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            dts.build(self.out)
        with self.assertRaisesRegex(ValueError, "outside DT source"):
            dts.build(dts.ROOT / "out")

    def test_offline_tool_free_verify(self):
        with patch.object(dts.subprocess, "run", side_effect=AssertionError("publisher must not execute tools")), \
             patch.object(dts.subprocess, "check_output", side_effect=AssertionError("publisher must not execute tools")), \
             patch.object(dts, "source_archive", side_effect=AssertionError("publisher must not recompress gzip")):
            self.assertEqual(dts.verify_bundle(self.files, dts.ROOT), self.receipt)

    def test_exact_asset_set(self):
        for name in dts.ASSETS:
            files = dict(self.files)
            del files[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "exactly ASSETS"):
                dts.verify_bundle(files, dts.ROOT)
        with self.assertRaises(ValueError):
            dts.verify_bundle({**self.files, "build.log": b""}, dts.ROOT)

    def test_each_asset_tamper(self):
        for name in dts.ASSETS:
            files = dict(self.files)
            files[name] += b"tampered"
            with self.subTest(name=name), self.assertRaises(ValueError):
                dts.verify_bundle(files, dts.ROOT)

    def test_receipt_cannot_repin_output(self):
        files = dict(self.files)
        files["maxion-linux.dtb"] += b"tampered"
        receipt = copy.deepcopy(self.receipt)
        receipt["outputs"]["maxion-linux.dtb"] = dts.identity(files["maxion-linux.dtb"])
        files["dts-build-receipt.json"] = dts.json_bytes(receipt)
        with self.assertRaisesRegex(ValueError, "output pin mismatch"):
            dts.verify_bundle(files, dts.ROOT)

    def test_receipt_dirty_fields_and_whitespace(self):
        changes = [lambda r: r.update(extra="not allowed"),
                   lambda r: r["toolchain"]["dtc"].update(sha256="0" * 64),
                   lambda r: r["sources_sha256"].update({"maxion-linux.dts": "0" * 64}),
                   lambda r: r.update(status="failure"),
                   lambda r: r["outputs"]["dts-sources.tar.gz"].update(size=1)]
        for change in changes:
            receipt = copy.deepcopy(self.receipt)
            change(receipt)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "receipt differs"):
                dts.verify_bundle({**self.files, "dts-build-receipt.json": dts.json_bytes(receipt)}, dts.ROOT)
        with self.assertRaises(ValueError):
            dts.verify_bundle({**self.files, "dts-build-receipt.json": b" " + self.files["dts-build-receipt.json"]}, dts.ROOT)

    def test_source_comment_binds_archive_and_receipt_not_output(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = self.clone(parent)
            source = root / "maxion-linux.dts"
            source.write_bytes(source.read_bytes() + b"\n// provenance-only source edit\n")
            with self.assertRaises(ValueError):
                dts.verify_bundle(self.files, root)
            out = parent / "modified-build"
            receipt = dts.build(out, root=root)
            files = {name: (out / name).read_bytes() for name in dts.ASSETS}
            self.assertEqual(files["maxion-linux.dtb"], self.files["maxion-linux.dtb"])
            self.assertNotEqual(receipt["sources_sha256"], self.receipt["sources_sha256"])
            dts.verify_bundle(files, root)
            with self.assertRaises(ValueError):
                dts.verify_bundle(files, dts.ROOT)

    def test_changed_contract_cannot_build_by_reasserting_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = self.clone(parent)
            source = root / "maxion-linux.dts"
            source.write_text(source.read_text().replace("no4lvl", "no4lvl private-session=bad"))
            with self.assertRaisesRegex(ValueError, "output pin mismatch"):
                dts.build(parent / "bad-build", root=root)

    def test_explicit_inventory_excludes_outputs_and_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.clone(Path(temp))
            (root / "out").mkdir()
            (root / "out/private.dtb").write_bytes(b"must not archive")
            (root / "__pycache__").mkdir(exist_ok=True)
            (root / "__pycache__/build.pyc").write_bytes(b"must not archive")
            (root / "unused-symlink").symlink_to("/nonexistent")
            self.assertEqual(dts.source_files(root), dts.source_files(dts.ROOT))
            dts.verify_bundle(self.files, root)
            (root / "maxion-linux.dts").unlink()
            (root / "maxion-linux.dts").symlink_to(dts.ROOT / "maxion-linux.dts")
            with self.assertRaisesRegex(ValueError, "source symlink refused"):
                dts.source_files(root)

    def test_archive_canonical_metadata_content_inventory(self):
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(self.files["dts-sources.tar.gz"]), mode="r:gz") as archive:
            self.assertEqual(archive.getnames(), ["dts/" + name for name in sorted(dts.SOURCE_FILES)])
            for member in archive:
                self.assertTrue(member.isfile())
                self.assertEqual((member.mode, member.uid, member.gid, member.mtime, member.uname, member.gname),
                                 (0o644, 0, 0, 0, "", ""))
        # A dirty archive plus a correspondingly forged receipt must still fail.
        raw = bytearray(gzip.decompress(self.files["dts-sources.tar.gz"]))
        raw[100:108] = b"0000755\0"  # permissions in first canonical tar header
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
            stream.write(raw)
        changed = compressed.getvalue()
        receipt = copy.deepcopy(self.receipt)
        receipt["outputs"]["dts-sources.tar.gz"] = dts.identity(changed)
        with self.assertRaisesRegex(ValueError, "archive differs"):
            dts.verify_bundle({**self.files, "dts-sources.tar.gz": changed,
                               "dts-build-receipt.json": dts.json_bytes(receipt)}, dts.ROOT)
        # Timestamp changes are rejected before decompressing or reading tar.
        changed = bytearray(self.files["dts-sources.tar.gz"])
        changed[4] = 1
        with self.assertRaisesRegex(ValueError, "gzip header"):
            dts.verify_bundle({**self.files, "dts-sources.tar.gz": bytes(changed)}, dts.ROOT)

    def test_archive_expansion_and_crc_fail_closed(self):
        sources = dts.source_files(dts.ROOT)
        raw = dts.source_tar(sources)
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
            stream.write(raw + b"x" * (len(raw) * 10))
        with self.assertRaisesRegex(ValueError, "archive differs"):
            dts.verify_archive(compressed.getvalue(), sources)
        corrupt = bytearray(self.files["dts-sources.tar.gz"])
        corrupt[-8] ^= 1
        with self.assertRaisesRegex(ValueError, "invalid DT source gzip"):
            dts.verify_archive(bytes(corrupt), sources)

    def test_profiles_and_independent_references(self):
        for profile in ("linux", "9front"):
            candidate = self.files[f"maxion-{profile}.dtb"]
            reference = (dts.ROOT / "reference" / ("maxion-linux-public-base.dtb" if profile == "linux"
                                                    else "maxion-9front-original.dtb")).read_bytes()
            dts.validate_profile(candidate, profile)
            self.assertEqual(dts.normalize_phandles(dts.parse_dtb(candidate)),
                             dts.normalize_phandles(dts.parse_dtb(reference)))
            if profile == "linux":
                self.assertEqual(candidate, reference)
            else:
                self.assertNotEqual(candidate, reference)  # represented ordering change, not semantic drift
        # Check the preserved original 9front source against the original frozen DTB.
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "original.dtb"
            subprocess.run(["/usr/bin/dtc", "-I", "dts", "-O", "dtb", "-o", str(out),
                            str(dts.ROOT / "reference/maxion-9front-original.dts")],
                           env=dts.safe_environment(), check=True, capture_output=True)
            self.assertEqual(out.read_bytes(), (dts.ROOT / "reference/maxion-9front-original.dtb").read_bytes())

    def test_phandle_normalization_retains_reference_meaning(self):
        original = dts.expected_tree("9front")
        changed = copy.deepcopy(original)
        for props in changed.values():
            for key, data in list(props.items()):
                if key in ("phandle", "cold-boot-harts", "interrupt-parent", "interrupts-extended"):
                    words = list(struct.unpack(">" + "I" * (len(data)//4), data))
                    for i in range(0, len(words), 2 if key == "interrupts-extended" else 1):
                        words[i] += 100
                    props[key] = dts.cells(*words)
        self.assertEqual(dts.normalize_phandles(original), dts.normalize_phandles(changed))
        changed["/chosen/opensbi-config"]["cold-boot-harts"] = dts.cells(102)
        self.assertNotEqual(dts.normalize_phandles(original), dts.normalize_phandles(changed))

    def test_exact_structural_allowlist_rejects_private_data_and_drift(self):
        data = self.files["maxion-linux.dtb"]
        parsed = dts.parse_dtb(data)
        cases = [("/chosen", "linux,initrd-start", dts.cells(0x86, 0x10000000)),
                 ("/chosen", "private-session", b"secret\0"),
                 ("/cpus", "timebase-frequency", dts.cells(3733333)),
                 ("/soc/interrupt-controller@10000000", "esperanto,keep-priorities", None),
                 ("/soc/serial@12007000", "current-speed", dts.cells(115200)),
                 ("/cpus/cpu@0", "mmu-type", dts.strings("riscv,sv48"))]
        for path, key, value in cases:
            bad = copy.deepcopy(parsed)
            if value is None:
                del bad[path][key]
            else:
                bad[path][key] = value
            with self.subTest(key=key), patch.object(dts, "parse_dtb", return_value=bad):
                with self.assertRaisesRegex(ValueError, "contract mismatch"):
                    dts.validate_profile(data, "linux")
        for bad in (b"", b"bad" * 100, data[:-1], data + b"trailing"):
            with self.assertRaises(ValueError):
                dts.parse_dtb(bad)


if __name__ == "__main__":
    unittest.main()
