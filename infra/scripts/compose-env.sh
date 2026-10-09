#!/usr/bin/env bash
# Source por install/backup; não imprime nem carrega segredos no shell.
# Docker Compose lê --env-file após remover overrides ambientais das mesmas variáveis.
sanitize_compose_environment() {
  local names variable
  names="$(python3 - "$@" <<'PY'
from pathlib import Path
import re
import sys

names = {'COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_PROJECT_NAME', 'COMPOSE_ENV_FILES', 'COMPOSE_DISABLE_ENV_FILE'}
for argument in sys.argv[1:]:
    path = Path(argument)
    files = path.glob('docker-compose*.yml') if path.is_dir() else [path]
    for file in files:
        names.update(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', file.read_text()))
print('\n'.join(sorted(names)))
PY
)" || return 1
  while IFS= read -r variable; do
    unset "$variable" || return 1
  done <<< "$names"
}
