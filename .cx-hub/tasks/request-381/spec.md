# Spec da Solicitacao

## Contexto

O projeto avatar (video-generation) gera vídeos de avatar em duas VPS: uma CPU (API/PostgreSQL/painel) e uma GPU (worker com modelos de TTS/render). Atualmente, o worker GPU fica rodando continuamente (`docker-compose.worker.yml`), ouvindo a fila de vídeo (`video_jobs`). Quando um job chega, o supervisor (`avatar_worker.supervisor`) faz claim, processa e publica o resultado. Quando a fila está vazia, o worker continua rodando, consumindo GPU ociosamente.

A task solicita provisionamento automático da VM GPU sob demanda: ao receber pedidos na fila, uma VM Verda deve ser criada, o worker deve iniciar, processar a fila e, quando a fila esvaziar, a VM deve ser encerrada preservando o disco de modelos.

## Entendimento da solicitacao

Importar o código do PR #8 de `BrookSK/video-generation` (commit `f26fcbda207bbb6c3995668b9272913d9a7fb1df`) para branch derivada de `homolog` (`cbb451a`), validar o ciclo completo em DEV (criação de VM, worker, processamento, upload MP4, exclusão da VM com disco preservado) e, após aprovação técnica no Hub, promover para HOMOLOG e PROD.

## Comportamento atual

O worker GPU (`avatar_worker.supervisor`) roda 24/7 na VPS GPU. Jobs são criados via API (`POST /api/v1/jobs`), enfileirados em `video_jobs`, reivindicados pelo worker, processados e concluídos. Não há automação de infra: a VM GPU é ligada/desligada manualmente.

## Comportamento esperado

1. Um pedido de vídeo entra na fila (`video_jobs` com status `queued`).
2. Um agente/serviço detecta jobs pendentes e provisiona uma VM Verda (GPU) via API de hypervisor.
3. A VM Verda inicializa, monta o disco de modelos (persistente, preservado entre ciclos), baixa a imagem worker mais recente e inicia o supervisor.
4. O supervisor faz claim, processa o job, faz upload do MP4 para a API (VPS CPU), conclui o job.
5. Quando a fila fica vazia por N segundos (configurável), a VM Verda é encerrada (preservando o disco de boot/modelos).
6. O disco de modelos persiste entre ciclos para evitar redownload.

## Escopo

- Importar o código do PR #8 para uma branch a partir de `homolog`.
- Criar script ou módulo de orquestração da VM Verda (provisionar, aguardar ready, monitorar fila, desligar).
- Modificar o worker/supervisor para reportar heartbeat de forma que o orquestrador saiba que está vivo.
- Adicionar lógica de "shutdown when idle" no orquestrador ou no supervisor com sinal para o host.
- Pipeline de release: nova imagem worker com as alterações, atualização dos manifests compose (release worker, API).
- Roteiro de validação em DEV: criação de VM, execução de job, download do MP4, exclusão da VM, verificação do disco preservado.
- Registro do SHA da imagem e versionamento dos manifestos antes de HOMOLOG e PROD.

## Fora do escopo

- Alterações no pipeline de geração de vídeo (TTS, render, finalize) ou no formato do job.
- Mudanças na API pública (`/api/v1`) ou na API interna (`/internal/v1`) além do necessário para o orquestrador.
- Migrações de banco de dados.
- Refatoração do supervisor, jobs, ou modelos existentes.
- Suporte a múltiplas GPUs ou balanceamento entre VMs.
- Dashboard ou UI para acompanhamento da VM Verda.
- Monitoramento ou alertas além dos logs do orquestrador.

## Proposta de implementacao

### 1. Importação do PR

Criar branch `feat/verda-auto-gpu` a partir de `cbb451a` (homolog). Incorporar os commits do PR #8 (`f26fcbda...`) via cherry-pick ou merge. Resolver conflitos se houver (espera-se apenas nos arquivos que o PR já toca).

### 2. Orquestrador Verda (novo módulo)

Criar `apps/orchestrator/` (ou dentro de `apps/worker/src/avatar_worker/verda.py`) com:

