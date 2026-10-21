#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Invoke only in the publishing step; never pass GH_TOKEN to build commands.
set -euo pipefail
if [[ $# != 2 ]]; then
    echo "Usage: $0 maxion-vMAJOR.MINOR.PATCH ASSETS_DIRECTORY" >&2
    exit 2
fi
: "${GH_REPO:?GH_REPO must select the release repository}"
tag=$1
assets=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$script_dir/release.py" verify --tag "$tag" --assets "$assets"
commit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$assets/release.json")
check_remote_tag() {
    local remote_commit
    remote_commit=$(gh api "repos/$GH_REPO/commits/$tag" --jq .sha)
    if [[ "$remote_commit" != "$commit" ]]; then
        echo "Remote tag differs from verified package/current HEAD: $tag" >&2
        exit 1
    fi
}
check_remote_tag
if gh release view "$tag" >/dev/null 2>&1; then
    echo "Release already exists; refusing replacement: $tag" >&2
    exit 1
fi
# No upload --clobber, delete, tag creation, or cleanup on failure: a failed
# upload/create/edit must not publish a partial release or replace old assets.
gh release create "$tag" --verify-tag --draft --title "$tag" \
    --notes-file "$assets/RELEASE-NOTES.md" \
    "$assets/fw_jump.bin" "$assets/fw_jump.elf" \
    "$assets/build-receipt.json" "$assets/build.log" \
    "$assets/fw_jump.readelf.txt" "$assets/toolchain.json" \
    "$assets/PROVENANCE.json" "$assets/COPYING.BSD" \
    "$assets/ThirdPartyNotices.md" \
    "$assets/OPENSBI-BINARY-NOTICES.txt" \
    "$assets/et-platform-LICENSE" "$assets/et-platform-NOTICE" \
    "$assets/maxion-linux.dtb" "$assets/maxion-9front.dtb" \
    "$assets/dts-build-receipt.json" "$assets/dts-sources.tar.gz" \
    "$assets/release.json" "$assets/SHA256SUMS" "$assets/RELEASE-NOTES.md"
check_remote_tag
gh release edit "$tag" --draft=false
