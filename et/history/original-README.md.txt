# OpenSBI for the ET-SoC-1 Maxion cores

Works on the PCIe dev card since 2026-10-06 (OpenSBI v1.9, all four harts, console on PU
UART1 = ttyUSB3, host-staged reboots through `DM_CMD_MAXION_CTL`). The whole story, the
measured facts and the recipe are in `device-bootloaders/doc/Maxion/MaxionBringup.md`.
Phase D Linux (one/four CPUs, Sv39, interrupt-driven UART1) is documented in
`../linux/README.md`, including the exclusive-memory requirement.

* `etsoc1-maxion.dtsi` - common hardware for the hello and Linux DTs:
  4 Maxion harts (rv64imafdc, priv 1.11, Sv39 tested), CLINT @0x0200_0000
  (`timebase-frequency = <9330000>`, a nominal integer rate consistent with
  independent host-clock measurements and corrected sleeps on October 10, 2026;
  historical 3733333 made Linux time approximately 2.5x fast; see
  [`ClockValidation.md`](../../../doc/Maxion/ClockValidation.md) for bounds and
  limits, not an exact all-chip frequency), PU PLIC @0x1000_0000
  (register contexts 0..7 = S0,M0,S1,M1,S2,M2,S3,M3), PU UART1 @0x1200_7000
  (`current-speed = <0>` keeps the SP's fractional divisor).
* `etsoc1-maxion.dts` - hello DT: common hardware plus 2 MiB of DRAM at
  0x80_0420_0000 (inside the SP DM scratch region, unused by the ET stack except during a
  firmware update; host BAR0 + 0x1FF000).
* `payload_hello.S` - tiny S-mode payload that prints through the SBI console (legacy
  putchar + DBCN), then starts the other harts one by one with SBI HSM `hart_start` (each
  prints its hartid) and parks. Built with `.option nopic`: a PIC `la` becomes a GOT load
  of a link-time address (first attempt printed 36 NULs).
* `opensbi-etsoc1-plic-keep-priorities.patch` - REQUIRED (build-opensbi.sh applies it):
  the PU PLIC is shared with the SP and the Master Minion; OpenSBI's cold init zeroes all
  source priorities unless the PLIC node has `esperanto,keep-priorities`.
* `opensbi-etsoc1-mtval-sign-extension.patch` - required for the Linux path:
  repairs RTLMAX-617 fault-address sign extension for the Maxion vendor/arch ID,
  including OpenSBI's misaligned-access emulation.
* `build-opensbi.sh [opensbi-src] [out-dir]` - applies the required patches if needed,
  preprocesses the DT with cpp, and builds the payload and OpenSBI
  `fw_payload` for `FW_TEXT_START=0x8004200000` (payload at +0x80000, FDT copied to
  +0x100000). Needs a cross compiler whose linker supports PIE (`gcc-riscv64-linux-gnu`
  from Ubuntu is fine; the /opt/et bare-metal toolchain is not) and `dtc`. Also
  produces **`fw_jump.bin`**: same firmware load address,
  `FW_JUMP_ADDR=0x8600200000` (Linux Image), no embedded DTB. The boot stub supplies
  the external Linux DTB in `a1`. The generic default `FW_JUMP_FDT_OFFSET=0x2200000`
  relocates it to `0x8006400000` before the Linux handoff (see the recorded
  `Domain0 Next Arg1` in `doc/Maxion/LinuxBootWalkthrough.md`). Tested source:
  `6ad246a1494807ee91e36ffcf60e4c30bb309d45`; use a dedicated source copy because
  the build applies patches to it.
* `opensbi-etsoc1-progress-markers.patch` - optional bring-up aid: stores progress
  markers (fw_base.S, init_coldboot, hart_detect_features, uart8250) and the number of the
  last CSR probed with trap-and-skip into the Maxion->SP mailbox (+0xF0/+0xF4), and makes
  `_start_hang` record mcause/mepc/mtval there. SP BL2 prints them
  ("MAXION: next stage marker=0x.. csr=0x.."). This is how the debug-mode hang was located
  (marker 0x57, csr 0x30a = menvcfg: the first CSR that has to trap).

Turning the result into a flash image region and booting it:

    et-dev/bin/et-mkflash --bl2 <ServiceProcessorBL2_linux.elf> --maxion out/fw_payload.elf \
                          --zero-counters -o ~/work/out/flash-maxion.bin
    et-dev/bin/et-ota ~/work/out/flash-maxion.bin ~/work/logs/maxion     # OTA + reset + capture

SP BL2 (linux variant) loads the `MAXION_BL1` region into DRAM at boot (`Maxion_Boot()`),
the boot stub leaves debug mode and jumps to its entry with a0 = hartid, a1 = 0 (OpenSBI
uses its embedded FDT), and OpenSBI prints on ttyUSB3.  Without reflashing:

    scp out/fw_payload.bin root@<card-host>:/root/
    ssh root@<card-host> et-maxion boot /root/fw_payload.bin --harts 0xf

(`et-dev/host/et-maxion`: stop + L2 evict, stage through BAR0, start, decoded status.)
DTS notes: `/chosen/opensbi-config` makes hart 0 the only cold-boot hart (the stub wakes
the secondaries while hart 0 still prints its banner).
