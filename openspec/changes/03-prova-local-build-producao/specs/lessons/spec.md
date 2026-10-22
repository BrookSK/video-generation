# Spec Delta

## ADDED Requirements

### Requirement: Montagem no build de produção
As imagens de produção SHALL gerar e entregar uma aula completa e um vídeo avulso rodando local. O supervisor CPU de produção MUST ter FFmpeg e aceitar `lesson_assemble`, e o guard de release MUST bloquear imagem sem FFmpeg ou serviço com `video` e `lesson_assemble` juntos.

#### Scenario: Aula e vídeo avulso no build de produção
- **WHEN** uma pessoa usa o painel do Compose de produção local para cadastrar identidade e trilha, gerar uma aula de quatro cenas com todos os elementos e um vídeo avulso 9:16
- **THEN** os dois arquivos são baixados íntegros, no perfil de saída e com áudio

#### Scenario: Imagem sem FFmpeg
- **WHEN** o guard de release roda contra uma imagem de supervisor CPU sem FFmpeg
- **THEN** o release é bloqueado com mensagem

#### Scenario: Configuração mista
- **WHEN** o guard de release encontra `WORKER_KINDS` com `video` e `lesson_assemble` no mesmo serviço
- **THEN** o release é bloqueado com mensagem
