#!/bin/bash
set -euo pipefail
E=/var/lib/shelley/work/opensbi-maxion/et/build/clean-validation
exec > >(tee "$E/commands.log") 2>&1
run() {
  local label=$1; shift
  printf '\n[%s] COMMAND: ' "$(date -u +%FT%TZ)"; printf '%q ' "$@"; printf '\n'
  set +e
  "$@" > "$E/$label.log" 2>&1
  local rc=$?
  set -e
  cat "$E/$label.log"
  echo "EXIT_STATUS=$rc"
  test "$rc" = 0
}
echo 'Clone command executed: git clone --no-local --single-branch -b et /var/lib/shelley/work/opensbi-maxion /tmp/opensbi-maxion-readme-check'
pwd
run clone-before git status --porcelain=v1 --untracked-files=all
run source-before git -C /var/lib/shelley/work/opensbi-maxion status --porcelain=v1 --untracked-files=all
run source-head git -C /var/lib/shelley/work/opensbi-maxion rev-parse HEAD
run clone-head git rev-parse HEAD
run history git log --oneline -4
run upstream-ancestor git merge-base --is-ancestor 6ad246a1494807ee91e36ffcf60e4c30bb309d45 HEAD
run clone-config git config --get remote.origin.fetch
run no-alternates test ! -e .git/objects/info/alternates
run os cat /etc/os-release
run packages dpkg-query -W '-f=${binary:Package}\t${Version}\n' gcc-riscv64-linux-gnu gcc-11-riscv64-linux-gnu binutils-riscv64-linux-gnu
run sha-manifest sha256sum -c et/SHA256SUMS
run verify-only python3 et/build.py --verify-only
run unit-tests python3 -m unittest discover -s et/tests -p 'test_*.py' -v
run mkdir mkdir -p et/build
run build-1 python3 et/build.py --out "$PWD/et/build/reproduce-1" --jobs 2
run cmp-1 cmp et/reference/fw_jump.bin et/build/reproduce-1/fw_jump.bin
run sha-1 sha256sum et/build/reproduce-1/fw_jump.bin
run bytes-1 stat -c '%s %n' et/build/reproduce-1/fw_jump.bin
run build-2-poisoned env MAKEFLAGS='--definitely-invalid-make-option' CFLAGS='-this-flag-must-not-reach-gcc' FW_TEXT_START=0xBAD FW_FDT_PATH=/nonexistent/poisoned.dtb GCC_EXEC_PREFIX=/nonexistent/poisoned-gcc/ python3 et/build.py --out "$PWD/et/build/reproduce-2-poisoned" --jobs 1
run cmp-2 cmp et/reference/fw_jump.bin et/build/reproduce-2-poisoned/fw_jump.bin
run cmp-builds cmp et/build/reproduce-1/fw_jump.bin et/build/reproduce-2-poisoned/fw_jump.bin
run sha-2 sha256sum et/build/reproduce-2-poisoned/fw_jump.bin
run bytes-2 stat -c '%s %n' et/build/reproduce-2-poisoned/fw_jump.bin
run sha-manifest-after sha256sum -c et/SHA256SUMS
run clone-after git status --porcelain=v1 --untracked-files=all
run source-after git -C /var/lib/shelley/work/opensbi-maxion status --porcelain=v1 --untracked-files=all
echo "COMPLETE $(date -u +%FT%TZ)"
