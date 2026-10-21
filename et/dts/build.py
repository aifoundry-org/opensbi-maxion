#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pinned, offline Maxion device trees. No hardware or third-party Python modules."""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import zlib

ROOT = Path(__file__).resolve().parent
ASSETS = ("maxion-linux.dtb", "maxion-9front.dtb", "dts-build-receipt.json", "dts-sources.tar.gz")
DTBS = ASSETS[:2]
RECIPE = ["/usr/bin/dtc", "-I", "dts", "-O", "dtb", "-o", "OUTPUT", "PROFILE.dts"]
SOURCE_FILES = (
    "COMPARISON.md", "LICENSE.Apache-2.0", "NOTICE", "PROVENANCE.json", "README.md",
    "build.py", "maxion-9front.dts", "maxion-common.dtsi", "maxion-linux.dts",
    "reference/etsoc1-maxion-linux-original.dts",
    "reference/etsoc1-maxion-original.dtsi",
    "reference/maxion-9front-original.dtb",
    "reference/maxion-9front-original.dts",
    "reference/maxion-linux-public-base.dtb", "toolchain.json",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def source_files(root):
    """Explicit release allowlist; ignored outputs/caches never enter inventory."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("DT source directory must be a real directory")
    result = {}
    for name in sorted(SOURCE_FILES):
        path = root / name
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError(f"source symlink refused: {name}")
        if not path.is_file():
            raise ValueError(f"missing/non-regular DT source: {name}")
        result[name] = path.read_bytes()
    return result


def source_tar(sources):
    """Canonical POSIX tar, without paths, clocks, owners or modes from host."""
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(sources.items()):
            info = tarfile.TarInfo("dts/" + name)
            info.size = len(data)
            info.mode = 0o644
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    return tar.getvalue()


def source_archive(sources):
    """Deterministic gzip header on Python 3.10 and newer."""
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed,
                       compresslevel=9, mtime=0) as stream:
        stream.write(source_tar(sources))
    return compressed.getvalue()


def verify_archive(archive, sources):
    # Do not recompress on the publisher: zlib releases can encode the same tar
    # differently. Exact canonical tar comparison checks names, order, metadata,
    # contents and padding (and never extracts potentially hostile paths).
    if archive[:10] != b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff":
        raise ValueError("noncanonical DT archive gzip header")
    expected = source_tar(sources)
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive), mode="rb") as stream:
            # One extra byte both bounds expansion and forces CRC/trailer checks
            # for an archive of the expected length.
            unpacked = stream.read(len(expected) + 1)
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("invalid DT source gzip archive") from exc
    if unpacked != expected:
        raise ValueError("DT source archive differs from current tagged sources")


def load_pins(sources):
    try:
        pins = json.loads(sources["toolchain.json"])
        if (pins["schema"] != 1 or pins["dtc"]["path"] != "/usr/bin/dtc"
                or set(pins["outputs"]) != set(DTBS)):
            raise ValueError("invalid DT toolchain pin schema")
        for entry in pins["outputs"].values():
            if len(entry["sha256"]) != 64 or entry["size"] <= 0:
                raise ValueError("invalid DT output pin")
        provenance = json.loads(sources["PROVENANCE.json"])
        for name, expected in provenance["reference_sha256"].items():
            if sha(sources[name]) != expected:
                raise ValueError(f"historical reference hash mismatch: {name}")
        return pins
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid DT source pins/provenance") from exc


def safe_environment():
    return {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "0"}


def check_tools(pins):
    tool = pins["dtc"]
    path = Path(tool["path"])
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("pinned /usr/bin/dtc is missing or not executable")
    if sha(path.read_bytes()) != tool["sha256"]:
        raise ValueError("dtc executable hash mismatch")
    try:
        version = subprocess.check_output([str(path), "--version"], env=safe_environment()).decode().strip()
        package = subprocess.check_output(
            ["/usr/bin/dpkg-query", "-W", "-f=${Version}", "device-tree-compiler"],
            env=safe_environment()).decode().strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("cannot verify pinned dtc version/package") from exc
    if version != tool["version"] or package != tool["package_version"]:
        raise ValueError("dtc version/package mismatch")


def cells(*values):
    return struct.pack(">" + "I" * len(values), *values)


def strings(*values):
    return b"".join(value.encode("ascii") + b"\0" for value in values)


def parse_dtb(data):
    """Small strict FDT-v17 reader; no dtc/fdtget is needed to verify a release."""
    def fail():
        raise ValueError("invalid or unsupported DTB structure")

    if len(data) < 56:
        fail()
    magic, total, off, stroff, reserve, version, last, boot, strsize, size = struct.unpack_from(">10I", data)
    if (magic != 0xD00DFEED or total != len(data) or version != 17 or last != 16
            or boot != 0 or reserve != 40 or data[40:56] != bytes(16)
            or off != 56 or off + size != stroff or stroff + strsize != total):
        fail()
    names = data[stroff:]
    end = off + size
    stack, nodes = [], {}
    cursor = off
    finished = False
    while cursor < end:
        if cursor + 4 > end:
            fail()
        token, = struct.unpack_from(">I", data, cursor)
        cursor += 4
        if token == 1:  # FDT_BEGIN_NODE
            stop = data.find(b"\0", cursor, end)
            if stop < 0:
                fail()
            try:
                name = data[cursor:stop].decode("ascii")
            except UnicodeDecodeError:
                fail()
            if "/" in name or (not stack and (name or nodes)) or (stack and not name):
                fail()
            path = "/" + "/".join(stack[1:] + [name]) if stack else "/"
            if path in nodes:
                fail()
            nodes[path] = {}
            stack.append(name)
            cursor = (stop + 4) & ~3
        elif token == 2:  # FDT_END_NODE
            if not stack:
                fail()
            stack.pop()
        elif token == 3:  # FDT_PROP
            if not stack or cursor + 8 > end:
                fail()
            length, nameoff = struct.unpack_from(">II", data, cursor)
            cursor += 8
            stop = names.find(b"\0", nameoff)
            if nameoff >= len(names) or stop < 0 or cursor + length > end:
                fail()
            try:
                name = names[nameoff:stop].decode("ascii")
            except UnicodeDecodeError:
                fail()
            path = "/" + "/".join(stack[1:])
            if not name or name in nodes[path]:
                fail()
            nodes[path][name] = data[cursor:cursor + length]
            cursor = (cursor + length + 3) & ~3
        elif token == 9:  # FDT_END
            if stack or cursor != end:
                fail()
            finished = True
        else:  # No NOP/padding/extensions in the pinned outputs.
            fail()
    if not finished or not nodes:
        fail()
    return nodes


def normalize_phandles(nodes):
    """Compare semantics, ignoring allocation IDs and node/property order only."""
    targets = {}
    for path, props in nodes.items():
        values = [props[key] for key in ("phandle", "linux,phandle") if key in props]
        if values:
            if any(len(value) != 4 or value != values[0] for value in values):
                raise ValueError("invalid phandle")
            value, = struct.unpack(">I", values[0])
            if value in (0, 0xFFFFFFFF) or value in targets:
                raise ValueError("duplicate or invalid phandle")
            targets[value] = path
    normalized = {}
    for path, props in nodes.items():
        normalized[path] = {}
        for name, value in props.items():
            if name in ("phandle", "linux,phandle"):
                continue
            if name in ("cold-boot-harts", "interrupt-parent", "interrupts-extended"):
                stride = 2 if name == "interrupts-extended" else 1
                if not value or len(value) % (4 * stride):
                    raise ValueError("invalid phandle reference array")
                words = struct.unpack(">" + "I" * (len(value) // 4), value)
                try:
                    value = tuple((targets[words[i]], *words[i + 1:i + stride])
                                  for i in range(0, len(words), stride))
                except KeyError as exc:
                    raise ValueError("unresolved phandle reference") from exc
            normalized[path][name] = value
    return normalized


def expected_tree(profile):
    if profile not in ("linux", "9front"):
        raise ValueError("unknown DT profile")
    linux = profile == "linux"
    tree = {
        "/": {"#address-cells": cells(2), "#size-cells": cells(2),
              "compatible": strings("esperanto,et-soc-1"),
              "model": strings("Esperanto ET-SoC-1 (Maxion)" if linux else
                               "Esperanto ET-SoC-1 Maxion: 9front RAM-root bring-up")},
        "/chosen": {"stdout-path": strings("serial0"), "bootargs": strings(
            "earlycon=sbi console=ttyS0,115200n8 no4lvl" if linux else
            "console=0 user=glenda *ncpu=1 *uartpoll=1")},
        "/chosen/opensbi-config": {"compatible": strings("opensbi,config"),
                                    "cold-boot-harts": cells(1)},
        "/aliases": {"serial0": strings("/soc/serial@12007000")},
        "/memory@8600000000": {"device_type": strings("memory"), "reg": cells(0x86, 0, 0, 0x40000000)},
        "/cpus": {"#address-cells": cells(1), "#size-cells": cells(0), "timebase-frequency": cells(9330000)},
        "/soc": {"#address-cells": cells(2), "#size-cells": cells(2), "compatible": strings("simple-bus"), "ranges": b""},
        "/soc/clint@2000000": {"compatible": strings("sifive,clint0", "riscv,clint0"),
                                 "reg": cells(0, 0x2000000, 0, 0x10000),
                                 "interrupts-extended": cells(*(v for n in range(4) for v in (n+2, 3, n+2, 7)))},
        "/soc/interrupt-controller@10000000": {
            "compatible": strings("sifive,plic-1.0.0", "riscv,plic0"),
            "reg": cells(0, 0x10000000, 0, 0x2000000), "#address-cells": cells(0),
            "#interrupt-cells": cells(1), "interrupt-controller": b"", "riscv,ndev": cells(41),
            "esperanto,keep-priorities": b"", "phandle": cells(6),
            "interrupts-extended": cells(*(v for n in range(4) for v in (n+2, 9, n+2, 11)))},
        "/soc/serial@12007000": {"compatible": strings("snps,dw-apb-uart", "ns16550a"),
                                  "reg": cells(0, 0x12007000, 0, 0x1000), "reg-shift": cells(2),
                                  "reg-io-width": cells(4), "clock-frequency": cells(25000000),
                                  "current-speed": cells(0), "interrupt-parent": cells(6),
                                  "interrupts": cells(15), "status": strings("okay")},
    }
    for n in range(4):
        path = f"/cpus/cpu@{n}"
        tree[path] = {"device_type": strings("cpu"), "reg": cells(n), "status": strings("okay"),
                      "compatible": strings("riscv"), "riscv,isa": strings("rv64imafdc"),
                      "mmu-type": strings("riscv,sv39" if linux else "riscv,sv48")}
        if n == 0:
            tree[path]["phandle"] = cells(1)
        if linux or n == 0:
            tree[path].update({"riscv,isa-base": strings("rv64i"),
                               "riscv,isa-extensions": strings("i", "m", "a", "f", "d", "c", "zicsr", "zifencei")})
        tree[path + "/interrupt-controller"] = {
            "#address-cells": cells(0), "#interrupt-cells": cells(1), "interrupt-controller": b"",
            "compatible": strings("riscv,cpu-intc"), "phandle": cells(n + 2)}
    return tree


def validate_profile(data, profile):
    actual = normalize_phandles(parse_dtb(data))
    expected = normalize_phandles(expected_tree(profile))
    if actual != expected:
        changed = sorted(path for path in actual.keys() | expected.keys()
                         if actual.get(path) != expected.get(path))
        raise ValueError(f"{profile} DT contract mismatch: {', '.join(changed)}")


def identity(data):
    return {"sha256": sha(data), "size": len(data)}


def receipt_for(sources, pins, outputs, archive):
    return {
        "schema": 1,
        "status": "PINNED-DT-PASS",
        "recipe": RECIPE,
        "toolchain": pins,
        "sources_sha256": {name: sha(data) for name, data in sorted(sources.items())},
        "outputs": {**{name: identity(outputs[name]) for name in DTBS},
                    "dts-sources.tar.gz": identity(archive)},
        "qualification": "Static rebuild only; no new hardware qualification or runtime memory ownership.",
    }


def verify_bundle(files: dict[str, bytes], source_dir: Path):
    """Offline/tool-free verification against the caller's trusted tagged et/dts tree.

    No subprocesses, network, extraction or reliance on receipt assertions. Raises
    ValueError on mismatch; returns the expected receipt on success. Only these
    four DT assets are accepted (pass a subset of the full firmware release).
    """
    if set(files) != set(ASSETS) or any(not isinstance(data, bytes) for data in files.values()):
        raise ValueError("DT bundle must contain exactly ASSETS as bytes")
    sources = source_files(source_dir)
    pins = load_pins(sources)
    for name in DTBS:
        if identity(files[name]) != pins["outputs"][name]:
            raise ValueError(f"DT output pin mismatch: {name}")
        validate_profile(files[name], name.removeprefix("maxion-").removesuffix(".dtb"))
    archive = files["dts-sources.tar.gz"]
    verify_archive(archive, sources)
    receipt = receipt_for(sources, pins, files, archive)
    if files["dts-build-receipt.json"] != json_bytes(receipt):
        raise ValueError("DT receipt differs from independently expected receipt")
    return receipt


def build(out: Path, root: Path = ROOT):
    """Build into NEW out directory; root denotes et/dts, not the repository root."""
    root, out = Path(root).absolute(), Path(out).absolute()
    sources = source_files(root)
    root = root.resolve()
    if out.resolve() == root or root in out.resolve().parents:
        raise ValueError("output must be outside DT source directory")
    if out.exists() or out.is_symlink():
        raise ValueError("DT output directory already exists")
    pins = load_pins(sources)
    check_tools(pins)
    out.mkdir(parents=True, exist_ok=False)
    outputs = {}
    # Snapshot includes/native inputs so concurrent source edits cannot mix builds.
    with tempfile.TemporaryDirectory(prefix="maxion-dts-") as temporary:
        snapshot = Path(temporary)
        for name, data in sources.items():
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        logs = []
        for name in DTBS:
            command = [pins["dtc"]["path"], "-I", "dts", "-O", "dtb", "-o", str(out / name), name.replace(".dtb", ".dts")]
            result = subprocess.run(command, cwd=snapshot, env=safe_environment(),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            logs.append(result.stdout)
            (out / "build.log").write_bytes(b"".join(logs))
            if result.returncode:
                raise ValueError(f"dtc failed for {name}; see {out / 'build.log'}")
            outputs[name] = (out / name).read_bytes()
            if identity(outputs[name]) != pins["outputs"][name]:
                raise ValueError(f"DT output pin mismatch: {name}; retain failed output for investigation")
            validate_profile(outputs[name], name.removeprefix("maxion-").removesuffix(".dtb"))
    if source_files(root) != sources:
        raise ValueError("DT source tree changed during build")
    archive = source_archive(sources)
    receipt = receipt_for(sources, pins, outputs, archive)
    outputs["dts-sources.tar.gz"] = archive
    outputs["dts-build-receipt.json"] = json_bytes(receipt)
    verify_bundle(outputs, root)
    for name, data in outputs.items():
        (out / name).write_bytes(data)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--out", type=Path, help="new output directory (never reused)")
    choice.add_argument("--verify-only", action="store_true", help="verify source references and pinned local dtc; no outputs")
    args = parser.parse_args()
    try:
        if args.verify_only:
            sources = source_files(ROOT)
            check_tools(load_pins(sources))
            validate_profile(sources["reference/maxion-9front-original.dtb"], "9front")
            validate_profile(sources["reference/maxion-linux-public-base.dtb"], "linux")
            print("DT-INPUTS-PASS (not an output build)")
        else:
            build(args.out)
            print(f"PINNED-DT-PASS: {args.out.absolute()}")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"DT build refused: {exc}\n")


if __name__ == "__main__":
    main()
