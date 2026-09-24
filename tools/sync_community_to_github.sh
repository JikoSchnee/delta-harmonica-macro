#!/usr/bin/env bash
# Production scores must stay in the private Docker volume. A branch in a
# public repository is public, including every score in its Git history.
set -euo pipefail

echo "Refusing to sync production scores to GitHub: public branches expose the song library." >&2
echo "Use the server backup for private retention; export only explicitly approved public scores." >&2
exit 1