- **VerdaOrchestrator**: classe que periodicamente consulta a API interna (`/internal/v1/claim` com kinds `video` apenas, ou consulta SQL direta) para detectar jobs `queued`.
- **Provisionamento**: chamada HTTP/gRPC a uma API de hypervisor (a definir) para criar VM com specs GPU, imagem worker, montagem do disco persistente `/models`.
- **Monitoramento**: health check da VM (ping no worker ou heartbeat indireto via API).
- **Shutdown**: quando fila vazia por N segundos (config `VERDA_IDLE_SHUTDOWN_SECONDS`), envia comando de desligamento para o hypervisor, preservando o disco de boot.
- **Variáveis de ambiente**: `VERDA_API_URL`, `VERDA_TOKEN`, `VERDA_PROVISION_COMMAND` (script ou endpoint), `VERDA_IDLE_SHUTDOWN_SECONDS`, `VERDA_MODELS_DISK_ID`.

### 3. Alterações no worker/supervisor

Pequena alteração em `apps/worker/src/avatar_worker/supervisor.py` para que, ao detectar fila vazia por múltiplas pollagens consecutivas, envie um sinal (ex.: arquivo de flag `/tmp/verda-idle` ou chamada a endpoint local) para o orquestrador.

Ou, alternativamente, o orquestrador faz polling na API (`/api/v1/worker-status` e/ou `GET /internal/v1/jobs?status=queued`). Esta abordagem é preferível por ser desacoplada: o worker não precisa saber que está numa VM efêmera.

### 4. Infra/Compose

- `infra/compose/docker-compose.verda.yml`: define o serviço do orquestrador (pode rodar na VPS CPU ou num agente leve).
- `infra/compose/docker-compose.worker-release.yml`: imagem worker referenciada por digest.
- `infra/compose/docker-compose.release.yml`: já existe, ajustar se necessário para incluir o orquestrador.

### 5. Scripts

- `infra/scripts/verda-provision.sh`: script chamado pelo orquestrador para criar a VM.
- `infra/scripts/verda-shutdown.sh`: script para encerrar a VM.

### 6. Pipeline de release

- Build da imagem worker com tag semântica e sha256, registro no.env.example.
- Executar `bash infra/scripts/check-release.sh --role worker --supervisor-image <img>`.
- Publicar manifestos atualizados para HOMOLOG, validar, promover para PROD.

## Modulos e arquivos relacionados

| Caminho | Tipo de impacto | Motivo | Confianca |
|---|---|---|---|
| `apps/worker/src/avatar_worker/supervisor.py` | alteração | Pode receber sinal para desligar quando fila vazia; ou nenhuma alteração se polling externo | alta |
| `apps/worker/src/avatar_worker/video.py` | nenhum (fora do escopo) | Pipeline de geração não muda | alta |
| `apps/worker/pyproject.toml` | alteração | Dependências novas do orquestrador (httpx, schedule) | media |
| `apps/worker/tests/test_supervisor.py` | alteração | Testes para o novo comportamento idle | alta |
| `infra/compose/docker-compose.worker-release.yml` | alteração | Imagem worker com novo digest | alta |
| `infra/compose/docker-compose.release.yml` | alteração | Pode incluir orquestrador | media |
| `infra/compose/.env.example` | alteração | Novas variáveis do orquestrador Verda | alta |
| `infra/scripts/check-release.sh` | alteração | Validação da nova config | baixa |
| `infra/scripts/verda-provision.sh` | criação | Script de provisionamento VM | media |
| `infra/scripts/verda-shutdown.sh` | criação | Script de desligamento VM | media |
| `apps/api/src/avatar_api/internal_v1.py` | nenhum | API interna não precisa mudar (já expõe claim) | alta |
| `apps/api/src/avatar_api/jobs.py` | nenhum | Lógica de fila permanece igual | alta |
| `apps/orchestrator/` (novo) | criação | Módulo do orquestrador Verda | baixa |

## Mudancas de banco

Nenhuma. O orquestrador pode consultar `video_jobs` via API interna existente (`/internal/v1/claim`). Não há necessidade de novas tabelas ou colunas.

## Mudancas de API

Nenhuma na API pública (`/api/v1`). A API interna (`/internal/v1`) já expõe `POST /claim` que pode ser usada pelo orquestrador para detectar jobs pendentes (204 = fila vazia). Se necessário, criar endpoint `GET /internal/v1/queue-depth` para consulta leve de profundidade da fila.

## Riscos

