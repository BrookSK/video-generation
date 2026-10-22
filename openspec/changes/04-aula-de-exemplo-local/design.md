# Design

## Context

Pacote privado: `~/Developer/video-generation-amostras/p06-roteiro-rafael-20261021/`. Ele tem os renders nativos 896x448 (`renders/<cena>/out/avatar_16x9.mp4`), os WAVs aprovados (`gpu/jobs/<cena>/in/speech.wav`), o roteiro com as falas de cada cena (`docs/homologacao/P06-ROTEIRO-RAFAEL.md`), as medições de sincronia (`qc/SINCRONIA.json` e `qc/cena-*-sync.json`) e o status da fila na GPU com início e fim de cada render (`renders/_remoto/status.json`). A v2 entregue ao cliente usou a receita A e o atraso de vídeo por cena medido pelo SyncNet.

## Goals / Non-Goals

**Goals:**
- Aula de exemplo gerada pela montagem da plataforma, não por script avulso.
- Tempo de GPU por cena registrado a partir de medição real.

**Non-Goals:**
- Novos renders ou qualquer uso de GPU.
- Publicação da aula para o cliente pelo desenvolvedor. O Felipe decide o envio.

## Decisions

### Cenas a partir dos renders existentes
Cada plano da receita A passa pela finalização da plataforma (`finalize`) com o WAV aprovado, gerando o MP4 de cena em 1920x1080, como um job de cena geraria. O atraso de vídeo por cena da v2 é mantido, e a sincronia de cada cena finalizada é conferida de novo com o SyncNet (`qc/scripts/sync.py`), com resultado de 0 quadros como na v2. Esses MP4s entram como cenas prontas de uma aula criada pelo painel local, e a montagem roda pelo supervisor CPU.

### Conteúdo da aula
O texto de cada cena é a fala literal do roteiro. Tópicos curtos tirados do roteiro, uma captura de tela sintética numa cena, logo e cores sintéticos e uma trilha de licença livre ou sintética, até o cliente enviar os materiais dele.

### Tempo de GPU por cena
Para cada cena, a duração do render vem de início e fim em `renders/_remoto/status.json`, ao lado da duração do áudio da cena. O registro mostra segundos de GPU por segundo de vídeo e o total da aula, com a GPU e o perfil usados (2x H200, receita A, 4 passos).

## Risks / Trade-offs

- Logo, cores e trilha do exemplo não são os do cliente. O registro deixa isso claro.
- Os tempos vêm da H200. Em outra GPU o tempo muda; o registro informa a máquina.

## Dependências do cliente

- Logo, cores e trilha reais para uma versão final do exemplo, se o cliente quiser.
