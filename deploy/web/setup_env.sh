#!/usr/bin/env bash
#
# One-time environment setup for the web driver on a corporate-proxy Mac.
#
# Two gotchas this handles:
#  1) Python/pip can't verify TLS (the proxy uses a custom root CA that's in the
#     macOS keychain but not in Python's bundle) -> export the keychain roots to
#     a PEM and point pip/Playwright at it.
#  2) Playwright's own Chromium download gets reset by the proxy -> skip it and
#     use the system-installed Google Chrome via channel="chrome".
#
# After this, run the driver with:  SSL_CERT_FILE=~/.threes-ca.pem python threesjs_driver.py
#
set -euo pipefail
CA="$HOME/.threes-ca.pem"

echo "1) Exporting keychain root CAs -> $CA"
security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain >  "$CA"
security find-certificate -a -p /Library/Keychains/System.keychain                        >> "$CA" 2>/dev/null || true
echo "   $(grep -c 'BEGIN CERT' "$CA") certificates"

echo "2) Installing Python deps (playwright, pillow, numpy) with that CA"
SSL_CERT_FILE="$CA" PIP_CERT="$CA" python3 -m pip install --user playwright pillow numpy

echo "3) Using system Google Chrome (no Chromium download needed)"
if [ -d "/Applications/Google Chrome.app" ]; then
  echo "   found Google Chrome — the driver launches it via channel=chrome"
else
  echo "   WARNING: Google Chrome not found. Install it, or run:"
  echo "     SSL_CERT_FILE=$CA NODE_EXTRA_CA_CERTS=$CA python3 -m playwright install chromium"
fi

echo
echo "Done. Start the brain and run the driver:"
echo "   go run ../../cmd/moveserver -addr :9010 -deckaware &"
echo "   SSL_CERT_FILE=$CA python3 threesjs_driver.py --headed --user-data-dir ~/.threes-profile   # first run: click through the one-time tutorial"
echo "   SSL_CERT_FILE=$CA python3 threesjs_driver.py --user-data-dir ~/.threes-profile             # afterwards: headless auto-play"
