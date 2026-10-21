#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline, fresh-source build with mandatory independent historical comparison."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

SOURCE_TREE = "765649af8f071b5981e3c186d35ab6da709af47a"
UPSTREAM_COMMIT = "6ad246a1494807ee91e36ffcf60e4c30bb309d45"
REFERENCE_SHA256 = "97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18"
REFERENCE_SIZE = 279048
EPOCH = "1790598985"
SAFE_PATH = "/usr/bin:/bin"
CROSS = "/usr/bin/riscv64-linux-gnu-"
MAWK = "/usr/bin/mawk"
HOST_TOOLS = (
    "make", "git", "python3", "sh", "bash", "sed", "grep",
    "head", "readlink", "dirname", "basename", "mkdir", "rm", "cat",
    "uname", "tr", "od", "cp", "ln",
)
SETTINGS = (
    "PLATFORM=generic", "CROSS_COMPILE=" + CROSS,
    "PLATFORM_RISCV_XLEN=64", "PLATFORM_RISCV_ISA=rv64imac_zicsr_zifencei",
    "PLATFORM_RISCV_ABI=lp64", "FW_TEXT_START=0x8004200000",
    "FW_DYNAMIC=n", "FW_JUMP=y", "FW_PAYLOAD=n",
    "FW_JUMP_ADDR=0x8600200000", "FW_JUMP_FDT_OFFSET=0x2200000",
    "BUILD_INFO=n", "OPENSBI_VERSION_GIT=",
)


class BuildError(Exception):
    pass


def safe_environment(home="/"):
    # Deliberately do NOT copy os.environ: no MAKEFLAGS, CPATH, GCC_EXEC_PREFIX,
    # LD_PRELOAD, FW_*, KCONFIG_*, PYTHONPATH, BASH_ENV, or git overrides.
    return {"PATH": SAFE_PATH, "HOME": str(home), "LC_ALL": "C", "TZ": "UTC",
            "SOURCE_DATE_EPOCH": EPOCH, "PYTHONNOUSERSITE": "1"}


def safe_path(value):
    text = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_./+-]+", text):
        raise BuildError("Paths must contain only letters, digits, _ . / + - "
                         "(no whitespace or shell/Make metacharacters): " + text)
    return value


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if (
            sys.version_info >= (3, 11)
        ) else digest_stream(stream)


