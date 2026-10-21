# Linux and 9front use the same OpenSBI binary

Checked October 21, 2026, using saved Shelley conversations and local artifacts.
**The canonical RAM-loaded `fw_jump.bin` is byte-for-byte identical for the
historical Linux boot, the saved 9front package, and this standalone rebuild.**
This is an actual full-file comparison, not an inference from matching names,
OpenSBI banners, source versions or build settings.

All four compared files contain **279,048 bytes**, with SHA-256:

```text
97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18
```

## Evidence chain

Historical paths below are relative to `/var/lib/shelley/work/`. They identify
saved evidence on the research host, not dependencies of this repository.

1. **Linux artifact:** `mx-packet/baseline/opensbi/fw_jump.bin`.
   Its saved `baseline/manifest.json` identifies its source as
   `/tmp/mx/repro/out/fw_jump.bin`, with this exact size and SHA-256.
   The Linux investigation conversation
   `c5UASUD` (`maxion-cores-opensbi-uart-investigation`), sequence 1553,
   records the source hash; sequence 2439 records the same hash for the
   staged remote `/root/mx/fw_jump.bin`.
2. **Linux boot evidence:** the saved
   `mx-packet/user-link-20261010.KKSuih/boot-artifacts.sha256` independently
   records that same OpenSBI input hash. The accompanying
   `boot-a/guest-boot-console.log` records Linux
   `6.12.112-etsoc1-maxion`, execution of `/init`, and a BusyBox shell.
   In `c5UASUD`, sequences 3275–3280 select that file as
   `APPROVED_FW_JUMP`, verify its hash, and record a successful fresh Linux
   launch on **October 11, 2026 at 05:02 UTC** (October 10 Pacific).
   Sequence 3288 then records 12/12 ping replies and the running-session
   handoff. This ties the matching artifact to an actual successful boot,
   rather than merely to a staged but unused file.
3. **Transfer to 9front:** conversation `cYJOINM`
   (`rebuild-9front-plan9-kernel`), sequences 267, 271 and 273, records the
   original `/tmp/mx/repro/out/fw_jump.bin`, the 9front package, and its
   remote staging copy with the same hash. The saved
   `9front-riscv64-lab/evidence/maxion/artifacts.sha256` agrees.
4. **Direct comparison now:** the Linux baseline binary, the saved
   `9front-riscv64-lab/work/maxion/package/fw_jump.bin`, this repository's
   `et/reference/fw_jump.bin`, and
   `et/build/final-branch-check/fw_jump.bin` all compare equal in their
   entirety. The last file was freshly built from commit
   `483e3fd677bf1f66012b43abdf58c225dd6d8571`; see the standalone
   [validation](../VALIDATION.md) for the build controls and earlier
   independent clean-clone reproductions.

## What is and is not identical

There is no Plan-9-specific OpenSBI firmware change here. The OS kernel and
external device tree differ; Linux also has its separate initramfs. This
`FW_JUMP` image embeds none of those OS payloads.

The comparison concerns the raw firmware actually RAM-loaded for Linux and
9front. It does **not** equate every early experimental OpenSBI build, the
flash-resident hello/`fw_payload` image, or a complete SPI image with this
binary. Debug-path-dependent ELF files are not the equality target.

This check read saved files and conversation records only. No new hardware
boot, UART access, deployment, reset or live-state verification was performed.
