# Design

## Context

A change 01 montou abertura, cenas e encerramento com FFmpeg no supervisor CPU. O FFmpeg local não tem `drawtext` nem `ass`, e a prova local precisa ser igual à produção. O texto de cada cena é literal e não pode ser trocado na legenda.

## Goals / Non-Goals

**Goals:**
- Legenda que confere palavra por palavra com o texto da cena.
- Tópicos, imagem e trilha aplicados na montagem, sem GPU.

**Non-Goals:**
- Tempo por palavra vindo de modelo de reconhecimento de fala.
- Estilos de legenda configuráveis pela equipe.

## Decisions

### Texto na tela desenhado com Pillow e aplicado com `overlay`
Legenda e tópicos viram PNGs transparentes desenhados com Pillow e uma fonte OFL versionada no repositório. O FFmpeg aplica cada PNG com `overlay` e `enable='between(t,a,b)'`. Layout fixo por formato: legenda na faixa inferior com caixa de fundo; tópicos à direita no 16:9 e acima da legenda no 9:16; cores dos textos e das caixas vêm da identidade congelada na aula. Quebra de linha pela largura medida com a fonte; legenda com até duas linhas por trecho.

Rejeitado: `ass` e `drawtext`. Indisponíveis no FFmpeg local.

### Tempo da legenda a partir do áudio, texto sempre literal
O texto da cena é dividido em frases pela pontuação e cada frase em trechos de até duas linhas, cortando só em fronteira de palavra. O áudio da cena passa por `silencedetect`; os intervalos de fala são casados com as frases em ordem e, dentro de cada frase, o tempo é dividido pelos caracteres dos trechos. Se o número de intervalos não casar com o de frases, o tempo da cena inteira é dividido por caracteres. O texto exibido é sempre o texto da cena.

Rejeitado: timestamps por palavra de um modelo de reconhecimento. Modelo e pesos novos e risco de trocar palavras.

### Imagem da cena em tela principal
Durante uma cena com imagem, a imagem ocupa a área principal, ajustada sem distorção sobre fundo na cor da identidade, e o vídeo do apresentador vai para um quadro menor no canto, mantendo fala e legenda. Cenas sem imagem mostram o apresentador em tela cheia. Imagens aceitas: JPEG, PNG e WebP, com o mesmo validador do upload de avatar.

### Trilha com ducking
A trilha da identidade é repetida ou cortada até a duração da aula, com volume base baixo, `sidechaincompress` usando a voz como controle para abaixar sob a fala e saída suave no encerramento. Arquivo MP3, WAV, M4A ou OGG de até 20 MB, guardado como arquivo imutável. A montagem confere a trilha com `ffprobe`; arquivo ilegível falha a aula com mensagem em português. A aula grava se a trilha está ligada e o ID do arquivo vigente na criação.

### Limites
Até 5 tópicos por cena, com até 80 caracteres cada. Uma imagem por cena.

## Risks / Trade-offs

- O tempo da legenda por caracteres é aproximado dentro da frase. O casamento com os silêncios mantém cada trecho dentro da frase falada.
- A licença da trilha é responsabilidade do cliente.

## Dependências do cliente

- Trilha de fundo e imagens das aulas, enviadas pela equipe no painel. Para os testes, usar áudio e imagens sintéticos.
- Escolha da fonte OFL fica com o desenvolvedor, versionada no repositório com a licença.
