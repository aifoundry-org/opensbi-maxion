#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline release packaging for the immutable Maxion raw-byte baseline."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("maxion_release_builder", ROOT / "et/build.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

TAG_PATTERN = r"maxion-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
OUTPUTS = ("fw_jump.bin", "fw_jump.elf", "build.log", "fw_jump.readelf.txt")
COPIES = {
    "toolchain.json": "et/toolchain.json",
    "PROVENANCE.json": "et/PROVENANCE.json",
    "COPYING.BSD": "COPYING.BSD",
    "ThirdPartyNotices.md": "ThirdPartyNotices.md",
    "et-platform-LICENSE": "et/licenses/et-platform-LICENSE",
    "et-platform-NOTICE": "et/licenses/et-platform-NOTICE",
}
PAYLOADS = (*OUTPUTS, "build-receipt.json", *COPIES, "RELEASE-NOTES.md")
ASSETS = (*PAYLOADS, "release.json", "SHA256SUMS")


class ReleaseError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def check_tag(tag):
    require(re.fullmatch(TAG_PATTERN, tag) is not None,
            "Invalid downstream tag: expected maxion-vMAJOR.MINOR.PATCH (no leading zeros)")


def read_regular(path):
    require(path.is_file() and not path.is_symlink(), "Missing regular file: " + str(path))
    return path.read_bytes()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def reference_identity():
    return {"sha256": builder.REFERENCE_SHA256, "size": builder.REFERENCE_SIZE}


def notes(tag, commit):
    return f"""# Maxion OpenSBI {tag}

Source commit: `{commit}`

This release preserves the immutable pinned historical raw-byte baseline.
`fw_jump.bin` is byte-for-byte identical to the independent frozen reference:

* SHA-256: `{builder.REFERENCE_SHA256}`
* Size: {builder.REFERENCE_SIZE} bytes

No candidate-blessing or baseline replacement is performed. The symbol-bearing
ELF is diagnostic; debug paths can differ and ELF identity is not the acceptance
target. See build-receipt.json, release.json, toolchain.json and PROVENANCE.json
for source, recipe, pinned toolchain and historical provenance. SHA256SUMS covers
every other release asset (not itself).

This is build-only evidence, not a new hardware boot or hardware qualification
claim, security certification, deployment approval, or OTA/rollback guarantee.
No hardware access, flashing, reset or deployment is performed. Compatible
external kernel/DT and provisioned firmware, exclusive card ownership, and
separate authorization remain necessary.
"""


def validated_build(root, build, tag):
    check_tag(tag)
    env = builder.safe_environment()
    source = builder.verify_source(root, env)
    require(source["support_status"] == "", "Current support tree is dirty")
    tag_commit = builder.run(
        [builder.prerequisite("git"), "rev-parse", "--verify",
         "refs/tags/" + tag + "^{commit}"], root, env).decode().strip()
    require(tag_commit == source["commit"], "Tag does not resolve to current HEAD")

    files = {name: read_regular(build / name) for name in (*OUTPUTS, "build-receipt.json")}
    receipt = json.loads(files["build-receipt.json"])
    require(receipt.get("status") == "BIT-IDENTICAL-PASS", "Receipt is not BIT-IDENTICAL-PASS")
    require(receipt.get("make_exit_status") == 0, "Receipt records an unsuccessful build")
    inputs = receipt["inputs"]
    require(inputs["source"].get("support_status") == "", "Receipt support tree is dirty")
    require(inputs["source"] == source, "Receipt source is stale or differs from current HEAD/tree")
    support = {name: sha(read_regular(root / "et" / name))
               for name in ("build.py", "toolchain.json")}
    require(inputs["support_sha256"] == support, "Receipt support hashes differ from current files")
    require(inputs["reference"] == reference_identity(), "Receipt reference identity differs")
    reference = builder.verify_reference(root / "et/reference/fw_jump.bin")
    candidate = files["fw_jump.bin"]
    require(candidate == reference and len(candidate) == builder.REFERENCE_SIZE
            and sha(candidate) == builder.REFERENCE_SHA256,
            "Candidate differs from immutable raw-byte baseline")
    require(receipt.get("comparison") == {
        **reference_identity(), "byte_comparison": "identical"},
        "Receipt comparison is not the pinned identical baseline")
    require(receipt["output_sha256"] == {name: sha(files[name]) for name in OUTPUTS},
            "Receipt output SHA256 hashes differ (or output set is incomplete)")
    files.update({name: read_regular(root / path) for name, path in COPIES.items()})
    pins = json.loads(files["toolchain.json"])
    actual_tools = inputs["toolchain"]["cross_tools"]
    require(set(actual_tools) == set(pins["cross_tools"]), "Receipt toolchain set differs")
    for name, pin in pins["cross_tools"].items():
        require(all(actual_tools[name].get(key) == pin[key] for key in ("sha256", "version")),
                "Receipt pinned toolchain differs: " + name)
    return source, support, files


