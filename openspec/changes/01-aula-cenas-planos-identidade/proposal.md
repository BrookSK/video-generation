# Proposal

## Why

A equipe do cliente quer produzir aulas institucionais e de treinamento na própria plataforma, no padrão da videoaula de demolição do Rafael. Hoje a plataforma gera um vídeo por texto, sem cenas, sem troca de plano e sem identidade visual. A videoaula de demolição foi montada fora da plataforma. Esta change cria a base da aula: identidade visual do cliente, aula com várias cenas, plano médio ou close por cena e um único arquivo final com abertura e encerramento.

## What Changes

- Tela Identidade no painel com logo e duas cores (fundo e destaque) do cliente.
- Cenário com dois enquadramentos por formato, plano médio e close, ajustados no editor com prévia.
- Tela Nova aula com 2 a 12 cenas ordenadas, cada uma com texto falado e plano.
- Cada cena gera um job de vídeo comum na GPU, sem mudança na receita.
- Quando todas as cenas ficam prontas, o supervisor CPU monta abertura, cenas em ordem com corte seco e encerramento num único MP4.
- Tela da aula com estado de cada cena e da montagem, player e download.

Fora de escopo nesta change: legenda, tópicos, imagens e trilha (change 02), build de produção (change 03) e aula de exemplo (change 04). Fora do ciclo: narração contínua refeita em GPU, produção da série de aulas pelo desenvolvedor, trabalho contínuo e instalação no ambiente do cliente.

## Capabilities

### New Capabilities

- `brand-identity`: logo e cores do cliente usados na abertura e no encerramento das aulas.
- `lessons`: aula com cenas ordenadas, plano por cena, jobs filhos, montagem em CPU e download.

### Modified Capabilities

Nenhuma com spec no OpenSpec. O cadastro de cenário do M001 ganha o enquadramento close, coberto em `lessons`.

## Impact

- Migração aditiva `0004_aulas_e_identidade`: `brand_identity`, `lessons`, `lesson_scenes`, `lesson_assemble_tasks` e as colunas `lesson_id`, `lesson_position` e `shot` em `video_jobs`.
- Rotas novas em `/panel` e em `/internal/v1/lesson-tasks`. `docs/api/openapi.json` regerado. `/api/v1` sem mudança.
- Worker: composição por plano e módulo novo de montagem com FFmpeg. Supervisor CPU aceita `lesson_assemble`.
- Painel: telas Identidade, Nova aula, Aulas e Aula, e editor de cenário com dois planos.
- Requisitos do escopo M002 atendidos: REQ-020, REQ-021, REQ-025, NFR-005, DAT-006, DAT-007, com REQ-001 a REQ-005, ERR-001 e BR-001 herdados do M001.
