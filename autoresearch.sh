#!/usr/bin/env bash
# Deterministic quality benchmark for the psy-course website.
# Measures the committed artifacts the site serves: docs/data/courses.json,
# docs/data/courses.csv, docs/index.html, docs/app.js. No network access.
set -euo pipefail
cd "$(dirname "$0")"
python3 tools/benchmark_quality.py
