# Servidor temporário em CPU

Esta VPS é um ambiente temporário de testes. Ela permite validar o painel, a API
e a preparação dos avatares em CPU. Os containers devem ficar parados entre os testes.
A geração de vídeos e o piloto da P02 exigem uma GPU NVIDIA e continuam pendentes.

## Instalação

Use Ubuntu 24.04 x86_64 com Docker Engine e Docker Compose instalados.
Reserve pelo menos 12 GB de RAM para validar o recorte em CPU.

O código fica em `/srv/avatar/app`, o modelo em `/srv/avatar/models` e os dados nos
volumes persistentes `avatar_pgdata` e `avatar_appdata`.

Crie `infra/compose/.env` com permissão `600`, usando senhas aleatórias para
`POSTGRES_PASSWORD` e `WORKER_TOKEN`. Defina `APP_ENV=production`,
`MODELS_DIR=/srv/avatar/models` e `PANEL_PORT=8088`.
Nunca use a senha de acesso SSH como senha do painel ou do banco.

Na raiz do código:

```bash
docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml build

mkdir -p /srv/avatar/models
docker run --rm --user 0:0 \
  -v "$PWD/docs/models:/policy:ro" \
  -v /srv/avatar/models:/models:rw avatar-worker \
  python -m avatar_worker.manifest pull \
  --policy /policy/MODEL_MANIFEST.json --dest /models \
  --component birefnet-portrait
```

O comando de download monta `/models` com escrita. O serviço de preparação usa
somente leitura. O manifesto verifica tamanho e SHA-256 antes de aceitar o modelo.

```bash
docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml up -d --wait
```

Crie o primeiro usuário pela CLI, com a senha na entrada padrão:

```bash
docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml exec -T api \
  avatar-api users create --username admin@avatar.local --password-stdin
```

## Acesso

O painel de testes escuta apenas em `127.0.0.1:8088` no servidor.
Abra o túnel na sua máquina e mantenha o comando em execução:

```bash
ssh -N -L 8088:127.0.0.1:8088 root@157.173.113.161
```

Abra `http://localhost:8088`. A comunicação com o servidor passa pelo SSH.
Na instalação realizada em `157.173.113.161`, o usuário inicial e a senha foram
gerados e guardados em `/srv/avatar/access/painel-admin.json`, com leitura permitida
somente ao root. Leia esse arquivo por SSH para obter o acesso. Em uma nova
instalação, guarde a senha escolhida para a CLI no cofre de senhas da equipe.

## Operação

```bash
docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml ps

docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml logs --tail 100 worker
```

Para atualizar, preserve `infra/compose/.env`, `/srv/avatar/models` e os volumes.
Repita o build e o `up -d --wait` após atualizar o código.
Não use `down -v` neste servidor: ele apagaria os dados persistentes.

Ao terminar os testes, pare e remova os containers, preservando os dados:

```bash
docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml down
```

Para testar novamente, rode `up -d --wait` com os mesmos arquivos e abra o túnel.
Para gerar vídeos, use o procedimento de GPU em `INSTALACAO.md`.
