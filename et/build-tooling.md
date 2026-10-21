# Build-tooling contract

`python3 et/build.py` builds only local files. It never fetches dependencies,
installs packages, accesses hardware, flashes, resets, or launches firmware.
Python 3.10+ and the preinstalled tools in `toolchain.json` are required.
Use `--help` for options. No inherited build variables are accepted: use
`--jobs N` to change parallelism, not `JOBS` or `MAKEFLAGS`.

The mandatory cross-toolchain pins are executable SHA-256 **and complete version
output**, including GCC-selected `cc1`, assembler, linker and `collect2`.
`toolchain.json` records the exact installed Ubuntu package versions, including
GCC 11.4 and binutils 2.38. Package versions explain acquisition/provenance;
the baseline list is not a requirement to install every listed package.
Package inventory is best-effort: missing `dpkg-query`, missing packages or an
inventory-command failure produce a warning and are recorded, not a failed build.
The receipt retains its stdout, stderr and exit status when available.
Executable hashes are the enforced cross-toolchain gate. Host tools, Python and
make are fingerprinted/reported in each receipt; host binaries need not match
the original machine. This is not a fully hermetic operating-system image:
shared libraries, kernel and Python standard library remain host dependencies.
There is no tested container workflow and the builder never uses Docker.

The script captures `HEAD` and its full tree, reconstructs the root Git tree hash
with only `et/` removed, and demands
`e1b04052bd6a5093d5abf9e1279f168974899f7d` (including the release workflow; firmware sources unchanged). Dirty tracked files outside `et/`
(staged or unstaged) fail. Untracked source-side files cannot enter the build:
only a fresh `git archive` of the captured commit is extracted. No vendor tarball
or patch reapplication is involved. The archive includes committed `et/` support
evidence but builds the actual root fork source. Output always starts in a new
directory; an existing `--out` destination, including symlinks, is refused.

`et/` support edits are allowed during development. The receipt records their
Git status and hashes the actual builder and toolchain manifest. The independent
reference is read from the working tree, with its size and hash pinned in code.
For a release reproduction, run from a clean committed checkout so the commit
identifies all support files as well. The firmware source itself is never edited.

Every build subprocess receives a new explicit environment, not an augmented
copy of the caller's environment. PATH is `/usr/bin:/bin`; build HOME and TMPDIR
are private. Locale, timezone, source epoch, ISA, ABI, firmware addresses, version
suffix and build-info settings are fixed. Paths with whitespace or shell/Make
metacharacters are rejected because the upstream Makefiles cannot handle them.

A normal build exits zero only after `BIT-IDENTICAL-PASS`: SHA-256, size and a
complete byte comparison against the independently pinned reference all pass.
There is no skip-verification, alternate-reference or bless-candidate option.
The explicit `--verify-only` mode exits zero after input checks only and labels
its result `INPUTS-VERIFIED`, **not** a firmware pass. `--help` also builds nothing.

Each output directory retains `source.tar`, extracted source, fresh objects,
`build.log`, `fw_jump.bin`, `fw_jump.elf`, `fw_jump.readelf.txt`,
`OUTPUT-SHA256SUMS`, and `build-receipt.json`. The receipt includes actual tools,
source commit/tree, support status/hashes, source archive hash, command,
environment, generated configuration/linker-script hashes, output/log hashes,
make status and comparison outcome. Build failure or binary mismatch is nonzero,
with the failed output and receipt preserved. Preflight failures create no output
directory. Receipts describe local evidence, not cryptographic attestations or
hardware qualification.

Fast offline controls:

```sh
python3 -m unittest discover -s et/tests -p 'test_*.py' -v
```

They test dirty/changed source, reference corruption, one-byte candidate changes,
mandatory byte comparison, toolchain corruption, hostile inherited environment,
stale-output refusal, path rejection, unsafe archives, missing tools, and failed
make status/log retention. They do not compile firmware or exercise hardware.
