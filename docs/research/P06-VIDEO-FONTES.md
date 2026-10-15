# P06 — fontes sobre movimento, sincronia e estabilidade visual

Pesquisa de **15/10/2026**. Escopo: fontes primárias, exemplos dos autores e comparação
com o código local. Nenhum peso foi baixado, nenhuma inferência foi executada e nenhuma
receita de produção foi alterada nesta pesquisa. **P06 continua incompleta.**

A evidência é forte para contratos de entrada e propagação dos parâmetros no código.
É limitada para a qualidade que obteremos com nossos materiais em pt-BR. Demos e
benchmarks dos autores não substituem um ensaio local com o WAV exato revisado.

## 1. O que a comparação atual permite concluir

O [registro local de qualidade](../homologacao/P06-QUALIDADE.md) documenta um vídeo de
25,96 s, nativo 448 × 832 e ampliado para 1080 × 1920. O avatar consumiu 2.304,575 s e
atingiu 49.328 MiB de VRAM. Esses números pertencem àquela execução; não são orçamento
garantido para outra GPU, resolução ou perfil.

O nosso caminho usa foto, áudio e prompt. O [piloto](../../apps/worker/src/avatar_worker/pilot.py)
compõe pessoa e fundo com Pillow antes de salvar `render_input.png`. O
[adaptador](../../apps/worker/runtimes/avatar/avatar_stage.py) usa essa imagem em
`cond_video`; não recebe trajetória de corpo nem vídeo de atuação. O modelo gera o
quadro inteiro, incluindo o cenário composto. Assim, composição estática antes do
modelo não garante cenário estático depois dele.

A [receita](../models/RECIPE-v1.json) pede movimentos sutis e também proíbe gestos.
A foto de busto tem ombros cortados. **Inferência de engenharia:** são restrições
plausíveis para o pouco movimento observado. Reduzir a escala dessa foto não recupera
braços ou tronco que não estão nos pixels de origem. Ainda não demonstramos quanto
cabe à foto, ao prompt, ao schedule ou ao modelo.

## 2. Como os autores obtêm e controlam movimento

### InfiniteTalk: distinguir foto de vídeo de referência

