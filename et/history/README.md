# Archival material — not the build or deployment entry point

These two files preserve the original ET recipe and README byte-for-byte.
Their `.txt` suffix and nonexecutable mode are intentional:

- `build-opensbi.sh.txt`
- `original-README.md.txt`

The later standalone-archive recipe and its dated test report from the 9front
package are also preserved as `portable-build-opensbi.sh.txt` and
`portable-VALIDATION.md.txt`. They record the intermediate portability work;
their old directory references are not dependencies of this fork.

**Use `../README.md` and `../build.py`, not these old directions.**
The old script patches an external checkout, assumes old paths, can reuse
objects and does not enforce the source/toolchain/reference identity.
Its documentation also contains flash/OTA examples and historical board
assumptions that are not current safety gates or permission to operate hardware.
Do not replay those commands.

The “nothing else uses this memory outside firmware update” wording in the
old hello materials is not a host allocator reservation or concurrency proof.
No OTA/SDK/competing launcher is permitted while the historical firmware/
guest memory layout is in use. See `../docs/RUNTIME.md`.

Original hashes and paths are in `../PROVENANCE.json`. The archival recipe's
associated source/DT/patch inputs are retained in sibling `diagnostics/` and
`patches/` directories. The original relative directory layout is not offered
as a new executable workflow.
