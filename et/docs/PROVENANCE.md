# Source, reference and license provenance

The full upstream OpenSBI history is retained. This fork's reference base is
`6ad246a1494807ee91e36ffcf60e4c30bb309d45`, upstream tree
`55a808af978e000950dcb01e6cf0fc87b71a641f`.

The two production patches were imported unchanged from
`aifoundry-org/et-platform`, commit
`cb3f00b751df0041f57dcaf926f06d9a723a577d`,
`device-bootloaders/src/Maxion/opensbi/`.
The original PLIC change was introduced in `f84a8b20`, and the trap-value/
`fw_jump` work in `9e5d002c`. The corrected DT timebase followed in `57ba7a8a`.

Standalone production commits are now `8736d4f9` and `b8681ccd`, formerly
`c50ce7a2` and `ba6cec97` before the owner's requested
[attribution correction](COMMIT-ATTRIBUTION.md). Their original
source tree, **excluding only the new top-level `et/` directory**, is
`f048c30f926905c34497da4665a14c2d2d5e564b`.
No progress-marker instrumentation is applied to that tree.

The release workflow adds only `.github/workflows/maxion-release.yml` outside
`et/`, changing the current enforced non-`et/` tree to
`e4cfebeae3381c05e8d77f558040eaaedd2aa24d`.
No firmware source files change. Both identities are retained in
`et/PROVENANCE.json`; historical receipts keep their original source trees.

`et/PROVENANCE.json` maps all eight original files to their retained location
and original SHA-256. Original diagnostic files and historical text are not
silently rewritten into new qualification claims. The copies of production
patches are review/provenance material, not build-time patch dependencies.

The previous hardened portable builder was developed in the local 9front
package (`et/opensbi/`, packaging lineage ending
`18732d3350d8eb20c30b4b7f10235173715833d2`). Its clean outputs had already
matched the frozen firmware. The new standalone builder instead builds this
fork's actual committed source and enforces byte equality as an acceptance
gate. That previous repository is not required to build this one.

## Independent reference

`et/reference/fw_jump.bin` was copied from the preserved hardware-tested
Maxion package **before** running the standalone build under test. Its hash
was already recorded in the original lab's boot-artifact manifests:

`97252e0c8dbd66b38950d14a89f3bfdedd994727ee22dc1f2652144cde23ba18`

It is 279,048 bytes. It is not a candidate generated and then blessed as its
own expected result. `et/reference/SHA256SUMS` describes the frozen bytes;
the builder also enforces the expected hash independently.

## Licenses

The upstream root licenses, contributors and per-file notices are unchanged:
OpenSBI is predominantly BSD-2-Clause, with some BSD-3-Clause files, libfdt's
BSD license option and bundled Kconfiglib's ISC terms. Consult the actual
upstream headers and `COPYING.BSD` / `ThirdPartyNotices.md`.

The imported ET DTS/DTSI and hello payload have Apache-2.0 SPDX/Ainekko notices.
The original ET repository's Apache license and NOTICE are retained in
`et/licenses/` for its recipe/patch provenance. The new ET build tooling and
documentation are Apache-2.0. None of that relicenses upstream OpenSBI or
removes existing per-file notices.

No private keys, packet-session seeds, site-specific loader, proprietary RTL,
card flash image, OS kernel or installed driver is included. The source
toolchain and host OS remain explicitly documented prerequisites.
