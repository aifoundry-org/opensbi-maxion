# Static comparison evidence (no hardware)

The independent reference files are immutable evidence, not regenerated during
build or tests. Their original paths, observed commits and SHA-256 values are
in `PROVENANCE.json`. Original Apache-2.0/Ainekko notices remain intact.

| Profile | Public DTB SHA-256 | Size |
| --- | --- | --- |
| Linux | `95391dbcebbd8c10eb46e6e8f3a331c884be97458c67a77e5c844380920b66e5` | 2917 |
| 9front | `2af95f991d3b8731b3a2a48f98d0b1ef17b40d4df40c2341784c0aef8216bfb0` | 2761 |

## 9front: semantic parity, changed DTB representation

Historical independent artifact:
`990cdb7f40c680534b3c57d70048fb8359a8dcf04a1ec02f4bc7f5d644d4183a`
(2761 bytes). Its source is copied unmodified as
`reference/maxion-9front-original.dts`; its DTB is copied unchanged too.

The new tree moves `/memory@8600000000` from before `/cpus` to after `/soc`
to share the common Linux layout. Consequently flattened structure/string-table
ordering and binary bytes differ. The root node remains the ordinary FDT `/`
root with empty encoded name; it is not a new hardware memory model. This is
**not byte-identical 9front DTB acceptance**.

Tests parse both independently and compare all node paths/properties, ignoring
node/property order and normalizing numeric phandle allocations to target paths.
Only phandle allocation properties are omitted; all references in
`cold-boot-harts`, `interrupt-parent`, and `interrupts-extended` retain their exact
target and interrupt values. There are **zero semantic property changes**.
Explicit overrides preserve Sv48 on all harts, CPU0-only detailed ISA properties,
model, `console=0 user=glenda *ncpu=1 *uartpoll=1`, and all four enabled hardware
harts. Single-CPU operation is selected by 9front bootargs, not by hiding harts
from OpenSBI. Tests also compile the original source and require its original
DTB hash, never updating that reference.

## Linux: independently frozen corrected public base

`reference/maxion-linux-public-base.dtb` was derived once from the original
Linux DTS/default CPP configuration and corrected common DTSI (9330000-Hz
nominal timebase), with **no** initrd or macro overrides. It is not evidence of
the exact DTB used by any historical private Linux launch. The preserved Linux
source is a parameterized template; its conditional initrd code is inactive in
this frozen public snapshot. No private launch DTB or initrd bounds are copied.

Replacing CPP by native dtc `/include/` and factoring the common memory node
preserves the public default output byte-for-byte. Tests compare both hashes
and normalized property maps. All four CPUs advertise Sv39 and detailed ISA;
the default line is `earlycon=sbi console=ttyS0,115200n8 no4lvl`. Runtime initrd
fixups and packet/session data remain a separate loader derivation contract.

Both contracts require hart-0 OpenSBI cold boot, 9,330,000-Hz nominal timebase,
1-GiB memory range, CLINT routes, PLIC S/M context order, 41 sources,
`esperanto,keep-priorities`, and UART register width/shift/clock/source and
`current-speed=0`. Exact property allowlists exclude unintended runtime data.
These are source/static checks, **not fresh hardware qualification**.