O trabalho principal é *sparse-frame video dubbing*: quadros de um vídeo fornecem
identidade, gestos de referência e trajetória de câmera; o modelo adapta movimentos ao
novo áudio. A animação a partir de uma única imagem também existe, mas não recebe essa
atuação de referência. O paper usa contexto temporal para continuidade entre chunks
e condicionamento suave, em vez de prometer cópia rígida de cada pixel.
Fontes: [paper v1, 19/08/2025](https://arxiv.org/html/2508.14033v1),
[página dos autores](https://meigen-ai.github.io/InfiniteTalk/).

Li dois exemplos reais do **mesmo commit usado pelo projeto**, `50aa0a94`:

| Exemplo dos autores | Entrada e intenção | Consequência para nossa comparação |
|---|---|---|
| [single_example_image.json](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/examples/single_example_image.json) | Foto `ref_image.png`, áudio e descrição de uma cantora expressiva em estúdio, com microfone e fones. | Há uma cena visual compatível com a ação. Não é um teste de apresentar ombros completos a partir de um recorte de busto. |
| [single_example_video.json](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/examples/single_example_video.json) | `ref_video.mp4`, áudio e descrição curta de uma pessoa falando. | O vídeo fornece informação temporal que nossa foto não fornece. |

### Inspeção de demos publicadas, além do README

Baixei os arquivos indicados no HTML da página oficial, seção `identity`, em 15/10/2026.
O HTML identifica explicitamente as entradas de imagem e vídeo. Os tamanhos abaixo
são dos **arquivos publicados**, sem prova de resolução nativa de inferência.

| Papel no HTML | URL publicada | ffprobe |
|---|---|---|
| I2V: imagem e resultado | [images/0.png](https://meigen-ai.github.io/InfiniteTalk/images/0.png), [videos/0.mp4](https://meigen-ai.github.io/InfiniteTalk/videos/0.mp4) | Vídeo: 16,56 s; 1280×704; 25 FPS; H.264. |
| V2V: vídeo de entrada | [videos/2.mp4](https://meigen-ai.github.io/InfiniteTalk/videos/2.mp4) | 33,272 s; 1920×1080; 30 FPS; H.264. |
| V2V: resultado adjacente | [videos/1.mp4](https://meigen-ai.github.io/InfiniteTalk/videos/1.mp4) | 27,16 s; 1280×704; 25 FPS; H.264. |

**Observação visual própria:** na I2V há duas figuras ilustradas, com tronco e braços
já desenhados; seis quadros mostram mudanças de mãos, cabeça e expressão. Não é um
caso de pessoa fotográfica única. Na V2V humana, a fonte já contém ombros, antebraços,
mãos e gestos com um celular. O resultado também varia braços/mãos; parede, faixa de
luz e sombras permanecem reconhecíveis nos quadros amostrados. As durações diferem:
quadros no mesmo segundo não constituem alinhamento de atuação. Não avaliei áudio,
sincronia labial ou naturalidade temporal a partir dessas grades.

Cópias, hashes, ffprobe, horários dos quadros e comandos ficam no diretório privado
`video-generation-amostras/p06-pesquisa-naturalidade-20261015/demos-autores`, fora do
repositório. O HTML não informa seed, steps ou pós-processamento por demo. Há curadoria
dos autores. O rodapé limita o material exibido a pesquisa acadêmica não comercial;
direitos individuais não foram verificados. **Somente referência interna, não material
entregável do produto.** [Página e rodapé](https://meigen-ai.github.io/InfiniteTalk/).

Para câmera e fundo, o paper reconhece que InfiniteTalk sozinho não reproduz movimentos
sutis de câmera com exatidão. SDEdit melhora esse controle; Uni3C teve dificuldade em
preservar o fundo no experimento publicado. Isso sustenta um tradeoff entre liberdade
de movimento e aderência à referência, não uma garantia de fundo imóvel.
[Paper, seção 4.2](https://arxiv.org/html/2508.14033v1#S4.SS2).

O README recomenda áudio CFG conforme o perfil: sem LoRA, texto 5/áudio 4; com LoRA,
texto 1/áudio 2. Declara LightX2V em quatro passos e FusionX em oito. Também alerta para
deriva de cor/identidade em vídeos longos e para SDEdit versus controle de câmera.
Não aumentar áudio CFG indiscriminadamente usando a faixa de outro perfil.
[README fixado](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/README.md#L182-L208).

MultiTalk é a base anterior, com foto, áudio e prompt. Seus autores dizem que reduzir
passos pode preservar a sincronia labial enquanto piora movimento e qualidade visual;
recomendam chunks de 81 quadros para aderência ao prompt. Isso demonstra que sincronia
e movimento devem ser julgados separadamente. Não prova o mesmo efeito quantitativo
no nosso InfiniteTalk com LoRA.
[MultiTalk, dicas de inferência](https://github.com/MeiGen-AI/MultiTalk/blob/c1ad84009b99ed36c97ab18e4517ca5f98692438/README.md#-quick-inference).

### Foto e plano precisam corresponder à tarefa

Não há uma regra universal de ocupar 70% da imagem com o rosto. O Hallo original
recomenda imagem quadrada, rosto frontal com menos de 30° de rotação e rosto ocupando
50–70%; também restringe o áudio recomendado a inglês. É uma receita de retrato,
não uma prescrição para gerar gestos de braços em pt-BR.
[Hallo, preparo de dados](https://github.com/fudan-generative-vision/hallo/blob/8fd7c572a3d43c2a9c1a5473219ce4fc1b6e3ed2/README.md#-prepare-inference-data).

Em contraste, HunyuanVideo-Avatar declara retrato, meio corpo e corpo inteiro. Seu
[CSV de exemplo](https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar/blob/8c31d0d489df8418fa36a2a709ebdf0b47c7bf06/assets/test.csv)
combina fotos de pessoas sentadas, em pé ou com instrumento e descrições compatíveis
com a cena. Wan-S2V apresenta exemplos com ações explícitas de corpo e ambiente.
Esses exemplos evidenciam o papel da cena de entrada e da ação descrita; não medem
a taxa de acerto para nossa pessoa/fundo/áudio.
[Wan-S2V, exemplos oficiais](https://humanaigc.github.io/wan-s2v-webpage/).

**Proposta local:** boca visível, rosto nítido, iluminação coerente com o cenário e
ombros completos para testar movimentos de ombro. Para braços/mãos, usar uma fonte
que já mostre esses membros e espaço para o movimento. Manter o plano de busto e
pedir grandes gestos torna o teste dependente de invenção de anatomia.

## 3. Achado verificável: `sample_shift` fica implícito

O adaptador local repassa steps, guias, `motion_frame` e LoRA, mas não repassa
`sample_shift` nem `base_seed`. Não basta acrescentar essas chaves à receita: o
adaptador atual não as lê. Ensaio exige CLI upstream direto ou overlay privado,
com origem e hash registrados; isso não é uma alteração proposta de produção já validada.

| Campo | Perfil local / comportamento esperado do código fixado |
|---|---|
| Steps | `4`, repassado como `sampling_steps`. |
| LoRA | LightX2V rank32, escala `1.0`, hash conferido pelo adaptador. O pipeline aplica `WanLoraWrapper`. |
| CFG | Texto `1.0`, áudio `2.0`, repassados e usados na predição guiada. Texto 1 ainda usa o contexto de texto condicional. |
| `sample_shift` | Omitido. O CLI resolve para **7 em 480p** e **11 em 720p**. |
| `base_seed` | Omitido. O CLI tem default **42**; a omissão não implica seed aleatória. |
| `motion_frame` | `9`. São quadros finais reaproveitados como contexto do próximo chunk, não um controle de amplitude corporal. |

Referências exatas: [adaptador local, build_args](../../apps/worker/runtimes/avatar/avatar_stage.py),
[defaults do CLI, linhas 38–55](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/generate_infinitetalk.py#L38-L55),
[seed e flags](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/generate_infinitetalk.py#L171-L208),
[propagação ao pipeline](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/generate_infinitetalk.py#L628-L641),
[LoRA no construtor](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/generate_infinitetalk.py#L525-L539),
[aplicação da LoRA](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/wan/multitalk.py#L239-L243),
[CFG](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/wan/multitalk.py#L752-L763),
[contexto temporal](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/wan/multitalk.py#L799-L805).

O [exemplo LoRA do README](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/README.md#L300-L320)
passa `sample_shift=2`, mas o comando mostrado é **FusionX em oito passos**. A frase
anterior permite LightX2V em quatro. Logo, testar 2 com nossa LightX2V é uma hipótese
fundada nesse exemplo, **não um valor ótimo demonstrado para esse checkpoint**.
A docstring interna ainda menciona 3 para 480p, divergindo do default efetivo do CLI.

O código não usa um ajuste genérico `denoise=0..1`: cria timesteps de 1000 até 1,
acrescenta 0, aplica `t' = shift*t/(1+(shift-1)*t)` com `t` normalizado e atualiza
o latent por `noise_pred*dt`. SDEdit e `sample_shift` não são o mesmo mecanismo.
O CLI/adaptador usados não expõem um parâmetro genérico de denoise ou uma flag SDEdit;
esse caminho exigiria uma implementação de ensaio própria.
[Transformação](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/wan/multitalk.py#L95-L104),
[schedule](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/wan/multitalk.py#L638-L643).

Cálculo ilustrativo desse código, sem executar modelo, arredondado a três casas:

| Quatro passos | Timesteps após transformação, incluindo término |
|---|---|
| Shift 7 | `1000 → 933.427 → 778.296 → 6.958 → 0` |
| Shift 2 | `1000 → 800.240 → 500.750 → 1.998 → 0` |

É uma diferença material de integração. **A pesquisa não demonstrou sua causalidade
no vídeo existente.** Registrar o `Namespace` resolvido na próxima execução elimina
a dependência de inferir defaults a partir do código.

Guias do próprio LightX2V também vinculam modelos destilados a configuração e lista
de timesteps específicas. Seus números de velocidade pertencem ao runtime deles;
não devem ser transferidos para nosso pipeline apenas porque a LoRA tem esse nome.
[Guia oficial Wan2.1 14B](https://github.com/ModelTC/LightX2V/blob/main/examples/BeginnerGuide/EN/Wan21-14B.md).

## 4. Alternativas e a tarefa que realmente resolvem

As opções abaixo têm código e/ou pesos públicos. Não foram instaladas nem testadas
nesta pesquisa. A coluna de recurso reproduz requisitos dos autores, sem estimativa
de custo da nossa implantação.

| Opção | Entrada e movimento | Recursos, controles e limite relevante |
|---|---|---|
| **Wan2.2-S2V-14B** | Foto + áudio + prompt; pose de vídeo opcional. Pode gerar meio corpo/corpo inteiro. | README: 480/720p, comando single GPU com pelo menos 80 GB; `--pose_video`, `--num_clip`, `--start_from_ref`. Config fixa 40 passos, shift 3 e guia 4,5. Trocar só o Wan2.1 dentro do nosso adapter não implementa esse pipeline. [README](https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/README.md#run-speech-to-video-generation), [config S2V](https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/configs/wan_s2v_14B.py). |
| **HunyuanVideo-Avatar** | Foto + áudio + descrição; emoções e cenas com mais de uma pessoa. Propõe dinâmica também no fundo. | Exemplo com 50 passos. README: mínimo 24 GB para 704×768×129f, muito lento; recomenda 96 GB. Perfil low-VRAM usa FP8/offload, portanto não equivale ao nosso bf16. Não é garantia de fundo estável. [README](https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar/blob/8c31d0d489df8418fa36a2a709ebdf0b47c7bf06/README.md). |
| **LivePortrait** | Foto/vídeo fonte + vídeo/template de movimento. A atuação vem do driving; concatenar áudio não cria sincronia nova por si. | Guia pede driving quadrado, cabeça em foco, pouco movimento de ombros e primeiro quadro frontal neutro. Útil para controlar retrato; não substitui geração corporal a partir de áudio. Tem suporte Apple Silicon, com alerta de lentidão dos autores. [Guia oficial](https://github.com/KlingAIResearch/LivePortrait/blob/9b294b3d0536135442ea73cb01e6cb3ca7029dd3/readme.md#driving-video-auto-cropping-). |
| **MuseTalk 1.5** | Vídeo + áudio; altera região facial. Corpo e cenário vêm do vídeo base. | Região facial 256×256; `bbox_shift` influencia o resultado. Os autores propõem gerar primeiro o movimento em outro sistema e depois sincronizar. Reconhecem jitter e perda de detalhes de identidade. Há exemplos multilíngues, sem prova específica de pt-BR para nosso caso. [README](https://github.com/TMElyralab/MuseTalk/blob/0a89dec45a0192b824e3cf4daf96c239440c5ed8/README.md). |
| **LatentSync 1.6** | Vídeo + áudio; dublagem por edição facial, não geração de gestos novos. | Modelo 512×512, mínimo anunciado de 18 GB. Guia: 20–50 passos; guidance 1–3, com mais sincronia versus risco de distorção/jitter. Pode conservar uma atuação boa já existente, mas não resolve um corpo imóvel de origem. [README](https://github.com/bytedance/LatentSync/blob/a229c3948406bc2cf6eaf4873e662e70c6a04746/README.md). |
| **Hallo original** | Foto de retrato + áudio. Controles de pose/face/lábio. | Enquadramento restrito e recomendação de inglês; não é a primeira alternativa para nosso pt-BR/meio corpo. [README](https://github.com/fudan-generative-vision/hallo/blob/8fd7c572a3d43c2a9c1a5473219ce4fc1b6e3ed2/README.md). |

Atualização pertinente da mesma equipe: o README do InfiniteTalk anuncia
**LongCat-Video-Avatar 1.5 em 21/05/2026**, com novo encoder e alegações de maior
estabilidade. É uma pista para avaliação futura, não evidência independente em pt-BR
nem justificativa para abandonar a ablação curta do pipeline já instalado.
[Anúncio dos autores](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/README.md#-latest-news).

## 5. Ensaios mínimos que podem refutar hipóteses

Esta é uma sequência com pontos de parada, não uma fila para gastar automaticamente.
O responsável pela operação define janela e custo antes de cada execução.

1. **Controle sem GPU.** Conferir foto original, alfa, `canvas.png`, `render_input.png`
   e bucket. Identificar ombros cortados, objetos já presentes no fundo e escala real
   do rosto. Se o problema já existe no input, não classificá-lo como invenção do modelo.
2. **Par de schedule.** Mesma imagem, WAV exato/hash, prompt, seed explícita 42,
   steps 4, LightX2V/escala e CFG 1/2. Comparar somente `--sample_shift 7` versus
   `--sample_shift 2`. Um trecho curto e completo de fala, de até aproximadamente um
   chunk, reduz o primeiro custo; confirmar depois o vencedor em múltiplos chunks.
   A/B com resultados próximos não permite declarar causa a partir de um único par.
3. **Prompt.** Reutilizar o resultado de controle anterior e trocar apenas o prompt
   pela [variante positiva existente](../models/calibration/variants.json): pequenos
   acenos, inclinações e ombros naturais, câmera/fundo estáveis, mãos abaixo do quadro.
   Não trocar fundo, escala e texto ao mesmo tempo. Melhora aqui refuta a tese de que
   o modelo é incapaz de produzir qualquer presença corporal com aquela foto.
4. **Foto/plano, se ainda necessário.** Comparar uma fonte da mesma pessoa com ombros
   completos, se disponível, mantendo o restante. Uma segunda identidade ou uma foto
   com cenário totalmente diferente confunde o teste. Encolher o recorte anterior
   testa composição; não testa disponibilidade de anatomia.
5. **Passos, sob demanda.** Se a qualidade continuar insuficiente, comparar 4 versus
   8 com a mesma LoRA e demais condições. Yong Zhang, autor correspondente, sugeriu
   experimentar mais passos em resposta a um resultado LightX2V ruim em 02/09/2025;
   isso não fornece um ótimo universal. Um controle sem LoRA/40 passos é outra
   comparação de perfil completo, mais cara, não uma alteração isolada de steps.
   [Resposta no issue 58](https://github.com/MeiGen-AI/InfiniteTalk/issues/58).
6. **Só então ampliar o escopo.** Ensaiar 720p nativo para detalhe, ou V2V/pose para
   movimento controlado. Ambos exigem contrato de entrada e medição próprios. Uma
   exportação ampliada para 1080p não responde à pergunta sobre resolução nativa.

Para o par de schedule, a diferença de CLI proposta é somente:

```text
controle: --sample_steps 4 --sample_shift 7 --base_seed 42
variante: --sample_steps 4 --sample_shift 2 --base_seed 42
comuns:   --sample_text_guide_scale 1 --sample_audio_guide_scale 2 --motion_frame 9
```

O restante deve ser o mesmo comando preparado a partir do request local, incluindo
LoRA e seu hash. Guardar overlay/hash, imagem Docker por digest, `Namespace` resolvido,
inputs/hashes, log, vídeo nativo, final, tempo e VRAM. Reutilizar o WAV revisado evita
confundir outra síntese TTS com mudança visual. Seed fixa ajuda o controle, mas não é
garantia de resultado idêntico entre hardware, kernels ou versões.
[Nota oficial de reprodutibilidade do PyTorch](https://docs.pytorch.org/docs/2.14/notes/randomness.html).

Julgar os vídeos em reprodução: sincronia em início/meio/fim, identidade, movimento de
cabeça/ombros, mãos/oclusões e pontos fixos do cenário. Separar atraso global de áudio
de erro de formato de boca. Um score de SyncNet auxilia o diagnóstico, mas seu limiar
não deve ser inventado para pt-BR; o próprio LatentSync pede pré-processamento compatível
antes da avaliação. [Guia de avaliação](https://github.com/bytedance/LatentSync/blob/a229c3948406bc2cf6eaf4873e662e70c6a04746/README.md#-evaluation).

Se o requisito for cenário preservado com exatidão, comparar futuramente composição
após a animação ou dublagem de um vídeo já estável. São mudanças de arquitetura:
máscara temporal, bordas, sombras e oclusões precisam de avaliação. Prompt de câmera
estática sozinho é um condicionamento, não uma trava de pixels.

## 6. Rastreabilidade e limites das fontes

Revisões de `main` resolvidas na API pública do GitHub durante esta pesquisa:

| Repositório | Revisão consultada | Data UTC do commit |
|---|---|---|
| [InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk/commit/50aa0a94184315407a991ae804d9b58d6d311ba8) | `50aa0a94` | 22/05/2026 |
| [MultiTalk](https://github.com/MeiGen-AI/MultiTalk/commit/c1ad84009b99ed36c97ab18e4517ca5f98692438) | `c1ad8400` | 22/05/2026 |
| [Wan2.2](https://github.com/Wan-Video/Wan2.2/commit/1ea34ff48f87168174e12956e200b1d908b1c5ff) | `1ea34ff4` | 21/09/2026 |
| [HunyuanVideo-Avatar](https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar/commit/8c31d0d489df8418fa36a2a709ebdf0b47c7bf06) | `8c31d0d4` | 16/12/2025 |
| [LivePortrait](https://github.com/KlingAIResearch/LivePortrait/commit/9b294b3d0536135442ea73cb01e6cb3ca7029dd3) | `9b294b3d` | 01/06/2026 |
| [MuseTalk](https://github.com/TMElyralab/MuseTalk/commit/0a89dec45a0192b824e3cf4daf96c239440c5ed8) | `0a89dec4` | 26/09/2025 |
| [LatentSync](https://github.com/bytedance/LatentSync/commit/a229c3948406bc2cf6eaf4873e662e70c6a04746) | `a229c394` | 20/06/2025 |
| [Hallo](https://github.com/fudan-generative-vision/hallo/commit/8fd7c572a3d43c2a9c1a5473219ce4fc1b6e3ed2) | `8fd7c572` | 14/09/2024 |

Datas de referência: InfiniteTalk paper v1, 19/08/2025; Wan-S2V, lançamento de
26/08/2025; HunyuanVideo-Avatar, código/pesos de 28/05/2025; MuseTalk 1.5, 28/03/2025;
LatentSync 1.6, 11/06/2025. A data do commit acima não é a data do lançamento do modelo.

Os guias externos do Wan em DingTalk e o link de technical report da página de código
não entregaram conteúdo legível nesta consulta. Para requisitos/flags usei README,
config e página dos próprios autores, sem preencher lacunas por blogs.

Não localizei, nas fontes consultadas, um protocolo reproduzível que demonstre nossa
fala em pt-BR, pessoa, fundo, resolução e orçamento. As demos são selecionadas pelos
autores; não conhecemos tentativas descartadas nem uma taxa de sucesso para nosso caso.
O próximo resultado útil é uma comparação controlada, não uma promessa baseada no nome
do modelo ou em um vídeo de demonstração.
