# ET-SOC1 Maxion OpenSBI — exact reference rebuild

This branch carries the Maxion changes on top of upstream OpenSBI
**`6ad246a1494807ee91e36ffcf60e4c30bb309d45`**, retaining upstream history.
It builds the **same raw `fw_jump.bin` used for the successful Maxion Linux/
9front boot workflow**, not a new firmware configuration.

The acceptance target is:

```text
SHA-256: 97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18
Size:    279048 bytes
```

`et/reference/fw_jump.bin` is the frozen, independently preserved historical
binary. **The build must match its actual bytes, not merely print a new hash.**
A mismatch returns failure and retains outputs/logs for investigation. Do not
replace the reference with a candidate to make a failed comparison pass.

This is a build-only workflow: no UART, card, driver, flashing, reset or
deployment operation is performed.

## 1. Get the source

```sh
git clone --branch et https://github.com/aifoundry-org/opensbi-maxion.git
cd opensbi-maxion
```

Use a normal Git clone with a clean tracked source tree and a short path without
spaces or Make metacharacters. The required source patches are **already
applied and committed**; do not apply the copies in `et/patches/` again.
No sibling `et-platform`, `9front`, old `/tmp/opensbi`, vendor SDK or source
download during the build is needed.

## 2. Install the reference build prerequisites

The validated native environment is **Ubuntu 22.04, x86-64 Linux**, using:

| Component | Reference |
|---|---|
| RISC-V GCC | Ubuntu GCC 11.4.0 |
| `gcc-11-riscv64-linux-gnu` | `11.4.0-1ubuntu1~22.04cross1` |
| `gcc-riscv64-linux-gnu` selector package | `4:11.2.0--1ubuntu1` |
| `binutils-riscv64-linux-gnu` | `2.38-4ubuntu2.12` |
| GNU Make | 4.3 |
| Python | 3.10 or newer; validation used 3.10.12 |
| Other host tools | Git and standard Linux utilities |

On a suitable Ubuntu 22.04 server, provision prerequisites explicitly:

```sh
sudo apt-get update
sudo apt-get install git make python3 \
  gcc-riscv64-linux-gnu=4:11.2.0--1ubuntu1 \
  gcc-11-riscv64-linux-gnu=11.4.0-1ubuntu1~22.04cross1 \
  binutils-riscv64-linux-gnu=2.38-4ubuntu2.12
```

These commands install host packages only. The build itself needs no root
privileges or network. If your repository no longer supplies those exact
packages, stop and provision the recorded toolchain; silently substituting a
newer compiler is not the validated recipe.

The builder checks the installed `/usr/bin/riscv64-linux-gnu-*` tools against
`et/toolchain.json`, including compiler internals, and records the actual tools.
Use the **Linux RISC-V** toolchain with its PIE-capable linker. The ET bare-metal
toolchain is not a substitute. No target libc, `dtc`, pyelftools, Linux kernel
source or external device tree is required to build this `fw_jump` image.

Compiler binaries, host shared libraries and a Linux/container image are not
bundled. This is a checked, pinned native recipe, not a claim that every GCC
release, architecture or distribution generates identical code. No untested
Docker recipe is presented as verified.

## 3. Verify, build and compare

Run from the repository root:

```sh
sha256sum -c et/SHA256SUMS
python3 et/build.py --verify-only
python3 -m unittest discover -s et/tests -p 'test_*.py' -v
mkdir -p et/build
python3 et/build.py --out "$PWD/et/build/reproduce-1" --jobs 2
cmp et/reference/fw_jump.bin et/build/reproduce-1/fw_jump.bin
sha256sum et/build/reproduce-1/fw_jump.bin
```

Choose a **new** output directory for every build. An existing output directory
is refused, not cleaned or reused. Alternatively `python3 et/build.py` chooses
a fresh `et/build/run-*` directory and prints its location.

Require **`BIT-IDENTICAL-PASS`**, successful `cmp` (no output, exit 0), and the
SHA-256 above. An unexpected build, reference, source or toolchain mismatch is
a failure to investigate—not permission to update the expected result.

The builder:

1. Verifies the independent reference, exact patched source tree and toolchain.
2. Rejects uncommitted source changes and makes a fresh snapshot of the
   committed source. It never builds against old objects in another checkout.
3. Clears ambient make/compiler/firmware settings and uses the explicit
   reference configuration below.
4. Retains the source/build logs, resolved configuration, ELF inspection,
   input identity and toolchain/output hashes with the output.
5. Compares the produced raw firmware against the frozen reference.

The symbol-bearing **ELF is not the bit-identical acceptance target**. Its
debug paths may vary with checkout/output location. The card was loaded with
the raw `.bin`, which is the file compared here.

## Reference configuration

| Setting | Value |
|---|---|
| Platform | `generic` |
| XLEN / ISA / ABI | `64` / `rv64imac_zicsr_zifencei` / `lp64` |
| Firmware load/entry | `FW_TEXT_START=0x8004200000` |
| Next-stage entry | `FW_JUMP_ADDR=0x8600200000` |
| External DT relocation offset | `FW_JUMP_FDT_OFFSET=0x2200000` |
| Enabled image | `FW_JUMP=y` |
| Other images | `FW_DYNAMIC=n FW_PAYLOAD=n` |
| Build metadata | `BUILD_INFO=n`, empty `OPENSBI_VERSION_GIT` |
| Deterministic environment | `LC_ALL=C`, `TZ=UTC`, `SOURCE_DATE_EPOCH=1790598985` |

There is **no embedded kernel, DTB or hello payload**. At runtime a compatible
boot stub supplies the external DT in `a1`; OpenSBI relocates it to
`0x8006400000` and hands off in S-mode. The firmware can serve Linux or 9front
with their appropriate external kernels/DTs; those OS builds are not included
here.

## What was imported

Production changes are two separate commits:

- **Shared PLIC priorities:** add the `esperanto,keep-priorities` DT opt-in so
  cold initialization does not clear source priorities shared with SP/MM.
- **Maxion trap-value workaround:** sign-extend fault addresses from bit 47
  for the qualified Esperanto vendor/architecture IDs (RTLMAX-617).

All eight files from the original ET OpenSBI directory are preserved across
`et/patches/`, `et/diagnostics/` and `et/history/`, with original commit/path/
hash mapping in `et/PROVENANCE.json`. The optional hello payload, DTS/DTSI and
mailbox progress-marker patch are **not** part of the canonical build.
See [diagnostic scope](diagnostics/README.md) and [historical caveats](history/README.md).
This repository does not import unrelated BL2, Linux, driver, packet or OTA
work as if it were an OpenSBI patch.

## Validation and operating boundary

- [Tag-triggered GitHub build and release workflow](docs/RELEASES.md)
- [Validation records](VALIDATION.md)
- [Linux/9front binary identity evidence](docs/LINUX-IDENTITY.md)
- [Provenance and licenses](docs/PROVENANCE.md)
- [Runtime contract and safety](docs/RUNTIME.md)

The source/recipe was separated without upgrading OpenSBI or changing the
historically used firmware bytes. Hash equality is not a new hardware boot,
an allocator reservation, coherent DMA, general errata/security qualification,
or a qualified OTA/rollback path. **A physical card still needs compatible
provisioned firmware, exclusive ownership and separate authorization.**
