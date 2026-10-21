# P06 — o que os especialistas em avatar open source fazem

Pesquisa de 21/10/2026, depois do retorno do cliente sobre os vídeos de João, Rafael
e Marina. O cliente achou o Rafael o mais natural e pediu o roteiro de videoaula com
ele. A pergunta foi: o que os praticantes de modelos open source fazem para obter
naturalidade, e o que vale copiar para o nosso caso.

Três pesquisas paralelas cobriram modelos de vídeo, TTS e fluxo de produção. O
Fable fez a revisão crítica, com leitura do código fixado do InfiniteTalk. Não
houve inferência paga. O roteiro resultante está em [roteiro do Rafael](../homologacao/P06-ROTEIRO-RAFAEL.md).

## Diagnóstico do vídeo aprovado

Os quadros do Rafael (2 fps e a cada 6 quadros, 10 s) foram comparados com a
energia do áudio:

- Foto de entrada: mãos abertas e separadas, plano até as coxas, frontal.
- No vídeo, as mãos abrem nos ataques de fala depois de pausa (0–1 s, 2,4 s,
  5,0–6,0 s, 7,7–8,4 s). Elas se juntam em ponta nas pausas e nos trechos de menor
  energia, e ficam assim até a próxima frase.
- As fronteiras de bloco (3,24, 6,12 e 9,00 s) não explicam sozinhas: em 3,24 s as
  mãos já estavam unidas desde 2,9 s.
- A cabeça quase não muda de ângulo. A postura é simétrica, de âncora.
- O rosto tem cerca de 60 px de largura no nativo 448×832.

Conclusão: a pose unida é o repouso aprendido pelo modelo com a LoRA destilada,
não a pose da foto. O gesto nasce da estrutura de frases do áudio. Isso corrige a
hipótese de que cada bloco puxa o corpo de volta à foto.

A voz do Rafael tem variação de entonação de 4,15 semitons, contra 4,02 da
referência humana. A Marina tem 3,32, contra 4,87 da referência. A voz mais
expressiva coincide com o vídeo preferido. Há outros fatores que mudam junto
(audio CFG 2 contra 1, voz masculina), então não atribuir a preferência só à voz.

## Verificado no código fixado (50aa0a94)

- A cada bloco, a imagem de referência é reextraída de `cond_video`. Com uma PNG,
  todo bloco recebe a mesma foto, como latente do quadro 0 e como contexto CLIP.
- Com text CFG 1, o ramo sem condição usa o próprio prompt positivo. O negative
  prompt nunca entra. O stage já recusa `negative_prompt`.
- Defaults ativos que o stage não repassava: `base_seed` 42, `sample_shift` 7 em
  480p, `color_correction_strength` 1,0. Sem seed, um retake repete o vídeo.
- `max_frame_num` 1000 corta em 40 s sem erro.
- Quando o último bloco passa do fim, o áudio é espelhado. Os últimos quadros ficam
  vizinhos de áudio invertido.
- O áudio já é normalizado para −23 LUFS dentro do script.
- Buckets 480p: 1920×1080 cai em 896×448 (2:1), com corte central de 11%.
- `--scene_seg` só age com vídeo de entrada: detecta cortes, divide o áudio e gera
  um clipe por trecho. Equivale a jobs separados por cena.

## O que copiar