def package(root, build, out, tag):
    check_tag(tag)
    # Do not follow a dangling output symlink or reuse any prior evidence.
    require(not out.exists() and not out.is_symlink(), "Output path already exists: " + str(out))
    source, support, files = validated_build(root, build, tag)
    files["RELEASE-NOTES.md"] = notes(tag, source["commit"]).encode()
    manifest = {
        "schema_version": 1,
        "tag": tag,
        "commit": source["commit"],
        "tag_commit": source["commit"],
        "source": source,
        "status": "BIT-IDENTICAL-PASS",
        "reference": reference_identity(),
        "support_sha256": support,
        "receipt_sha256": sha(files["build-receipt.json"]),
        "provenance_sha256": sha(files["PROVENANCE.json"]),
        "assets_sha256": {name: sha(data) for name, data in sorted(files.items())},
    }
    files["release.json"] = json_bytes(manifest)
    files["SHA256SUMS"] = "".join(
        f"{sha(data)}  {name}\n" for name, data in sorted(files.items())).encode()
    out.mkdir()
    for name, data in files.items():
        with (out / name).open("xb") as stream:
            stream.write(data)
    verify_package(out, tag)
    return manifest


def verify_package(assets, tag):
    """Recheck the exact upload set, without invoking build tools or networking."""
    check_tag(tag)
    require(set(path.name for path in assets.iterdir()) == set(ASSETS),
            "Release directory must contain exactly the explicit release assets")
    files = {name: read_regular(assets / name) for name in ASSETS}
    expected = "".join(f"{sha(files[name])}  {name}\n"
                       for name in sorted(set(ASSETS) - {"SHA256SUMS"})).encode()
    require(files["SHA256SUMS"] == expected, "Release SHA256SUMS mismatch")
    manifest = json.loads(files["release.json"])
    require(manifest["tag"] == tag, "Release tag mismatch")
    require(manifest["status"] == "BIT-IDENTICAL-PASS", "Release is not BIT-IDENTICAL-PASS")
    require(re.fullmatch(r"[0-9a-f]{40}", manifest["commit"]) is not None
            and manifest["tag_commit"] == manifest["commit"], "Release commit mismatch")
    require(manifest["reference"] == reference_identity(), "Release reference mismatch")
    require(manifest["assets_sha256"] == {name: sha(files[name]) for name in PAYLOADS},
            "Release manifest asset hashes mismatch")
    require(sha(files["fw_jump.bin"]) == builder.REFERENCE_SHA256
            and len(files["fw_jump.bin"]) == builder.REFERENCE_SIZE,
            "Release raw binary mismatch")
    return manifest


def verify_checkout(assets, tag, root):
    """Bind downloaded assets to this exact, clean tagged checkout."""
    manifest = verify_package(assets, tag)
    source, support, expected_files = validated_build(root, assets, tag)
    require(manifest["source"] == source and manifest["commit"] == source["commit"],
            "Release manifest source differs from current checkout")
    require(manifest["support_sha256"] == support, "Release manifest support hashes differ")
    require(manifest["receipt_sha256"] == sha(expected_files["build-receipt.json"]),
            "Release receipt provenance hash differs")
    require(manifest["provenance_sha256"] == sha(expected_files["PROVENANCE.json"]),
            "Release historical provenance hash differs")
    for name in COPIES:
        require(read_regular(assets / name) == expected_files[name],
                "Release copied asset differs from current checkout: " + name)
    require(read_regular(assets / "RELEASE-NOTES.md") == notes(tag, source["commit"]).encode(),
            "Release notes differ from pinned baseline notes")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("package", help="validate a current tagged build and create NEWDIR")
    pack.add_argument("--build", type=Path, required=True)
    pack.add_argument("--out", type=Path, required=True)
    pack.add_argument("--tag", required=True)
    verify = commands.add_parser("verify", help="verify upload assets against this clean tagged checkout")
    verify.add_argument("--assets", type=Path, required=True)
    verify.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    if args.command == "package":
        manifest = package(ROOT, args.build, args.out, args.tag)
        print(f"RELEASE-PACKAGE-PASS: {manifest['tag']} {manifest['commit']} -> {args.out}")
    else:
        verify_checkout(args.assets, args.tag, ROOT)
        print("RELEASE-ASSETS-PASS: " + args.tag)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ReleaseError, builder.BuildError, OSError, ValueError, KeyError, TypeError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
