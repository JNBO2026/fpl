#!/usr/bin/env bash
# Refresh everything: pull live FPL data, rebuild projections, render the page.
set -euo pipefail
cd "$(dirname "$0")"
python3 build_data.py
python3 render.py
