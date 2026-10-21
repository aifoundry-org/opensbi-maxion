# Tagged GitHub releases

`.github/workflows/maxion-release.yml` runs on pushed tags matching
`maxion-v*`. It then requires the strict downstream version format
`maxion-vMAJOR.MINOR.PATCH`, for example `maxion-v1.0.0` (no leading zeros,
suffixes or prereleases). Ordinary branch pushes and upstream tags such as
`v1.9` do not publish releases. Both annotated and lightweight tags are supported.

## Build and publication gates

1. Check out the exact commit from the tag-push event, with complete history.
   The local tag must resolve to that commit. Verify `et/SHA256SUMS`.
2. On the native `ubuntu-22.04` runner, explicitly install the recorded Ubuntu
   GCC 11.4.0 cross-toolchain and binutils 2.38 packages. Executable hashes and
   complete version strings must pass the existing preflight. Package removal
   from the Ubuntu mirrors is a failure, not permission to substitute tools.
3. Run offline tests, compile in a fresh directory, and require the historical
   raw firmware size, SHA-256 and full byte comparison. The first release
   remains the same firmware used for Linux and 9front.
4. Validate the build receipt against the clean tagged checkout, tools and
   output files. Produce an explicit, checksummed release asset set.
5. Transfer assets within the same workflow run to a separate publishing job.
   That job rechecks the package against its own checkout of the event commit
   and verifies the remote tag still resolves to the expected commit.
6. Create a **draft** GitHub release for the existing tag and attach all assets.
   Recheck the remote tag before publishing the draft.

The build job has only `contents: read`. Only the publishing job gets
`contents: write`; its `GH_TOKEN` is supplied only to the publishing step.
All three external actions are pinned to full commit hashes. No personal
access token, SSH deploy key, hardware access or deployment permission is needed
by the workflow. Repository/organization policy must permit GitHub Actions and
the publishing job's token permissions.

The workflow never creates a missing remote tag, replaces an existing release,
uses `--clobber`, or deletes old assets. A failed upload/publication can leave a
draft: inspect it before deliberately removing that incomplete draft and
rerunning. Never delete a published release merely to make a retry pass.

Diagnostic workflow artifacts expire after 14 days. **The release assets are
the consumer-facing files**, not those temporary workflow artifacts.
Rerunning a workflow may replace its temporary workflow artifacts; it never
replaces the separately published GitHub release assets.

## Published assets

| File | Purpose |
|---|---|
| `fw_jump.bin` | Canonical raw firmware consumed by the OS boot package |
| `fw_jump.elf` | Diagnostic symbols; not a bit-identical cross-path target |
| `build-receipt.json`, `build.log`, `fw_jump.readelf.txt` | Actual compilation evidence |
| `toolchain.json`, `PROVENANCE.json` | Compiler pins and historical source provenance |
| `release.json` | Tag, full source commit, firmware identity and asset hashes |
| `SHA256SUMS` | SHA-256 of every other attached asset |
| `RELEASE-NOTES.md` | Reference identity and qualification limits |
| `COPYING.BSD`, `ThirdPartyNotices.md`, `et-platform-LICENSE`, `et-platform-NOTICE` | License/notice material |
| `OPENSBI-BINARY-NOTICES.txt` | Individual upstream copyright notices and BSD-2/BSD-3 license terms |

`SHA256SUMS` intentionally does not checksum itself. The release manifest and
checksums are integrity records, not standalone signatures or GitHub build
attestations.

## Maintainer procedure

Before the first release, enable **immutable releases** in this repository's
GitHub settings and protect the `maxion-v*` tag namespace against unauthorized
creation, movement and deletion. Those administrative settings are not changed
by this source-controlled workflow. Do not move a release tag during a run.

After reviewing and pushing the tested `et` commit, create a new version tag
at that exact commit and push **only that tag**, for example:

```sh
git tag -a maxion-v1.0.0 <reviewed-full-commit> -m 'Maxion reference firmware 1.0.0'
git push origin refs/tags/maxion-v1.0.0
```

This is an example for a future intentional release, not a tag created by
implementing this workflow. A first hosted run is still required to validate
the runner's actual package provisioning and GitHub release publication.
Local native compilation and mocked publication tests cannot prove those
external services work.

## Linux and 9front consumption

Both OS workflows consume the **same** tagged `fw_jump.bin`; this is Maxion
firmware, not a Plan-9-specific build. Each consuming project's host-side
preparation pins the downstream tag, source commit, asset filename and expected
binary SHA-256 **in that project's own repository or checked-in dependency
manifest**.

Download the tagged binary, verify the independently pinned hash, and stage it
separately from the OS-specific assets:

- **Linux:** kernel `Image`, Linux device tree, and initramfs when required by
  the selected Linux boot configuration.
- **Plan 9/9front:** the Maxion kernel (with its embedded boot filesystem) and
  9front device tree; no Linux initramfs is used.

Neither OS links OpenSBI into its kernel. The separately loaded firmware runs
first and hands off through the shared [runtime contract](RUNTIME.md), including
the fixed next-stage entry address. Each OS supplies a compatible external DT.

Never select “latest,” accept a checksum solely because it arrived beside an
untrusted binary, or fetch replacement firmware from the running guest kernel.
A verified cached copy supports offline preparation. Updates are deliberate
dependency-pin changes, with validation for each consuming OS.
This workflow does not itself change either the Linux or the 9front consumer.

## Upstream check and source fingerprint

The pinned upstream revision and upstream `master` inspected on October 21,
2026 (`6ad246a1494807ee91e36ffcf60e4c30bb309d45`) contain only
`.github/workflows/repo-lockdown.yml`. That closes and locks pull requests in
favor of upstream's mailing-list review; it does not build or publish firmware.
It is left unchanged here.

Adding our workflow changes the repository's non-`et/` tree fingerprint.
The builder's strict expected tree is updated explicitly for that one added
workflow; no exclusions or bypasses are added. The OpenSBI firmware sources
remain the same two-patch baseline. Historical receipts correctly retain
their original tree identities.
