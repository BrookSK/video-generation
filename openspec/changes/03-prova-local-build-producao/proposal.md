# Proposal

## Why

As changes 01 e 02 provam a aula com a stack de desenvolvimento. Antes da entrega, o sistema inteiro precisa gerar e entregar uma aula completa e um vídeo avulso com as imagens de produção, rodando local, para que nada dependa de ambiente de desenvolvimento.

## What Changes

- A imagem `supervisor-cpu` passa a ter FFmpeg.
- O Compose CPU passa a aceitar `lesson_assemble` em `WORKER_KINDS`.
- O guard de release (`infra/scripts/check-release.sh`) confere FFmpeg no supervisor CPU e a configuração da montagem.
- Jornada de aceite com o Compose de produção local: identidade com trilha, aula de quatro cenas com todos os elementos e um vídeo avulso 9:16, ambos baixados íntegros.
- `docs/operacao/USO.md` ganha a seção de aulas para a equipe.

Fora de escopo: instalação no ambiente do cliente (pendente do M001), GPU real e Verda. TTS e render têm dublê só nas fronteiras de inferência, como no M001.

## Capabilities

### New Capabilities

Nenhuma.

### Modified Capabilities

- `lessons`: montagem disponível no build de produção.

## Impact

- `infra/docker/worker.Dockerfile` (estágio `supervisor-cpu`), `infra/compose/docker-compose.cpu.yml`, `infra/compose/.env.example` e `infra/scripts/check-release.sh`.
- Documentação de uso em `docs/operacao/USO.md`.
- Requisitos do escopo M002 atendidos: FLW-005 e FLW-001 de ponta a ponta no build de produção.
