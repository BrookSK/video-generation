# P06 — roteiro da videoaula com o Rafael

Preparo de 21/10/2026. O cliente elogiou o vídeo 2, do Rafael, como o mais natural
dos três enviados em 21/10. Pediu o roteiro de videoaula com esse personagem. O
roteiro é o PDF de demolição descrito em [retorno da videoaula](P06-RETORNO-VIDEOAULA.md):
seis cenas, até 60 s, 16:9. O cliente também disse que B-roll, trilha, legendas e
demais "enfeites" ficam para depois. A prioridade continua sendo a naturalidade
do apresentador.

Este documento define falas, voz, planos e renders. A pesquisa e a análise crítica
que sustentam as escolhas estão em [especialistas em avatar open source](../research/P06-ESPECIALISTAS-20261021.md).
Não houve inferência de vídeo nesta etapa: a Verda tem US$ 0,20.

## Falas

As falas são as do PDF, sem reescrita. Uma única mudança vale só para a entrada
do TTS: "os EPIs" vira "os é-pê-is". Sem isso, a sigla foi lida como palavra
inglesa ("apps" na transcrição de 1 em 5 tomadas). A legenda futura mantém "EPIs".

| Cena | Fala | Palavras | Alvo no PDF | Fala medida |
|---|---|---:|---:|---:|
| 1 | Olá! Seja bem-vindo ao nosso treinamento. Hoje você vai conhecer cinco cuidados essenciais antes de iniciar uma demolição. | 18 | 0–8 s | 8,00 s |
| 2 | Primeiro: confira o projeto e a avaliação técnica. Nunca remova paredes, pilares ou vigas sem autorização e análise de um profissional habilitado. | 22 | 8–19 s | 9,35 s |
| 3 | Segundo: identifique as instalações elétricas, hidráulicas e de gás. Os sistemas afetados devem ser isolados com segurança antes do serviço. | 20 | 19–29 s | 9,14 s |
| 4 | Terceiro: proteja pisos, esquadrias e áreas comuns. Isole o ambiente, sinalize os riscos e controle a circulação de pessoas. | 19 | 29–39 s | 8,96 s |
| 5 | Quarto: verifique os EPIs, as ferramentas e os riscos de poeira e queda. Quinto: defina a sequência de demolição e a retirada segura do entulho. | 25 | 39–51 s | 9,89 s |
| 6 | Lembre-se: uma demolição segura começa antes da primeira ferramenta. Siga o plano aprovado e libere a atividade somente após as verificações! | 21 | 51–60 s | 9,19 s |

Com 0,5 s entre cenas, a narração completa tem **57,02 s**. Não houve aceleração,
time-stretch ou corte de palavra. Os tempos do PDF eram alvo; a fala real fica
mais curta nas cenas 2 a 5 e mais longa na 6. A redistribuição é consequência da
leitura natural, não uma decisão de conteúdo.

## Voz

Receita idêntica à do Rafael aprovado: Qwen3-TTS Base 1.7B MLX bf16, revisão
`a6eb4f68e4b056f1215157bb696209bc82a6db48`, referência Faber/OHF CC0
(`f0475c62…e48`), temperatura 0,9, top-p 1, top-k 50, repetition penalty 1,5 e
512 tokens. Ambiente recriado com freeze idêntico ao de 16/10, rede bloqueada na
síntese. Uma chamada por cena, todas com EOS real.

As cenas 4, 5 e 6 tiveram tomadas extras com sementes 11, 23, 37 e 41. A seleção
usou a transcrição Whisper large-v3-turbo como filtro de defeitos e a altura média
mais próxima do Rafael aprovado (154 Hz):

| Cena | Tomada | Motivo |
|---|---|---|
| 1, 2, 3 | semente da receita | Transcrição correta |
| 4 | semente 37 | Única sem "issole" ou "protaja" |
| 5 | grafia fonética, semente da receita | "EPIs" correto nas cinco tomadas fonéticas |
| 6 | semente 37 | A original transcreveu "libera" |

A transcrição da narração montada corresponde ao roteiro inteiro. A variação de
entonação por cena fica entre 3,5 e 4,2 semitons, perto da referência (4,0). A
altura média varia entre 150 e 173 Hz. Essa diferença pode aparecer nos cortes.
**Voz aprovada pelo usuário em 21/10, por escuta da narração completa.** Ele notou
um leve corte no final de algumas palavras e considerou aceitável. Transcrição e F0
serviram só como filtro de defeitos.

A síntese rodou no Mac, com MLX, pelo mesmo caminho da voz do Rafael aprovada em
16/10. Isso mantém a voz igual e não usa GPU paga. Não é a voz de produção: na
plataforma, o TTS roda no worker CUDA, cuja integração com o Qwen ainda não foi
homologada. O MLX força repetition penalty 1,5 e o CUDA oficial usa 1,05, então a
mesma fala pode soar diferente. Essa comparação fica para a homologação do worker.

