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

Clean-clone reproduction records are retained under `et/validation/` when
completed. Historical tests from the earlier archive recipe are separately
labeled under `et/history/` and are not presented as this fork's new test runs.

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
