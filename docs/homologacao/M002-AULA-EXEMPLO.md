# M002: aula de exemplo sobre os renders de 21/10

Montagem de 22/10/2026. A aula de exemplo usa as cenas reais da videoaula do Rafael
([roteiro e renders](P06-ROTEIRO-RAFAEL.md)) e passa pela montagem nova da plataforma:
abertura e encerramento com a identidade, troca de médio e close, legenda literal,
tópicos, uma imagem com o apresentador no quadro menor e trilha de fundo. Nenhuma GPU
foi usada nesta etapa. A montagem rodou no supervisor CPU da imagem de produção, com
FFmpeg, no Compose de produção local.

**Logo, cores, trilha e captura de tela são sintéticos.** O logo é um "E Exemplo"
desenhado no script, as cores são `#12324A` (fundo) e `#F2A541` (destaque), a trilha
é um laço de acordes gerado no script e a captura é um checklist fictício de
liberação. Nada disso é material do cliente. Uma versão final depende do logo, das
cores e da trilha que o cliente enviar.

## Arquivo

Fica só no pacote privado de amostras, fora do repositório:

`~/Developer/video-generation-amostras/p06-roteiro-rafael-20261021/aula-exemplo/aula-exemplo-m002-16x9.mp4`

| Campo | Valor |
|---|---|
| SHA-256 | `1092f56b3f9d722636d8a5d281e47f3befa240a3b644641fa838f8b49f3b7f33` |
| Tamanho | 13.943.573 bytes |
| Vídeo | H.264 High, yuv420p, 1920x1080, 25/1, 1568 quadros |
| Áudio | AAC, 48 kHz, estéreo |
| Duração | 62,72 s = 3 s de abertura + 56,72 s de cenas + 3 s de encerramento |
| Faststart | `moov` antes de `mdat` |
| Loudness integrada | -21,5 LUFS |

O arquivo decodifica do começo ao fim sem erro (`ffmpeg -xerror`). Ao lado dele
ficam o manifesto da montagem (`aula-exemplo-m002-manifest.json`), o registro da
criação (`aula-exemplo-m002.json`) e os scripts `preparar_cenas.py` e `montar_aula.py`.

## Como foi gerada

1. `preparar_cenas.py` passa cada render nativo 896x448 da receita A pela finalização
   da plataforma (`avatar_worker.finalize`) com o WAV aprovado, como um job de cena
   faria: 1920x1080, H.264/AAC, 25 FPS, faststart. Antes, aplica o atraso de vídeo da
   v2 (o primeiro quadro repetido 2 ou 3 vezes, conforme a cena).
2. `montar_aula.py` sobe `docker-compose.yml` + `docker-compose.cpu.yml` com o
   override de teste da jornada `@M002-03`, cria usuário, avatar, cenário, identidade,
   trilha e a aula pelo painel. Depois faz o papel do worker GPU só na fronteira do
   render: cada job de cena recebe o MP4 finalizado do passo 1. O recorte do avatar e
   a montagem rodam no supervisor CPU. No fim, baixa a aula e o manifesto e derruba o
   projeto com os volumes.

A aula tem 7 cenas, na ordem 1, 2, 3, 4, 5a, 5b, 6. A cena 5 do roteiro é dividida
no "Quinto:", como nos renders. Planos: médio, close, médio, close, médio, close,
médio. A captura de tela entra na cena 2.

## Legenda

O texto de cada cena é a fala literal do roteiro. A legenda de cada cena, com os
trechos juntados, é igual a esse texto palavra por palavra nas 7 cenas (18, 22, 20,
19, 13, 12 e 21 palavras). A grafia fonética do TTS ("é-pê-is") não entra: a legenda
mostra "EPIs".

O tempo da legenda veio das pausas da fala só na cena 1. Nas outras 6, o número de
pausas medidas não bateu com o número de trechos, e a montagem usou o tempo
proporcional aos caracteres, como previsto. Vale conferir assistindo se a troca de
trecho acompanha a fala nessas cenas.

## Sincronia por cena

SyncNet oficial em CPU (`qc/scripts/sync.py`) sobre os MP4s de cena já finalizados,
com o crop da v2 e controles de ±200 ms.

