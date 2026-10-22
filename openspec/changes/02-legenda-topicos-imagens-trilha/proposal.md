# Proposal

## Why

A change 01 entrega a aula com cenas, planos e identidade, mas sem os elementos que dão cara de curso e ajudam quem assiste sem som. O cliente pediu legenda, tópicos na tela, imagem do sistema durante a explicação e trilha de fundo.

## What Changes

- Legenda automática com o texto literal de cada cena, sincronizada pelo áudio gerado.
- Até 5 tópicos por cena, escritos na tela durante a cena.
- Imagem opcional por cena (JPEG, PNG ou WebP). Durante a cena, a imagem ocupa a área principal e o apresentador vai para um quadro menor no canto.
- Trilha de fundo da identidade (MP3, WAV, M4A ou OGG, até 20 MB), em volume baixo, que abaixa sob a fala. A aula pode desligar a trilha.
- Painel: tópicos, imagem e trilha ligada ou desligada na Nova aula, e upload da trilha na tela Identidade.

Fora de escopo: legenda gerada por reconhecimento de fala, trilha ou banco de imagens fornecidos pelo sistema, animação de tópicos, build de produção (change 03) e aula de exemplo (change 04).

## Capabilities

### New Capabilities

Nenhuma.

### Modified Capabilities

- `lessons`: legenda, tópicos, imagem por cena e trilha de fundo na montagem.
- `brand-identity`: trilha de fundo opcional na identidade.

## Impact

- Usa as colunas criadas na change 01 (`lesson_scenes.topics`, `lesson_scenes.image_file_id`, `lessons.music_enabled`, `brand_identity.music_file_id`), sem tabela nova.
- Worker: desenho de textos com Pillow e fonte OFL versionada, overlays por cena, imagem com o apresentador em quadro menor e trilha com ducking no módulo de montagem.
- API: upload e validação de trilha e imagens, limites de tópicos. `docs/api/openapi.json` regerado.
- Requisitos do escopo M002 atendidos: REQ-022, REQ-023, REQ-024, REQ-026, DAT-008, BR-007 e o risco RSK-008.
