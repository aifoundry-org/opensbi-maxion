#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Consolidate upstream binary notices without copying implementation code."""

import argparse
from collections import defaultdict
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "et/licenses/OPENSBI-BINARY-NOTICES.txt"
SCOPES = ("firmware", "include", "lib", "platform")
# Skip string/character literals when looking for C comments. Also recognize
# Make/Kconfig comment lines, but not C preprocessor directives.
TOKENS = re.compile(
    r'"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'|"
    r"/\*.*?\*/|"
    r"//[^\n]*(?:\n[ \t]*//[^\n]*)*|"
    r"^[ \t]*#(?:[ \t]+[^\n]*|)(?:\n[ \t]*#(?:[ \t]+[^\n]*|))*",
    re.MULTILINE | re.DOTALL,
)
NOTICE = re.compile(r"copyright|SPDX-License-Identifier:", re.IGNORECASE)


def notice_comments(text):
    """Include complete notice comments, including notices after header guards."""
    return [
        match.group().strip()
        for match in TOKENS.finditer(text)
        if match.group().lstrip().startswith(("/*", "//", "#"))
        and NOTICE.search(match.group())
    ]


def generate():
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", *SCOPES], cwd=ROOT
    ).decode().split("\0")
    groups = defaultdict(list)
    for path in sorted(filter(None, paths)):
        text = (ROOT / path).read_text()
        comments = notice_comments(text)
        if NOTICE.search(text) and not comments:
            raise ValueError("Uncaptured source notice: " + path)
        if comments:
            groups["\n\n".join(comments)].append(path)

    # Use the complete BSD-3-Clause grant/disclaimer already retained in this
    # upstream tree, rather than fetching or paraphrasing license conditions.
    quad = notice_comments((ROOT / "lib/utils/libquad/qdivrem.c").read_text())[0]
    quad = "\n".join(
        re.sub(r"^ \* ?", "", line)
        for line in quad.splitlines()[1:-1]
    ).strip()
    quad = quad[quad.index("Copyright (c) 1992"):]
    assert "3. Neither the name of the University" in quad
    assert quad.endswith("SUCH DAMAGE.")

    sections = [
        """OpenSBI binary distribution notices
===================================

This supplements COPYING.BSD and ThirdPartyNotices.md. It retains individual
upstream notices from tracked firmware/, include/, lib/ and platform/ files.
Coverage is deliberately broader than the linked generic RV64 firmware:
uncompiled platforms, tests and RV32 helpers may appear. This does not assert
that all listed components are present in the firmware.

BSD-2-Clause is the selected license for libfdt's disjunctively dual-licensed
sources. The full BSD-2-Clause and BSD-3-Clause conditions/disclaimers are
included below. Per-file source notices are reproduced as comments, not code.
Build-only Kconfiglib/scripts and downstream et/ diagnostics are outside this
binary-source scope; their licenses are not changed.

Regenerate/check using: python3 et/ci/binary-notices.py [--check]
""",
        "BSD-2-Clause: upstream COPYING.BSD\n"
        "=================================\n\n" + (ROOT / "COPYING.BSD").read_text(),
        "Upstream ThirdPartyNotices.md\n"
        "============================\n\n" + (ROOT / "ThirdPartyNotices.md").read_text(),
        "BSD-3-Clause: HTIF and Berkeley arithmetic notices and terms\n"
        "==========================================================\n\n"
        "HTIF (lib/utils/sys/htif.c and include/sbi_utils/sys/htif.h):\n"
        "Copyright (c) 2010-2020, The Regents of the University of California\n"
        "(Regents).  All Rights Reserved.\n\n"
        "The following complete BSD-3-Clause terms are retained verbatim from\n"
        "lib/utils/libquad/qdivrem.c (comment delimiters removed). They include\n"
        "the Berkeley arithmetic attribution as well as all three conditions\n"
        "and the Regents' disclaimer:\n\n" + quad + "\n",
        "Individual source notices\n"
        "=========================\n\n"
        "Identical notice blocks are grouped; paths identify their source files.\n",
    ]
    for comments, names in sorted(groups.items(), key=lambda item: item[1][0]):
        sections.append("Files:\n" + "".join("  " + name + "\n" for name in names)
                        + "\n" + comments + "\n")
    return "\n".join(section.rstrip() + "\n" for section in sections).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if committed notice content differs")
    args = parser.parse_args()
    data = generate()
    if args.check:
        if OUTPUT.read_bytes() != data:
            parser.exit(1, "Binary notices differ; regenerate and review.\n")
        print("BINARY-NOTICES-PASS")
    else:
        OUTPUT.write_bytes(data)
        print("Wrote", OUTPUT.relative_to(ROOT), "(" + str(len(data)) + " bytes)")


if __name__ == "__main__":
    main()
