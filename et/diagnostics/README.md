# Preserved optional bring-up sources

These files are retained unchanged from the original ET OpenSBI work. They are
**not compiled or applied by `et/build.py`**, and they did not contribute bytes
to the canonical `fw_jump.bin`:

- `payload_hello.S`: a small no-stack S-mode hello/HSM test. Its nopic handling
  avoids the historical GOT-based `la` relocation problem.
- `etsoc1-maxion.dts` / `.dtsi`: hello/shared hardware description, including
  corrected nominal 9,330,000-Hz timebase, hart-0 cold boot, shared PLIC and
  UART1 properties. This is not the OS's complete external runtime DT.
- `opensbi-etsoc1-progress-markers.patch`: optional debug instrumentation that
  writes progress and trap information to the Maxion/SP mailbox.

The progress patch changes firmware bytes and performs unconditional
Maxion-specific MMIO. It requires reviewed mailbox ownership and a compatible
SP decoder. **Do not apply it to the bit-identical reference build or a generic
platform merely to obtain more logging.**

These diagnostic sources are archived historical work, not a freshly
hardware-qualified recovery path. The `fw_payload` hello recipe is preserved
as historical text in `../history/`; its firmware is distinct from `fw_jump`.
Default firmware has no embedded DT/payload, so canonical rebuilding needs
neither these inputs nor `dtc`.
