#!/bin/sh
set -eu
# Private, restricted SSH forwarding. The deployment mounts a verified configuration.
if [ -n "${VERDA_BATCH_SSH_CONFIG:-}" ]; then
    ssh -F "$VERDA_BATCH_SSH_CONFIG" -N -o BatchMode=yes -o StrictHostKeyChecking=yes \
        -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 -o ServerAliveCountMax=3 avatar-api &
fi
exec python -m avatar_worker.verda_batch