| Cena | Quadros | Offset | Confiança | Controles |
|---|---:|---:|---:|---|
| 1 | 209 | 0 | 4,05 | recuperados |
| 2 | 243 | 0 | 3,62 | recuperados |
| 3 | 238 | 0 | 4,54 | recuperados |
| 4 | 233 | 0 | 3,68 | recuperados |
| 5a | 141 | 0 | 4,71 | recuperados |
| 5b | 115 | 0 | 3,34 | recuperados |
| 6 | 239 | 0 | 4,26 | recuperados |

## Conferência sem som

- Quadros extraídos da abertura, de cada trecho de legenda e do encerramento:
  logo e cores na abertura e no encerramento, tópicos no canto superior direito,
  legenda embaixo, e na cena 2 a captura à esquerda com o apresentador no quadro
  menor e os tópicos abaixo dele.
- Trilha: -23 dB RMS na abertura sozinha. Dentro das cenas, subtraindo o áudio
  original de cada cena, a trilha fica por volta de -25 dB nas pausas e entre -32 e
  -38 dB sob a fala, com a voz a cerca de -20 dB. O valor sob a fala inclui o ruído
  de recodificação, então a trilha real é no máximo esse nível.

Falta assistir com som do começo ao fim: cortes entre cenas, entrada e saída da
trilha, tempo da legenda nas cenas por caracteres e a naturalidade geral.

## Tempo de GPU por cena

Render de 21/10 em 2x H200 SXM5 (Verda, FIN-02), receita A, 4 passos, uma fila por
GPU. "Job" é o tempo do container, de `renders/_remoto/status.json`; "Render" é o
tempo medido dentro do job, o mesmo da tabela do P06. Os dois incluem a carga do
modelo em cada job.

| Cena | GPU | Áudio (s) | Vídeo (s) | Job (s) | Render (s) | s de GPU por s de vídeo |
|---|---|---:|---:|---:|---:|---:|
| 1 | 0 | 8,40 | 8,36 | 704,4 | 702,6 | 84,3 |
| 2 | 1 | 9,75 | 9,72 | 802,6 | 800,7 | 82,6 |
| 3 | 0 | 9,54 | 9,52 | 653,9 | 653,3 | 68,7 |
| 4 | 1 | 9,36 | 9,32 | 658,9 | 658,4 | 70,7 |
| 5a | 0 | 5,64 | 5,64 | 452,1 | 451,6 | 80,2 |
| 5b | 1 | 4,62 | 4,60 | 459,8 | 459,3 | 100,0 |
| 6 | 0 | 9,59 | 9,56 | 701,3 | 700,8 | 73,4 |
| **Total** | | 56,89 | 56,72 | 4433,0 | 4426,7 | 78,2 |

As cenas 1 e 2 foram as primeiras de cada GPU (modelo frio). As cenas curtas pesam
mais por segundo porque a carga do modelo é fixa por job. O render extra 2-B
(699,3 s na GPU 1) não entra na aula.

Conferência com a fila: a GPU 1 somou 2620,6 s (cenas 2, 4, 5b e 2-B), igual à
duração total da fila, de 17:26:41 a 18:10:22 UTC. A GPU 0 somou 2511,7 s (cenas 1,
3, 5a e 6), igual ao intervalo entre o início da fila e o fim do seu último job.

Em outra GPU o tempo muda. Estes números valem para a H200 com a receita A.

## Prova da change 03

A stack de produção local (`docker-compose.yml` + `docker-compose.cpu.yml`) subiu
com as imagens dos Dockerfiles de produção. O supervisor CPU tem o FFmpeg 7.1.5 do
Debian e roda `asset_prepare` e `lesson_assemble`. A jornada `@M002-03` passou: aula
16:9 de 4 cenas com troca de plano, tópicos, imagem e trilha, mais um vídeo avulso
9:16, os dois baixados pelo painel com o perfil de saída conferido.
`check-release.sh --supervisor-image` recusa imagem sem FFmpeg e `.env` que junte
`video` e `lesson_assemble` no mesmo serviço. A instalação no ambiente do cliente
continua pendente do M001.
