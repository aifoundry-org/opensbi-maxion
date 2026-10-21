# Hosted build diagnosis and exact-byte repair

## First hosted run: correctly rejected

GitHub Actions run `39670322014`, tag `maxion-v1.0.0`, built the original
commit `649d779d10f67c5d13c0d69a33397f1dd7701cc0` on October 21, 2026.
Checkout, support checksums, exact cross-compiler/binutils fingerprint checks,
and all 41 then-current unit tests passed. Compilation succeeded, but the
mandatory raw-byte check rejected the candidate. Publication was skipped.

| Raw firmware | Bytes | SHA-256 |
|---|---:|---|
| Required historical Linux/9front reference | 279048 | `97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18` |
| Rejected hosted candidate | 279048 | `0242cb99ac3845c0d11ef72f28abbe363a7962f9abb1e212539ec7f061e7eb09` |

The owner supplied the actual Actions log archive. This was a reproducibility
failure, not a compile error or a reason to accept a new reference.

## Root cause reproduced locally

Upstream `scripts/carray.sh` calls `awk` and emits generated driver arrays by
iterating `for (v in VAR_LIST)`. That associative-array iteration order is not
portable between awk implementations. The historical host selected **mawk**;
the initial builder fingerprinted other host tools but only enforced cross-tool
pins, leaving default awk selection uncontrolled.

A private experiment downloaded/extracted GNU awk without installing it or
changing system alternatives. With the same unmodified firmware source,
cross tools and build settings, selecting GNU awk reproduced the **exact
rejected hosted SHA-256** above. A separate numeric-order experiment in a
disposable source copy produced the same candidate. Ten generated array files
changed order, and all 141 differing raw bytes fell in `.rela.dyn`.

This establishes the missing host code-generation dependency. GNU awk itself
is not defective; the source generator depends on an implementation-specific
iteration order. Changing that generator to numeric iteration would produce
the rejected bytes, not preserve the historically tested firmware.

## Repair

- Pin the actual `/usr/bin/mawk` executable and version in
  `et/toolchain.json` under `codegen_tools`.
- Require Ubuntu package `mawk=1.3.4.20200120-3` in the hosted recipe.
- Create a new private `host-tools/awk -> /usr/bin/mawk` alias for each build,
  ahead of the fixed system PATH. Do not mutate host alternatives or firmware
  sources.
- Record the selected code-generation tool in the build receipt and verify it
  again when packaging/publishing.
- Retain failed candidate BIN/ELF and generated arrays as diagnostic workflow
  artifacts. They are never silently promoted to releases.

The reference bytes, source patches and expected raw SHA-256 remain unchanged.
The failed tag is retained as historical evidence. A corrected release uses a
new tag rather than moving the failed tag or hiding its run.

## Corrected hosted release: PASS

Tag **`maxion-v1.0.1`**, commit
`19440df26710933841909f08d0c070a1bff810e3`, completed GitHub Actions run
**`39672576351`** successfully. Both the build and publish jobs passed:
package installation, pinned tool checks, all 45 tests, actual compilation,
mandatory firmware comparison, packaging, cross-job verification, draft upload
and publication.

All **15 published release assets** were then downloaded independently.
Their GitHub-reported digests and `SHA256SUMS` entries verified. The release
package verifier bound the downloaded receipt, toolchain, provenance and
licenses to the clean tagged checkout. The downloaded `fw_jump.bin` compared
byte-for-byte equal to the historical reference:

```text
279048 bytes
97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18
```

This is measured hosted build **and publication** success, not just a local
simulation. A separate local test also selected GNU awk as the simulated host
default and confirmed the repaired builder's private mawk selection still
produced the reference bytes.

GitHub reported this published release as `draft: false`, `immutable: false`.
Repository-level immutable releases were not enabled by this workflow.
Administrators should enable that setting for future releases; consumers must
still pin the expected binary hash independently.

The attribution correction is documented separately in
[COMMIT-ATTRIBUTION.md](COMMIT-ATTRIBUTION.md). The failed v1.0.0 tag and
original receipts are preserved; upstream history and firmware source files
remain unchanged.
