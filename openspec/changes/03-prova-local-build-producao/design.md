# Design

## Context

O estágio `supervisor-cpu` do `worker.Dockerfile` parte de `python:3.12-slim` e hoje roda só `asset_prepare`, sem FFmpeg. O worker GPU já instala FFmpeg do Ubuntu. O `docker-compose.cpu.yml` define `WORKER_KINDS` com padrão `asset_prepare`.

## Goals / Non-Goals

**Goals:**
- Mesma montagem da prova local rodando nas imagens de produção.
- Guard de release que bloqueia imagem sem FFmpeg ou configuração mista.

**Non-Goals:**
- Publicar imagens em registro ou instalar no cliente.
- Mudar o worker GPU.

## Decisions

### FFmpeg do Debian no supervisor CPU
O estágio `supervisor-cpu` instala `ffmpeg` do Debian com `--no-install-recommends`. O guard roda `ffmpeg -version` e `ffprobe -version` dentro da imagem construída.

### `WORKER_KINDS` do Compose CPU
O padrão passa a `asset_prepare,lesson_assemble`. O guard recusa `video` junto de `lesson_assemble` no mesmo serviço, como o próprio supervisor já recusa.

### Jornada de aceite com Compose de produção
A jornada sobe o Compose de produção local (API, banco, painel, Caddy e supervisor CPU). TTS e render usam o mesmo dublê de fronteira das changes anteriores. Uma pessoa entra no painel, cadastra identidade e trilha, gera uma aula de quatro cenas com todos os elementos e um vídeo avulso 9:16, e baixa os dois arquivos. Os arquivos são conferidos com `ffprobe`.

## Risks / Trade-offs

- A imagem do supervisor fica maior com FFmpeg. Aceito: é a única forma de montar em CPU.
