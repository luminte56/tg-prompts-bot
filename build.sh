#!/bin/bash
set -e

echo "===> [WhiteLord IntelLab] Initializing Infrlo build..."
df -h
export TMPDIR="${HOME}/.tmp"
export TEMP="${HOME}/.tmp"
export TMP="${HOME}/.tmp"
mkdir -p "${TMPDIR}"

echo "===> [WhiteLord IntelLab] Installing Python dependencies without cache..."
pip install --no-cache-dir --user -r requirements.txt

echo "===> [WhiteLord IntelLab] Build finished successfully!"
