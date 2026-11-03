#!/usr/bin/env bash
# Cria um usuário do painel no container da API em execução, ou troca a senha com --reset (que
# também reativa um acesso removido e encerra as sessões abertas). Sem senha na entrada padrão,
# gera uma senha provisória e a mostra uma única vez; a senha nunca vai para argumento nem log.
set -euo pipefail
USERNAME=
PROJECT=
FROM_STDIN=0
COMMAND=create
while [ "$#" -gt 0 ]; do
  case "$1" in
    --username) USERNAME="${2:?Falta e-mail}"; shift 2 ;;
    --project-name) PROJECT="${2:?Falta projeto}"; shift 2 ;;
    --password-stdin) FROM_STDIN=1; shift ;;
    --reset) COMMAND=set-password; shift ;;
    *) echo 'Uso: create-user.sh --username e-mail [--reset] [--password-stdin] [--project-name nome]' >&2; exit 2 ;;
  esac
done
[ -n "$USERNAME" ] || { echo 'Informe --username com o e-mail de acesso.' >&2; exit 2; }
FILTERS=(--filter label=com.docker.compose.service=api --filter status=running)
[ -z "$PROJECT" ] || FILTERS+=(--filter "label=com.docker.compose.project=$PROJECT")
CONTAINERS="$(docker ps -q "${FILTERS[@]}")"
case "$(printf '%s' "$CONTAINERS" | grep -c .)" in
  0) echo 'Nenhum container da API em execução. Suba a instalação antes.' >&2; exit 1 ;;
  1) ;;
  *) echo 'Mais de um container da API em execução; informe --project-name.' >&2; exit 1 ;;
esac
if [ "$FROM_STDIN" -eq 1 ]; then
  IFS= read -r PASSWORD
else
  PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
fi
printf '%s\n' "$PASSWORD" | docker exec -i "$CONTAINERS" avatar-api users "$COMMAND" --username "$USERNAME" --password-stdin
if [ "$FROM_STDIN" -eq 0 ]; then
  echo "Senha provisória: $PASSWORD"
  echo 'Guarde agora: ela não é mostrada de novo.'
fi
