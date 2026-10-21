# Commit attribution correction

On October 21, 2026, at the repository owner's request, the seven downstream
commits were rewritten with author and committer `Roman V Shaposhnik
<rvs@apache.org>`, preserving `Co-authored-by: Shelley <shelley@exe.dev>`.
The upstream base and its history were not rewritten. Each rewritten commit
has exactly the same tree as its original; firmware and support file bytes
were unchanged by the rewrite.

| Historical commit | Rewritten commit |
|---|---|
| `c50ce7a2af8d50fd552f494417aca2c9955e2bf8` | `8736d4f9d30e8fe94eec483635b34b3ab27b0afb` |
| `ba6cec973383b66427d605692cb9843b0349eab9` | `b8681ccdd3e67e5f35360898f398dd2add67c82f` |
| `6a53a4f77687e5f0d33e4768eb17f43bcf0fa5d1` | `68e6f1f4f3dd586fad88888ebb3f9d6579b39c4f` |
| `483e3fd677bf1f66012b43abdf58c225dd6d8571` | `2fb44823e20427be818f0da089788cf360d71f3e` |
| `007cdfb63cdc8d7bb8132eb6b4af38a7b39ca5fb` | `f9bc300ccbf382fb3dc3ce6bfb84a8c394c1a2db` |
| `801a49362bf3c9909d3f923970eb9539873e461c` | `122a752530d15f817d1eaa91b59b8f812ae1721b` |
| `649d779d10f67c5d13c0d69a33397f1dd7701cc0` | `4c808b63d8453371c41da1d6350b6d444e186fe6` |

Older build receipts and validation reports deliberately retain their original
commit IDs: they are records of actual past builds, not regenerated evidence.
The failed `maxion-v1.0.0` tag remains at its original commit so the Actions
failure can still be inspected. The corrected `et` branch uses the new lineage;
subsequent firmware fixes/releases receive new commits and tags.