## Planos e enquadramento

Um render por cena. A cena 5 é dividida no "Quinto:", porque tem dois tópicos.
São sete renders de 4 a 10 s, abaixo do limite de 40 s (`max_frame_num` 1000) e
da zona de deriva de cor do InfiniteTalk. O corte entre cenas troca a imagem a
cada 4 a 10 s, como fazem editores de talking head.

| Render | Fala | Plano | Seed |
|---|---|---|---:|
| 1 | cena 1 | médio, cintura para cima | 42 |
| 2 | cena 2 | close médio, peito para cima | 11 |
| 3 | cena 3 | médio | 23 |
| 4 | cena 4 | close médio | 37 |
| 5a | cena 5 até "queda." | médio | 41 |
| 5b | cena 5 desde "Quinto:" | close médio | 53 |
| 6 | cena 6 | médio | 67 |

O diagnóstico do vídeo aprovado mostra que as mãos abrem nos ataques de fala depois
de pausa e se juntam nas pausas e nos trechos de menor energia. A pose de mãos
unidas é o repouso do modelo, não da foto. O enquadramento da cintura para cima
deixa esse repouso perto da borda e mostra o gesto quando ele sobe. O close médio
dobra o tamanho do rosto em relação ao vertical atual, que tem cerca de 60 px de
largura no nativo. Não usar punch-in digital sobre o nativo de 448 px.

## Imagem 16:9

O bucket 480p não tem 16:9: 1920×1080 cai em 896×448 (2:1), com corte central de
11% da altura. A imagem precisa chegar em 2:1 exato, 1792×896 ou 896×448.

Preparo: recortar o PNG do Rafael (`assets/homem-02/avatar.png`, 941×1672) da
cabeça à cintura e do topo ao peito, e expandir as laterais por outpainting até
2:1. O rosto, a roupa e o corpo ficam com os pixels originais; só o escritório é
inventado. Crop puro vira close de testa a queixo; barras pretas seriam animadas
pelo modelo. Na finalização, escalar 2:1 para 2160×1080 e cortar 120 px de cada
lado, sem barras.

Pendente: ferramenta de edição de imagem. O Rafael foi criado com o `image_gen` do
Codex; a mesma ferramenta faz o outpainting. Alternativa open source: FLUX.1 Fill
ou Qwen-Image-Edit na própria GPU. Inspecionar mãos, cotovelos e margem antes da
inferência. Uma pose de repouso assimétrica (uma mão mais baixa) ajuda a quebrar a
simetria de âncora de telejornal.

## Prompt

Com text CFG 1 o prompt entra só no ramo condicional e o negativo é inerte. Mesmo
prompt curto, positivo e sem negações nos sete renders. A direção por cena vem do
áudio, da imagem e da seed.

> A man in a dark gray button-up shirt explains a workplace safety topic to the
> camera in a warm, confident and conversational way, with natural head movement,
> lively facial expressions and relaxed hand gestures. Static eye-level camera,
> bright modern office, soft daylight.

O prompt anterior pedia "without repeatedly clasping the hands". O encoder T5 não
entende negação de forma confiável; a frase nomeia justamente o gesto indesejado.

## Entradas prontas

Pacote privado: `video-generation-amostras/p06-roteiro-rafael-20261021/voz/`.

- `selecao/cena-N.render.wav`: fala da cena com 0,1 s antes e 0,4 s de silêncio
  real depois. O InfiniteTalk espelha a cauda do áudio quando o último bloco passa
  do fim; o silêncio evita boca falhando no fim. Cortar a cauda na finalização.
- `selecao/narracao-completa.wav` e `narracao-completa-escuta.mp3`: escuta contínua.
- `selecao/SELECAO.json`: fonte, SHA-256 e quadros a 25 fps de cada cena.
- `raw/` e `takes/`: todas as tomadas, requests, logs e resultados.

A cena 5 foi cortada no silêncio de 5,19 a 5,77 s, antes do "Quinto:":
`cena-5a.render.wav` (5,64 s, 141 quadros) e `cena-5b.render.wav` (4,62 s,
116 quadros). As duas metades transcrevem corretamente.

## Situação

Pronto: falas, voz das seis cenas, plano de renders, prompt e campos de seed,
shift e cor no stage de avatar. Pendente: imagem 16:9,
recarga da Verda, reconstrução autorizada da imagem do worker com o stage novo e
a execução do [plano de testes](../research/P06-ESPECIALISTAS-20261021.md#plano-de-testes).
Não há aceite de naturalidade nem do formato 16:9.
