#!/bin/bash
# Export Claude Code OAuth credentials from macOS Keychain to the instance volume.
# Run this on your host machine when the container reports "Not authenticated".
set -e

DEST="instance/.claude/.credentials.json"
mkdir -p instance/.claude

CREDS=$(security find-generic-password -s "claude-code-credentials" -w 2>/dev/null) || \
CREDS=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null) || \
  { echo "No Claude Code credentials found in macOS Keychain."; echo "Run 'claude auth login' on your host first."; exit 1; }

echo "$CREDS" > "$DEST"
chmod 600 "$DEST"
echo "Credentials exported to $DEST"
echo "Restart the container: docker compose restart"