def digest_stream(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def run(command, cwd, env, *, data=None):
    result = subprocess.run(command, cwd=cwd, env=env, input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise BuildError(f"Command failed ({result.returncode}): "
                         f"{shlex.join(map(str, command))}\n"
                         + result.stderr.decode(errors="replace"))
    return result.stdout


def prerequisite(name):
    path = shutil.which(name, path=SAFE_PATH)
    if not path:
        raise BuildError("Missing prerequisite: " + name
                         + ". See et/toolchain.json and et/README.md; "
                         "this script never installs or downloads tools.")
    return str(safe_path(Path(path).absolute()))


def filtered_root_tree(entries):
    """Hash the canonical Git tree after removing only the root et entry.

    Unlike git mktree this does not write an object into the source repository.
    """
    body = bytearray()
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, kind, oid = meta.split(b" ")
        if name == b"et":
            continue
        if kind not in (b"blob", b"tree"):
            raise BuildError("Unexpected submodule/source entry")
        body.extend(mode.lstrip(b"0") + b" " + name + b"\0"
                    + bytes.fromhex(oid.decode()))
    return hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).hexdigest()


def verify_source(root, env):
    git = prerequisite("git")

    def query(*args):
        return run([git, "-c", "core.fsmonitor=false", *args], root, env)

    commit = query("rev-parse", "--verify", "HEAD").decode().strip()
    tree = query("rev-parse", "HEAD^{tree}").decode().strip()
    actual = filtered_root_tree(query("ls-tree", "-z", commit))
    if actual != SOURCE_TREE:
        raise BuildError(f"Committed source fingerprint mismatch: {actual}; "
                         f"expected {SOURCE_TREE} (root excluding et/)")
    # Against HEAD catches staged AND unstaged edits, deletions and renames.
    changed = query("diff", "--name-only", "-z", "HEAD", "--", ".",
                    ":(top,exclude)et").split(b"\0")
    if any(changed):
        raise BuildError("Dirty tracked source outside et/: "
                         + repr([p.decode(errors="replace") for p in changed if p]))
    return {"commit": commit, "full_tree": tree,
            "source_tree_excluding_et": actual,
            "upstream_commit": UPSTREAM_COMMIT,
            "support_status": query("status", "--porcelain=v1",
                                    "--untracked-files=all", "--", "et").decode()}


def verify_reference(path):
    if not path.is_file() or path.is_symlink():
        raise BuildError("Missing independent regular reference: " + str(path))
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if len(data) != REFERENCE_SIZE or actual != REFERENCE_SHA256:
        raise BuildError(f"Independent reference INVALID: {actual}, {len(data)} bytes; "
                         f"required {REFERENCE_SHA256}, {REFERENCE_SIZE} bytes. "
                         "Do not replace it with a new candidate.")
    return data


def tool_record(path, cwd, env, version_args=("--version",)):
    resolved = Path(path).resolve(strict=True)
    safe_path(resolved)
    version = run([str(path), *version_args], cwd, env).decode(errors="replace")
    return {"path": str(path), "resolved_path": str(resolved),
            "sha256": digest(resolved), "version": version}


def package_inventory(packages, cwd, env):
    """Informational only: package names are not executable prerequisites."""
    dpkg = shutil.which("dpkg-query", path=SAFE_PATH)
    report = {"command": None, "exit_status": None, "stdout": "", "stderr": ""}
    if not dpkg:
        report["warning"] = ("dpkg-query unavailable; package inventory omitted. "
                             "Mandatory executable/version checks are unchanged.")
    else:
        command = [dpkg, "-W", "-f=${binary:Package}\\t${Version}\\n", *packages]
        report["command"] = command
        try:
            result = subprocess.run(command, cwd=cwd, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            report.update(exit_status=result.returncode,
                          stdout=result.stdout.decode(errors="replace"),
                          stderr=result.stderr.decode(errors="replace"))
            if result.returncode:
                report["warning"] = ("Package inventory incomplete or unavailable; "
                                     "see captured dpkg-query output. "
                                     "Mandatory executable/version checks are unchanged.")
        except OSError as error:
            report["stderr"] = str(error)
            report["warning"] = ("Could not execute dpkg-query; package inventory "
                                 "omitted. Mandatory executable/version checks "
                                 "are unchanged.")
    if "warning" in report:
        print("WARNING: " + report["warning"], file=sys.stderr)
    return report


def verify_toolchain(here, env):
    pins = json.loads((here / "toolchain.json").read_text())
    tools = {}
    for name in ("gcc", "ld", "ar", "objcopy", "readelf", "as"):
        tools[name] = prerequisite(CROSS + name)
    # GCC's internally chosen executables matter as much as its driver.
    for name in ("cc1", "as", "ld", "collect2"):
        path = run([tools["gcc"], "-print-prog-name=" + name], here, env).decode().strip()
        tools["gcc_selected_" + name] = prerequisite(path)
    records = {}
    for name, path in tools.items():
        records[name] = tool_record(path, here, env)
        expected = pins["cross_tools"][name]
        if records[name]["sha256"] != expected["sha256"]:
            raise BuildError(f"Toolchain fingerprint mismatch for {name}: "
                             f"{records[name]['sha256']}; expected {expected['sha256']}. "
                             "Use the pinned packages in et/toolchain.json.")
        if records[name]["version"] != expected["version"]:
            raise BuildError("Toolchain version mismatch for " + name)
    # carray.sh iterates associative arrays. GNU awk and mawk produce different
    # relocation ordering even with identical GCC/binutils and source inputs.
    mawk = tool_record(prerequisite(MAWK), here, env, ("-W", "version"))
    expected = pins["codegen_tools"]["mawk"]
    if any(mawk[key] != expected[key] for key in ("sha256", "version")):
        raise BuildError("Code-generation tool fingerprint/version mismatch for mawk")
    host = {}
    for name in HOST_TOOLS:
        path = prerequisite(name)
        # dash (sh) and a few small tools lack --version; record full package
        # versions separately and fingerprint every executable regardless.
        host[name] = {"path": path, "resolved_path": str(Path(path).resolve()),
                      "sha256": digest(path)}
    for name in ("make", "git", "python3", "bash"):
        host[name]["version"] = run([host[name]["path"], "--version"],
                                   here, env).decode(errors="replace")
    package_report = package_inventory(pins["packages"].keys(), here, env)
    return {"cross_tools": records, "codegen_tools": {"mawk": mawk},
            "host_tools": host, "packages": package_report}


def build_environment(out):
    """Select pinned awk privately; do not change host alternatives or source."""
    tools = out / "host-tools"
    tools.mkdir()
    (tools / "awk").symlink_to(MAWK)
    env = safe_environment(out / "home")
    env["TMPDIR"] = str(out / "tmp")
    env["PATH"] = str(tools) + ":" + SAFE_PATH
    return env


def new_output(here, requested):
    if requested:
        out = Path(requested).absolute()
        safe_path(out)
        # mkdir without exist_ok refuses directories, files, dangling symlinks.
        out.mkdir()
    else:
        base = here / "build"
        base.mkdir(exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    return safe_path(out.resolve())


def extract_source(archive, target):
    target.mkdir()
    with tarfile.open(archive, "r:") as source:
        members = source.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts
                    or not (member.isfile() or member.isdir())):
                raise BuildError("Unsafe git archive member: " + member.name)
        source.extractall(target, members=members)


def compare_candidate(candidate, reference):
    data = candidate.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if (len(data) != REFERENCE_SIZE or actual != REFERENCE_SHA256
            or data != reference):
        raise BuildError(f"BIT-IDENTICAL-FAIL: candidate {actual}, {len(data)} bytes; "
                         f"required {REFERENCE_SHA256}, {REFERENCE_SIZE} bytes. "
                         "All outputs retained; no candidate-blessing override exists.")
    return {"sha256": actual, "size": len(data), "byte_comparison": "identical"}


def build(root, here, out, env, inputs, reference, jobs):
    receipt = {"status": "INCOMPLETE", "inputs": inputs, "environment": env,
               "settings": list(SETTINGS), "output_directory": str(out)}
    receipt_path = out / "build-receipt.json"

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    save()
    try:
        archive = out / "source.tar"
        with archive.open("xb") as stream:
            result = subprocess.run(
                [prerequisite("git"), "archive", "--format=tar",
                 inputs["source"]["commit"]], cwd=root, env=env,
                stdout=stream, stderr=subprocess.PIPE)
        if result.returncode:
            raise BuildError("git archive failed: " + result.stderr.decode(errors="replace"))
        receipt["archive_sha256"] = digest(archive)
        src = out / "source"
        extract_source(archive, src)
        # et/ is support/evidence, not firmware source; archive includes committed
        # et/ provenance but never consumes it as a replacement source or patch.
        command = [prerequisite("make"), "-C", str(src), "O=" + str(out / "objects"),
                   *SETTINGS, "-j" + str(jobs)]
        receipt["command"] = command
        receipt["command_shell_display"] = shlex.join(command)
        save()
        with (out / "build.log").open("xb") as log:
            result = subprocess.run(command, cwd=out, env=env, stdout=log,
                                    stderr=subprocess.STDOUT)
        receipt["make_exit_status"] = result.returncode
        if result.returncode:
            raise BuildError(f"make failed with exit {result.returncode}; see {out / 'build.log'}")
        firmware = out / "objects/platform/generic/firmware"
        for name in ("fw_jump.bin", "fw_jump.elf"):
            shutil.copyfile(firmware / name, out / name)
        headers = run([CROSS + "readelf", "-h", "-l", str(out / "fw_jump.elf")],
                      out, env)
        (out / "fw_jump.readelf.txt").write_bytes(headers)
        # Record actual resolved Kconfig and generated build inputs, not just flags.
        receipt["configuration_files"] = {
            str(p.relative_to(out)): digest(p)
            for p in sorted((out / "objects").rglob("*"))
            if p.is_file() and (p.name in (".config", "auto.conf", "autoconf.h")
                                or p.suffix == ".ld")
        }
        receipt["output_sha256"] = {
            name: digest(out / name) for name in
            ("fw_jump.bin", "fw_jump.elf", "fw_jump.readelf.txt", "build.log")
        }
        (out / "OUTPUT-SHA256SUMS").write_text("".join(
            f"{value}  {name}\n" for name, value in receipt["output_sha256"].items()))
        receipt["comparison"] = compare_candidate(out / "fw_jump.bin", reference)
        receipt["status"] = "BIT-IDENTICAL-PASS"
        save()
        print(f"BIT-IDENTICAL-PASS: {REFERENCE_SHA256} ({REFERENCE_SIZE} bytes)")
        print(f"Firmware (NOT deployed): {out / 'fw_jump.bin'}")
        print(f"Receipt: {receipt_path}")
    except BaseException as error:
        receipt["status"] = "FAIL"
        receipt["error"] = str(error)
        save()
        print(f"Failed build retained: {out}", file=sys.stderr)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", metavar="NEW_DIRECTORY",
                        help="nonexisting output directory; default et/build/run-*")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--verify-only", action="store_true",
                        help="check inputs/toolchain, do not build (not a binary PASS)")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.verify_only and args.out:
        parser.error("--verify-only does not accept --out")
    if sys.version_info < (3, 10):
        raise BuildError("Python 3.10 or newer is required")
    here = safe_path(Path(__file__).resolve().parent)
    root = safe_path(here.parent)
    env = safe_environment()
    inputs = {"source": verify_source(root, env),
              "reference": {"sha256": REFERENCE_SHA256, "size": REFERENCE_SIZE},
              "support_sha256": {name: digest(here / name)
                                 for name in ("build.py", "toolchain.json")}}
    reference = verify_reference(here / "reference/fw_jump.bin")
    inputs["toolchain"] = verify_toolchain(here, env)
    if args.verify_only:
        print("INPUTS-VERIFIED (no build, NOT BIT-IDENTICAL-PASS)")
        print(json.dumps(inputs, indent=2, sort_keys=True))
        return 0
    out = new_output(here, args.out)
    (out / "home").mkdir()
    (out / "tmp").mkdir()
    env = build_environment(out)
    build(root, here, out, env, inputs, reference, args.jobs)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BuildError, OSError, ValueError, tarfile.TarError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print("::error title=OpenSBI build failed::" + message)
        sys.exit(1)
