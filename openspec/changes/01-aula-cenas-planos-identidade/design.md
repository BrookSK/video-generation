# Design

## Context

O M001 entregou painel, API, fila com lease e heartbeat, worker GPU (TTS, render e finalize com FFmpeg) e supervisor CPU para preparo de assets (`asset_prepare`). A videoaula de demolição provou que planos curtos, corte entre médio e close e abertura com identidade dão cara de curso. O close veio de um render com enquadramento fechado, não de ampliação digital.

## Goals / Non-Goals

**Goals:**
- Aula com várias cenas, plano por cena e um único arquivo final com abertura e encerramento.
- Reaproveitar o pipeline GPU sem mudança de receita. Cada cena é um job comum.
- Montagem só em CPU, com FFmpeg real também nos testes.

**Non-Goals:**
- Legenda, tópicos, imagens e trilha (change 02).
- Exposição de aulas na API pública.
- Transições além do corte seco.

## Decisions

### Aula como agregado de cenas com jobs filhos
`lessons` guarda avatar, cenário, formato, `music_enabled`, identidade congelada (logo e cores), estado, arquivo final, erro e datas. `lesson_scenes` guarda posição única por aula, texto, `shot` (`medio` ou `close`), `topics` (JSONB, vazio nesta change), `image_file_id` anulável e o job filho. `video_jobs` ganha `lesson_id`, `lesson_position` e `shot` (padrão `medio`). Ao criar a aula, a API grava aula, cenas e jobs filhos na mesma transação antes do `202`. A GPU não sabe que o job pertence a uma aula.

Estados da aula: `queued` enquanto há cena na fila ou em processamento; `assembling` quando todas as cenas estão `ready` e a montagem foi enfileirada; `ready` com o arquivo final publicado; `failed` se uma cena ou a montagem falhar em definitivo. Não se monta aula com cena faltando.

Rejeitado: um job único com todas as cenas. Prende a GPU, refaz tudo a cada retry e mistura montagem com inferência.

### Montagem como tarefa `lesson_assemble` no supervisor CPU
Na mesma transação que publica a última cena `ready`, a API trava a aula (`FOR UPDATE`) e insere `lesson_assemble_tasks` com `ON CONFLICT DO NOTHING` por `lesson_id`. A tarefa usa a fila existente: claim por tipo, lease, heartbeat, até três tentativas e publicação só pela tentativa vigente. O supervisor CPU aceita `lesson_assemble` em `WORKER_KINDS`, e a configuração recusa `video` junto de `lesson_assemble`. O worker GPU nunca recebe a montagem.

Rejeitado: montar no worker GPU depois da última cena. Ocupa a máquina paga por hora.

### Close como segundo enquadramento do cenário
`scenes.composition` ganha a chave opcional `close` com 9:16 e 16:9 (escala de 0,3 a 2,5, base de 0,5 a 2,5). O job filho leva `shot` e a composição usa o enquadramento correspondente. Cenário sem close salvo recebe um padrão derivado do médio: escala 1,6 vezes a do médio, limitada a 2,5, mesmo x, base ajustada para manter o topo da cabeça na altura do médio. Jobs avulsos continuam em `medio`.

Rejeitado: ampliar o vídeo do plano médio na montagem. Perde definição no render de 480p.

### Identidade visual única
`brand_identity` tem uma linha (CHECK `id = 1`) com logo (PNG ou JPEG), cor de fundo e cor de destaque em `#RRGGBB`, autor e data, e `music_file_id` anulável (usado na change 02). Arquivos são `stored_files` imutáveis; trocar cria arquivo novo e vale para as aulas criadas depois. A aula copia os IDs e as cores vigentes na criação, para a montagem e o retry usarem os mesmos insumos.

### Abertura, encerramento e arquivo final
Abertura e encerramento têm 3 s cada: fundo na cor de fundo, logo centralizado sem ampliar além do tamanho original, faixa na cor de destaque, fade de 0,5 s na entrada e na saída, áudio silencioso AAC 48 kHz. As cenas entram na ordem da posição com corte seco. Saída H.264 `yuv420p`, AAC 48 kHz, 25 fps CFR, `+faststart`, 1080x1920 ou 1920x1080. Cena com resolução diferente do formato é recusada, nunca escalada. Antes de publicar, `ffprobe` confere resolução, codecs, presença de áudio e duração esperada (3 s + soma das cenas + 3 s, tolerância de um quadro por junção). Falha vira `OUTPUT_INVALID` com mensagem em português. FFmpeg roda sem shell, sem `hwaccel` nem `nvenc`, com `CUDA_VISIBLE_DEVICES` vazio.

### API pública e jobs avulsos inalterados
A aula existe só no painel. O histórico de vídeos avulsos lista só jobs sem `lesson_id`. Limites: 2 a 12 cenas por aula e o limite de fala por job já vigente.

## Risks / Trade-offs

- Prazo curto (semana de 26/10): sem mudança no pipeline de inferência e com montagem mínima nesta change.
- Uma aula de muitas cenas consome mais GPU que um vídeo único. O custo por cena é medido na change 04 com os renders de 21/10.

## Dependências do cliente

- Logo e cores do cliente para a tela Identidade. Para os testes, usar materiais sintéticos.