| Prática | Origem | Decisão |
|---|---|---|
| Um render por plano curto, com corte entre planos | HeyGen limita movimento customizado a 10 s; Argil e Synthesia trabalham por clipe; README do InfiniteTalk relata deriva de cor após ~1 min | Copiar. Sete renders de 4 a 10 s |
| Trocar a imagem a cada 3 a 8 s, alternar plano médio e close | [1of10](https://1of10.com/blog/what-is-a-jump-cut/), [Subscribr](https://subscribr.ai/youtube-strategy/editing-talking-head-videos-engaging), [Argil](https://docs.argil.ai/resources/editingtips.md) | Copiar, com renders próprios para o close |
| Close gerado de imagem fechada, sem zoom digital | Benchmark [OmniHuman](https://arxiv.org/html/2604.18326): qualidade cai do close para o plano aberto | Copiar. Punch-in sobre 448 px perde definição |
| Uma chamada de TTS por cena, mesma referência | [Qwen3-TTS #239](https://github.com/QwenLM/Qwen3-TTS/issues/239), guia de fine-tune do Qwen | Feito |
| Várias tomadas por cena e escolha de ouvido | Card do [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2), [arXiv 2502.04128](https://arxiv.org/html/2502.04128v2) | Feito para as cenas 4 a 6; falta a escuta |
| Grafia fonética de siglas só na entrada do TTS | Checklists de avatar ([diyai](https://diyai.io/ai-tools/video-generation/ai-talking-head-generator/)) citam siglas como falha típica | Feito: "EPIs" corrigido nas 5 tomadas |
| Silêncio curto no fim do áudio de render | [InfiniteTalk #146](https://github.com/MeiGen-AI/InfiniteTalk/issues/146) e o espelhamento visto no código | Feito: 0,4 s de cauda |
| Seed diferente por plano | Necessário para retakes, conferido no código | Implementado no stage |
| Prompt curto, positivo, com a roupa descrita | [Kijai #1780](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1780), [guia do MagiHuman](https://github.com/GAIR-NLP/daVinci-MagiHuman/blob/main/prompts/enhanced_prompt_design.md) | Copiar, sem esperar muito efeito com text CFG 1 |
| LoRA I2V rank64 com 6 passos | Workflow do Kijai; autor sugere mais passos ([#58](https://github.com/MeiGen-AI/InfiniteTalk/issues/58)) | Testar como pacote, depois da base |

## O que não copiar agora

| Prática | Motivo |
|---|---|
| Trocar para LongCat-Video-Avatar 1.5 | Novo runtime de 13,6B, VRAM não validada em A100 40 GB, sync pior no longo prazo ([Vorch](https://arxiv.org/html/2609.26117)). O InfiniteTalk tem o melhor sync e identidade entre os abertos, e é isso que o cliente vê na fala |
| V2V com keyframes de pose | O autor diz que o V2V não copia gestos ([#11](https://github.com/MeiGen-AI/InfiniteTalk/issues/11)). Cria conflito entre a referência nova e os motion frames |
| Controle de pose (UniAnimate, Wan2.2-S2V, VACE) | Outro runtime e uma atuação gravada que não temos. Wan2.2-S2V oficial pede 80 GB |
| Mais passos isolados | O supressor de movimento é a destilação. 6 a 8 passos custam 1,5 a 2 vezes, sem evidência de soltar o corpo |
| Investir em prompt de gesto | Com text CFG 1 o efeito é pequeno; negações não funcionam |
| Trocar de TTS agora | O Rafael tem a voz aprovada. VoxCPM2 (Apache) e Chatterbox pt-br V3 (MIT) ficam para A/B cego se a voz continuar dura |

## Juízo externo

A solução dos especialistas que mais se aplica não é um modelo novo. É a linguagem
de produção: planos curtos, cortes que trocam o enquadramento e áudio com frases
bem marcadas. Isso esconde o repouso repetido, limita a deriva e permite refazer só
o plano ruim. O cliente descreveu o que quer como "stories ou aula", que é
exatamente esse formato.

Os limites continuam. Gesto semântico (apontar para o que se fala) não é controlado
pelos frameworks atuais, segundo o autor ([#24](https://github.com/MeiGen-AI/InfiniteTalk/issues/24)).
O repouso de mãos unidas continuará aparecendo; o enquadramento só o torna menos
visível. Se, depois dos planos curtos, o cliente ainda achar a fala dura, o teste
mais barato e mais alinhado é uma atuação humana gravada e convertida para o timbre
aprovado (Chatterbox VC ou RVC, ambos MIT), com termo do locutor. O áudio é o que
dirige rosto e cabeça.

Ninguém do lado técnico ouviu os vídeos com som. A QA anterior foi por quadros e
SyncNet. Ouvir a narração e assistir aos renders em reprodução contínua é a etapa
mais barata e a que falta.

## Plano de testes

Custo por clipe de 10 s no perfil low VRAM da A100 40 GB: cerca de 23 min de
render e 3 min de preflight, US$ 0,67 a US$ 1,531/h. Teto proposto: US$ 15 de
compute, com uma VM, fila única e exclusão ao fim. O estouro anterior veio de VM
ociosa, não de render.

Antes da GPU, no Mac:

1. Escuta das seis cenas e da narração completa; trocar tomadas se necessário.
2. Imagem mestre 2:1 do Rafael por outpainting, nos dois enquadramentos.
3. Reconstrução da imagem do worker com o stage novo, mediante autorização.

Na GPU, uma variável por vez até a decisão:

| Etapa | Muda | Mantém | Custo estimado |
|---|---|---|---:|
| G1 | Imagem 16:9 plano médio, WAV aprovado de 10 s | Receita do Rafael | US$ 0,7 |
| G1b | `num_persistent_param_in_dit` maior, na mesma VM | G1 | US$ 0,1 a 0,4 |
| G2 | Áudio da cena 2 desta seleção | Imagem de G1 | US$ 0,7 |
| G3 | LoRA I2V rank64, 6 passos, shift do card | Insumos de G2 | US$ 0,9 |
| Decisão | Receita de G2 ou G3 | — | — |
| G4 | Sete renders da videoaula, seeds distintas | Receita escolhida | US$ 4,5 |
| Reserva | Retakes de 3 a 4 planos | — | US$ 3,5 |

Total estimado: US$ 10 a 13 com overhead de VM. G1b só vale se não der falta de
memória; se couber, reduz o tempo de render de todo o resto. G3 muda LoRA, passos e
shift juntos: é uma receita candidata, não uma ablação.

Critérios por render: integridade de mídia, mãos e rosto no quadro, sincronia por
SyncNet com controles, junções sem salto, cor estável entre planos. Critério final:
reprodução contínua com som pelo usuário e pelo cliente.

## Fontes e limites

As pesquisas usaram READMEs, issues e código dos autores, papers do arXiv, cards do
Hugging Face e guias de fornecedores com método explícito. O Reddit bloqueou o
acesso direto; só entraram relatos citados em issues do GitHub. Não há benchmark
independente de naturalidade em pt-BR para TTS nem métrica de repetição de gesto
entre modelos de vídeo. Não foi confirmado o shift recomendado pelo card da LoRA
I2V rank64 nem a licença comercial das demos do LongCat.
