# Shared Maxion Linux / 9front device trees

Apache-2.0; original Ainekko 2025 notices are preserved. See
`LICENSE.Apache-2.0`, the original et-platform `NOTICE`, `PROVENANCE.json`,
and `COMPARISON.md`. Both license and notice ship in the standalone source archive.

These are **external OS device trees**, not embedded in OpenSBI. The raw
firmware remains the separately pinned `97252e0c…` reference. No hardware,
network, SDK, sibling checkout or target kernel is used by this recipe.

## Build (Python 3.10+, standard library only)

Provision the pinned Ubuntu 22.04 x86-64 `device-tree-compiler=1.6.1-1`
package separately. The builder checks `/usr/bin/dtc` hash, version and actual
`dpkg-query` package version against `toolchain.json`, not merely PATH.
Native dtc `/include/` needs no C preprocessor or include dependency downloads.

From the repository root:

```sh
python3 et/dts/build.py --verify-only
python3 et/dts/build.py --out "$PWD/et/build/dts-new"
python3 -m unittest discover -s et/tests -p test_dts.py -v
```

`--verify-only` checks tools, pinned historical references and the historical
9front/Linux structural contracts; it does **not** claim to build outputs. `--out`
requires a new directory outside `et/dts`, never cleans/reuses an existing one,
and retains failed outputs for investigation. `build.log` is diagnostic only.
The compiler environment is cleared: only fixed PATH, LC_ALL, TZ and
SOURCE_DATE_EPOCH are passed. No ambient DTC/CPP flags or include paths apply.

Release assets (exactly `ASSETS` in `build.py`):

- `maxion-linux.dtb`: public Sv39 Linux base, all four CPUs, default command line.
- `maxion-9front.dtb`: historical Sv48, RAM-root, single-CPU polling bootargs.
- `dts-build-receipt.json`: source SHA-256 inventory, exact recipe/toolchain
  pins, DTB and archive hashes/sizes; no machine paths, timestamps or private data.
- `dts-sources.tar.gz`: self-contained source recipe, license, provenance,
  comparison evidence, tools/output pins, and independent reference snapshots.

The archive uses the explicit `SOURCE_FILES` allowlist. `__pycache__`, `out/`,
build logs and arbitrary ignored/unlisted files are never inventoried or packed.
All listed paths must be regular files without symlink traversal. When adding
an intended source, update this allowlist. Tar entries are sorted `dts/...`,
regular mode 0644, uid/gid/mtime zero, empty owner names, USTAR; gzip has no
filename and mtime zero (via `GzipFile`, including on Python 3.10/3.11).
Builds snapshot source bytes, reject concurrent edits, validate exact structural
contracts and compare outputs with trusted DTB pins. Never refresh a historical
reference to hide a discrepancy.

## Python API and publishing

Load `build.py` with importlib (no package install needed):

- `ASSETS`: tuple of the four asset names above.
- `build(out: Path, root: Path = ROOT) -> dict`: `root` is the **et/dts directory**,
  not the repository root. Builds and returns the deterministic receipt.
- `verify_bundle(files: dict[str, bytes], source_dir: Path) -> dict`: pass exactly
  the four DT assets and a trusted **tagged et/dts directory**. Returns expected
  receipt, or raises `ValueError`. No dtc, dpkg, shell, subprocess, downloads or
  archive extraction are needed. The caller authenticates the tag/source tree.

Verification independently computes the expected source inventory, canonical
uncompressed archive and receipt, checks actual DTB bytes against pins from
that trusted source tree, and validates profile structure. It does not trust a
receipt's self-reported hashes. Gzip header and exact canonical tar bytes
(content, names, ordering, metadata and padding) are checked; the verifier does
not recompress, allowing zlib implementations to encode the identical canonical
tar differently. The receipt binds the actual compressed archive hash. JSON
receipt formatting is canonical and unknown/extra fields are rejected.

## Runtime boundary — not a loader

The common tree describes 1 GiB at `[0x8600000000,0x8640000000)`, four harts,
CLINT, shared PLIC and UART1. This is **inside host-managed allocator memory**;
DT memory declarations do not reserve it. Exclusive ownership and no competing
SDK/OTA/launcher remain external requirements. `esperanto,keep-priorities`
requires compatible patched OpenSBI **and Linux PLIC drivers**. UART1 is shared
with SBI console: never run ttyS0 and hvc0 console readers concurrently.

The Linux artifact is **not plug-and-play with an external initrd**: it has no
`linux,initrd-start/end`, packet/mailbox session, bootstrap seed, tickets,
credentials, private command line or runtime reservation. An authorized loader
must derive a separate final DTB, validate initrd bounds/ownership and any
private properties, and record both published **base DTB hash and final runtime
DTB hash**, derivation/fixups and kernel/initrd identities. Do not overwrite the
published base or claim a patched runtime DTB matches it. A fixup helper and
runtime launch qualification are explicitly outside this iteration.

No new card boot, allocator coexistence, DMA coherency, UART/interrupt driver,
OTA/recovery or all-chip clock qualification is claimed. Historical statements
in imported comments describe their original evidence, not fresh verification.
