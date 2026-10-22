# Tasks

## 1. Imagens e Compose

- [ ] 1.1 Instalar `ffmpeg` do Debian no estágio `supervisor-cpu` de `infra/docker/worker.Dockerfile`; verificar construindo a imagem e rodando `ffmpeg -version` e `ffprobe -version` dentro dela
- [ ] 1.2 Mudar o padrão de `WORKER_KINDS` em `infra/compose/docker-compose.cpu.yml` e em `infra/compose/.env.example` para `asset_prepare,lesson_assemble`; verificar com `docker compose config` mostrando o valor
- [ ] 1.3 Fazer `infra/scripts/check-release.sh` conferir FFmpeg e FFprobe na imagem do supervisor CPU e recusar `video` junto de `lesson_assemble`; verificar com `bash infra/scripts/check-release.sh` passando e com um `.env` de teste com configuração mista bloqueando o release

## 2. Jornada de aceite

- [ ] 2.1 Criar a jornada `@M002-03` com o Compose de produção local e dublê só nas fronteiras de TTS e render: entrar no painel, cadastrar identidade e trilha, gerar uma aula de quatro cenas com troca de plano, legenda, tópicos, uma imagem e trilha, gerar um vídeo avulso 9:16 e baixar os dois arquivos; conferir com `ffprobe` perfil, duração e presença de áudio dos dois; verificar com o comando da jornada documentado na própria tarefa

## 3. Documentação

- [ ] 3.1 Acrescentar a `docs/operacao/USO.md` a seção de aulas: cadastrar identidade e trilha, criar aula, planos médio e close, tópicos, imagem, acompanhar e baixar, limites e o que fazer quando uma cena falha; verificar seguindo o texto na stack local
- [ ] 3.2 Rodar a verificação completa: testes de `apps/api`, `apps/worker` (`-m "not gpu"`) e `apps/web`, `npm --prefix apps/web run typecheck`, `bash infra/scripts/check-release.sh` e as jornadas `@M002-01`, `@M002-02` e `@M002-03`, todos verdes
