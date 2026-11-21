#!/usr/bin/env sh
# Creates .env from .env.example with fresh random secrets (macOS / Linux / WSL).
set -e
[ -f .env ] && { echo ".env already exists; leaving it alone."; exit 0; }
jwt=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
key=$(python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())")
sed -e "s|^NEXUS_JWT_SECRET=.*|NEXUS_JWT_SECRET=$jwt|" -e "s|^NEXUS_ENCRYPTION_KEY=.*|NEXUS_ENCRYPTION_KEY=$key|" .env.example > .env
echo "Created .env with new secrets."
