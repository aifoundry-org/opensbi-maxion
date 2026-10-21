# Independent relocated README validation — PASS

Date: 2026-10-21 UTC, commands 17:24:00–17:24:18.
Source: /var/lib/shelley/work/opensbi-maxion, branch et,
commit 6a53a4f77687e5f0d33e4768eb17f43bcf0fa5d1.
Actual clone: `git clone --no-local --single-branch -b et /var/lib/shelley/work/opensbi-maxion /tmp/opensbi-maxion-readme-check`.
No alternates; single-branch origin refspec verified. Both original and clone
had empty `git status --porcelain=v1 --untracked-files=all` before and after.
Upstream 6ad246a1494807ee91e36ffcf60e4c30bb309d45 remains an ancestor.
Both production patch diffs equal archival patch contents (excluding leading
comments; git index abbreviations normalized for display only).

## Actual executed checks

All exact section 3 commands in et/README.md ran from relocated clone root,
in order, with command lines and explicit exit statuses in commands.log:

- `sha256sum -c et/SHA256SUMS`: 31/31 OK, also repeated after both builds.
- `python3 et/build.py --verify-only`: INPUTS-VERIFIED, exit 0.
- Unit discovery: Ran 18 tests, OK (exit 0). Negative-control warning/failure
  messages in the successful test log are expected test fixture outcomes.
- Fresh `et/build/reproduce-1`, jobs 2: make exit 0, BIT-IDENTICAL-PASS.
- Fresh `et/build/reproduce-2-poisoned`, jobs 1: make exit 0, BIT-IDENTICAL-PASS,
  despite MAKEFLAGS=--definitely-invalid-make-option,
  CFLAGS=-this-flag-must-not-reach-gcc, FW_TEXT_START=0xBAD,
  FW_FDT_PATH=/nonexistent/poisoned.dtb,
  GCC_EXEC_PREFIX=/nonexistent/poisoned-gcc/.
- External cmp(reference, first), cmp(reference, second), cmp(first, second):
  all silent, exit 0. Objects-tree binaries also equal each copied final binary.
- BOTH outputs: 279048 bytes;
  SHA-256 97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18.

Each build used a new source archive, extracted source and object tree. Each
actual build.log shows 202 CC, 6 AS, 2 AR, 1 ELF and 1 OBJCOPY stages.
No prebuilt candidate or reference was substituted for compilation. All four
output/log hashes in each receipt were independently rechecked. Receipts show
none of the poisoned keys in the subprocess environment. ELF entry: 0x8004200000.
Raw firmware is the equality target, not debug-path-dependent ELF.

## Prerequisites and README assessment

No build-recipe errors or unmet source/tool prerequisites observed on this host:
Ubuntu 22.04.4 LTS x86-64; Python 3.10.12; GNU Make 4.3; Git 2.34.1;
GCC package 11.4.0-1ubuntu1~22.04cross1, selector 4:11.2.0--1ubuntu1,
binutils package 2.38-4ubuntu2.12. All enforced executable hashes/version
outputs passed; actual host tools/package inventory are in both receipts.
The build consumed committed fork sources, no sibling source tree or patch
reapplication. Output paths were new and contained no unsafe metacharacters.

Scope gaps (not claimed tested): remote GitHub clone/authentication/publication;
apt-get installation/package-mirror availability (packages preinstalled; no
package changes authorized); minimum-package/no-target-libc/no-dtc absence tests
on a stripped host; other compilers/distributions/architectures. This validates
the documented standalone recipe on its native reference environment, not a
hermetic image or universal compiler reproducibility claim. VALIDATION.md at
this source commit has development records only; this independent run is saved
under ignored et/build/clean-validation as requested, not et/validation/.

Workspace and field-manual AGENTS/build safety guidance and project runtime
boundary were read. No hardware/UART/card/driver/deployment/network access,
package install, code edit, commit or push was performed. Only this ignored
evidence directory was written in the parent checkout.

## Evidence

commands.log and run-validation.sh: exact commands, UTC timings, exit statuses.
unit-tests.log: actual 18-test result. verify-only.log: actual input inventory.
reproduce-{1,2-poisoned}/: actual build-receipt.json, build.log,
OUTPUT-SHA256SUMS, fw_jump.readelf.txt and resolved.config.
additional-checks.log: patch equality, output hash and compile-stage checks.
Full source archives, objects, binaries and ELF remain in the relocated clone
under /tmp/opensbi-maxion-readme-check/et/build/reproduce-{1,2-poisoned}/.
