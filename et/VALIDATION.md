# Validation of the standalone Maxion branch

Validation date: **October 21, 2026 UTC**. All work here is software-only:
no firmware was deployed, no card/UART was opened, and no device was reset.

## Acceptance target

The reference was copied from the pre-existing hardware-tested package, before
the standalone build:

- Raw file: `fw_jump.bin`
- Size: **279,048 bytes**
- SHA-256: **`97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18`**

The comparison is against all bytes of that preserved file in addition to its
fixed size and SHA-256. A successful `make` alone is not acceptance. The ELF
is inspected and hashed, but is not claimed bit-identical across debug paths.

## Development validation

The instructions in `et/README.md` were run with the documented, preinstalled
Ubuntu 22.04 x86-64 GCC 11.4.0 / binutils 2.38 toolchain. An initial fresh-output
build and the explicit `--out .../reproduce-1 --jobs 2` build both printed
`BIT-IDENTICAL-PASS`; external `cmp` and `sha256sum` agreed.
Each built from a fresh archive of the committed fork source, not a vendor
archive, prebuilt output or reused object directory.

The tooling's **18 offline unit controls** cover source tree/dirty-input
checks, independent reference corruption, mandatory whole-byte comparison,
toolchain mismatch, stale output/path/archive refusal, cleared subprocess
environment, missing prerequisites, informational package-inventory failures,
and failed-build/mismatched-binary output retention. These are not hardware
tests and do not replace actual compilation.

## Independent clean-clone reproduction — PASS

A separate reviewer made an actual `git clone --no-local --single-branch -b et`
of commit `6a53a4f77687e5f0d33e4768eb17f43bcf0fa5d1` at a different path.
The clone had no alternates, retained the upstream history, and stayed clean.
All section 3 commands from `et/README.md` were executed, including:

- All 31 shipped support-file checksum entries verified.
- Source, independent reference and strict toolchain preflight passed.
- All 18 unit tests passed.
- A fresh two-job build passed; external `cmp` and `sha256sum` confirmed the
  exact canonical raw firmware.
- A second fresh one-job build with deliberately invalid inherited
  `MAKEFLAGS`, `CFLAGS`, `FW_TEXT_START`, `FW_FDT_PATH` and `GCC_EXEC_PREFIX`
  also produced exactly the same raw firmware.
- Both outputs matched the frozen reference and each other byte-for-byte:
  **279,048 bytes, SHA-256
  `97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18`.**

Each log shows 202 compilation, six assembly and two archive stages, plus ELF
linking and binary extraction. Each used a separate source archive and empty
object tree; no prebuilt output or reference was substituted for compilation.
Output and log hashes in both receipts were independently rechecked.

Full command/exit records, receipts, resolved configurations, logs and the
reviewer's original report are retained in `et/validation/clean-clone/`.
That report retains its original ignored-directory locations from the time
of testing; the evidence was subsequently copied unchanged here.

This was a real relocated **local-transport** Git clone, not a claim that
GitHub write authentication or publication succeeded. The exact tool packages
were preinstalled: apt provisioning, availability on future package mirrors,
and a stripped-host minimum-package test were not exercised.

Historical tests from the earlier archive recipe are separately labeled under
`et/history/` and are not presented as this fork's new test runs.

## Reproducibility boundary

The raw binary match is measured with the recorded toolchain, not promised for
arbitrary compilers or OS versions. The builder refuses differing cross-tool
fingerprints. Host package/tool inventory, generated configuration/linker
hashes, source identity, exact command, output hashes and comparison outcome
are recorded in each build receipt. The toolchain/host OS is not bundled and
is not a cryptographically attested or fully hermetic environment.

The unchanged firmware bytes preserve the historical configuration; they do
not qualify a new board layout, generic OpenSBI platform, OTA coexistence,
coherent DMA, SMP OS, security isolation or unattended recovery.