- **API de hypervisor não definida**: a task não especifica qual API será usada para provisionar a VM Verda. Isso pode travar a implementação. Premissa: existe um endpoint REST ou script SSH que cria a VM.
- **Tempo de boot da VM**: se a VM demorar > lease_seconds (120s), o job pode ser reivindicado por outro worker ou expirar. O orquestrador precisa criar a VM antes ou estender o lease inicial.
- **Concorrência**: múltiplos jobs chegando enquanto a VM está subindo podem ser reivindicados por um worker que ainda não existe, falhar e entrar em retry. O orquestrador deve garantir que a VM esteja pronta antes do primeiro lease expirar.
- **Disco de modelos**: o disco /models precisa ser preservado entre ciclos mas montado como somente leitura no worker (`:ro` no compose). Validar que o hypervisor suporta esse attachment.
- **Shutdown abrupto**: se o worker for encerrado durante um processamento, o job volta para a fila via `sweep_expired_leases` com retry. É seguro mas gera atraso.
- **Regressão**: a alteração não deve quebrar o worker em setup manual (sem orquestrador). O orquestrador deve ser opcional, ativado por config.

## Testes sugeridos

### Unitários

- Testar lógica de decisão do orquestrador: detecta job pendente, não cria VM duplicada, desliga após idle.
- Testar que o supervisor existente continua funcionando sem o orquestrador presente.

### Integração

- Testar ciclo: criar job via API, verificar que orquestrador provisiona VM (mock do hypervisor), worker faz claim e completa, orquestrador desliga.
- Testar idle: fila vazia por N segundos, orquestrador chama shutdown.
- Testar concorrência: job criado durante boot da VM, lease expira, job volta para fila, worker eventualmente processa.

### End-to-end / manuais

- Em DEV: provisionar VM Verda real, confirmar heartbeat do worker, submeter job, baixar MP4, verificar exclusão da VM com disco preservado.
- Validar que `/models` do ciclo anterior está íntegro e não houve redownload.

### Comandos provaveis

```bash
# Testes do worker (incluindo supervisor)
uv run --frozen pytest apps/worker/tests/test_supervisor.py -v
# Testes do orquestrador (se criado)
uv run --frozen pytest apps/orchestrator/tests/ -v
# Lint
ruff check apps/worker/src apps/orchestrator/src
# Typecheck (se pyright configurado)
# Build imagem worker
docker build -f infra/docker/worker.Dockerfile -t avatar-worker:pr-8 .
# Validação de release
bash infra/scripts/check-release.sh --role worker --supervisor-image avatar-worker:pr-8
```

> Nota: comandos inferidos com base em `pyproject.toml` (pytest, ruff) e `mise.toml` (uv). Não há evidência de script typecheck ou de build único no projeto.

## Criterios de conclusao

- [ ] Código do PR #8 importado e compilando sem erros.
- [ ] Orquestrador criado: detecta jobs pendentes, provisiona VM, monitora, desliga em idle.
- [ ] Worker existente não quebrado (testes de supervisor passam).
- [ ] Variáveis de ambiente documentadas em `.env.example`.
- [ ] Release worker validado com `check-release.sh`.
- [ ] Ciclo real validado em DEV: criação de VM, processamento de job, download MP4, exclusão com disco preservado.
- [ ] SHA e manifestos registrados para HOMOLOG.
- [ ] Promoção para PROD após validação em HOMOLOG.

## Duvidas

1. **API de hypervisor**: qual é o endpoint/script para criar/destruir a VM Verda? É uma API REST, CLI (OpenStack, Proxmox, AWS EC2, algo custom)? Qual o mecanismo de autenticação?
2. **Identificação do disco de modelos**: qual é o identificador do disco persistente `/models`? Como ele é anexado à VM existente?
3. **Rede entre VPS**: a VM Verda precisa alcançar a API na VPS CPU por HTTP (túnel SSH, rede interna, IP público)?
4. **Worker image registry**: onde a imagem docker do worker é armazenada? Docker Hub, GHCR, registro privado? O orquestrador precisa do pull URL.
5. **VERDA_IDLE_SHUTDOWN_SECONDS**: qual o valor adequado para evitar shut down/up frequente? Sugestão inicial: 300s (5 min).
6. **Profundidade da fila**: existe ou deve-se criar um endpoint `GET /internal/v1/queue-depth` para o orquestrador consultar sem precisar fazer claim (que altera estado)?