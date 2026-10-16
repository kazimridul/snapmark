#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo 'Create the environment first: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"' >&2
    exit 1
fi
exec .venv/bin/python -m cpp "$@"
