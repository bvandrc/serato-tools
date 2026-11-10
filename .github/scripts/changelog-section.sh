#!/usr/bin/env bash
# Prints the body of CHANGELOG.md's section for the version given (e.g. 6.0.0), without its heading, or nothing if
# there's no section for it.
set -euo pipefail

awk -v heading="## [$1]" '
  # each "## [x.y.z] - date" heading starts a section, ending the one before it
  index($0, "## [") == 1 { in_section = (index($0, heading) == 1); next }
  in_section { lines[++n] = $0 }
  END {
    # trim the blank lines around the body
    first = 1; while (first <= n && lines[first] ~ /^[[:space:]]*$/) first++
    last = n; while (last >= first && lines[last] ~ /^[[:space:]]*$/) last--
    for (i = first; i <= last; i++) print lines[i]
  }
' CHANGELOG.md
