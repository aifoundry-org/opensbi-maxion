# Runtime contract and safety

This repository builds firmware; it neither provisions nor deploys a card.
Do not infer authorization to open a UART, access PCI resources, stop a guest,
reload a driver, reset, flash or power-cycle from a successful build.

The historical contract is:

- A compatible ET-SOC1 boot stub leaves debug mode using `dret` on every
  released Maxion hart and supplies the DTB in `a1`.
- Firmware entry/load is `0x8004200000`; the next kernel is staged separately
  at `0x8600200000`, not embedded in `fw_jump`.
- The external DT relocates to `0x8006400000`.
- The runtime DT must set `esperanto,keep-priorities` on the shared PLIC.
  Having the patch in the binary does not activate that opt-in by itself.
- Register contexts are S0,M0,S1,M1,S2,M2,S3,M3; UART1 is source 15. Incorrect
  interrupt probing can steal another agent's pending interrupt.
- The hardware-description examples preserve UART fractional-divider behavior
  and select hart 0 as the only cold-boot hart with an `opensbi,config` node.
- Releasing four harts into OpenSBI is not proof that an OS's SMP mode is
  qualified. The demonstrated 9front port uses one hart and a polling console.

**These addresses are not reserved from the host allocator by this repository.**
OpenSBI at `0x8004200000` overlaps SP OTA scratch beginning at `0x8004001000`.
The relocated DT and OS RAM `[0x8600000000,0x8640000000)` are host-managed.
No concurrent OTA, SDK allocations/DMA or competing launchers are safe merely
because an address is BAR-accessible or appears in a guest device tree.
The high-memory recipe is not validated for arbitrary card capacities.

Actual RAM loading must follow a separately reviewed STOP/cache-evict,
stage/readback, START procedure after all prior guest/host ownership fences.
The host-visible readback is not proof of live Maxion cache coherence.
A failed eviction, uncertain timeout or missing completion is not permission
to retry/reset. Independent recovery and fresh authorization are required.

The diagnostic progress-marker patch performs Maxion mailbox MMIO and needs
reviewed ownership and a compatible SP decoder. It is deliberately unapplied.
Neither the old hello payload nor the old flash-image examples establish a
current recovery procedure. Do not use the archival examples as unattended
deployment instructions.

The trap-value patch is one scoped erratum workaround. It does not resolve
LR/probe, cache-coherence, PMP/PTW, security isolation, OTA survivability or
other hardware qualification issues. No silicon is accessed by the default
builder, unit tests or bit-identical comparison.
