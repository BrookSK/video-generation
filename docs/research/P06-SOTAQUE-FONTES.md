# P06 — sotaque brasileiro: causas, controles e limites

Pesquisa em 15/10/2026. Fontes primárias: código e documentação dos autores, model cards, artigo técnico e relatos identificados nos repositórios. Este documento não altera produção nem instala modelos. Complementa [P06-VOZ-FONTES.md](P06-VOZ-FONTES.md). Atualização após a escuta: o usuário rejeitou **Nova A/B, correspondentes a VoiceDesign L/M**. Não propor mais gerações VoiceDesign ou novas cláusulas de sotaque nesta rodada.

## O que o feedback permite concluir

O usuário considerou Qwen J, amostra 2, quase natural, mas percebeu português de Portugal no começo. Chatterbox F, amostra 4, ficou “mais ou menos”; outras amostras também pareceram portuguesas. Isso é evidência de percepção do usuário. Não identifica sozinho a origem do sotaque, nem reprova todos os caminhos desses modelos.

As duas amostras usam o mesmo áudio **sintético de Kokoro**, não uma gravação humana brasileira. O recorte retirou os primeiros **0,53 s**; a referência restante tem **11,145 s**, PCM mono de 24 kHz/16 bits. Portanto, 0,53 s é o trecho removido, não a duração fornecida ao modelo. A frase “Falo português do Brasil” faz parte da fala transcrita. No modo de clonagem, isso não equivale a uma instrução separada que force dialeto.

Evidência privada preservada em `video-generation-amostras/p06-pesquisa-naturalidade-20261015/experimentos/`, fora do Git:

| Item | Qwen J | Chatterbox F |
|---|---|---|
| Request | `inputs/qwen-J.request.json` | `inputs/prosody-F.request.json` e `prosody-F.config.json` |
| Referência | `models/references/sem-ola.wav`, SHA256 `fb086d17f8be82befaa50a367f17e536d906875f05dbe7cace02d570e299be1e` | A mesma referência e hash |
| Caminho | Qwen3-TTS 1.7B Base, bf16, MLX Audio 0.5.9, áudio + transcrição | Chatterbox 0.1.7 com pesos oficiais pt-BR, D001/policy v3, MPS |
| Idioma | `Portuguese` | `pt` |
| Sampler | seed 20261015, temperatura 0,9, top-p 1, top-k 50, repetition penalty efetiva 1,5 | seed 20261015, temperatura 0,8, CFG 0,3, exaggeration 0,4 |
| Saída | `out/qwen-J.wav`: 8,16 s; EOS observado | `out/prosody-F.wav`: 9,4 s; watermark detectado |
| Resultado e monitor | `out/qwen-J.result.json` e `.monitor.json` | `out/prosody-F.result.json` e `.monitor.json` |

O áudio original foi produzido com `lang_code='p'`, `pf_dora`, velocidade 1,0. Isso está em [voice_references.py](../../apps/worker/runtimes/voices/voice_references.py). Não há evidência aqui de troca acidental para um frontend português de Portugal. A referência sintética pode carregar prosódia, timbre ou articulação pouco naturais mesmo usando o frontend brasileiro. Esta última frase é uma hipótese, não uma análise auditiva nova.

## Qwen: idioma, dialeto e instrução são controles diferentes

### O token de idioma não distingue Brasil de Portugal

O config oficial de VoiceDesign contém `portuguese: 2071`, sem entradas `pt-br` e `pt-pt`. A conversão MLX usada no próximo ensaio preserva essa configuração. Pedir `Portuguese` seleciona o idioma disponível; o identificador não fixa uma variante nacional. Não inventar um token de dialeto nem passar `pt-BR` presumindo suporte. [Config oficial](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign/blob/5ecdb67327fd37bb2e042aab12ff7391903235d3/config.json), [config MLX](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16/blob/7d3824abff87e49756bb0f83fb5411de75d160c4/config.json).

O artigo apresenta WER de **1,526%** e similaridade de locutor **0,817** para 12Hz 1.7B Base na linha “Portuguese”. Não separa Brasil/Portugal nessa tabela. O teste de instruções publicado cobre chinês e inglês. Esses resultados não medem acerto de sotaque brasileiro nem garantem que uma descrição de dialeto será obedecida. [Artigo, tabelas 6 e 8](https://arxiv.org/html/2601.15621v1).

### Base: referência e ICL, sem `instruct` suportado

No Base, o caminho oficial normal usa áudio, transcrição e códigos acústicos da referência como contexto, além do embedding do locutor. Em `x_vector_only_mode=True`, ficam apenas os dados de embedding do locutor; texto e códigos da referência deixam de ser usados. São modos mutuamente exclusivos. O código documenta essa diferença, e o guia alerta para perda possível na qualidade da clonagem. Isso não demonstra que x-vector isolado elimine sotaque ou preserve a identidade com a mesma qualidade. [API oficial, linhas 355–455](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L355-L455), [guia de clonagem](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#voice-clone).

Há confirmação direta do colaborador `wangxiongts`, em 26/01/2026: o controle do Base 12Hz é instável e essa variante não suporta `instruct`. A promessa de um futuro modelo de edição 25Hz não deve ser tratada como capacidade já entregue no Base usado aqui. [Resposta oficial na issue 25](https://github.com/QwenLM/Qwen3-TTS/issues/25#issuecomment-3797751920).

Na cópia preservada de `setup/runtime-sources/qwen3_tts-mlx-audio-0.5.9.py`, linhas 1231–1255, a presença de `ref_audio`, `ref_text` e encoder escolhe ICL. Esse ramo não repassa `instruct`. O `generate` aceita `**kwargs`, mas não usa a flag oficial `x_vector_only_mode` para essa decisão. Copiar a flag do exemplo PyTorch para esse wrapper MLX não prova mudança de modo. O código precisaria de uma verificação específica antes de tal ensaio.

Para J, `ref_text` é a transcrição do recorte, incluindo a afirmação sobre falar português do Brasil. Acrescentar comandos não falados nessa transcrição criaria outra condição e deixaria de representar o áudio. A API exige transcrição em ICL; não a documenta como campo de persona. A alternativa verificável para instrução textual é usar a variante treinada para isso.

### VoiceDesign e CustomVoice: interface suportada, sotaque ainda por validar

VoiceDesign 1.7B recebe descrição de voz em `instruct`, além de texto e idioma. CustomVoice 1.7B oferece instruções para vozes predefinidas. As nove vozes documentadas são nativas de chinês, inglês, japonês ou coreano; nenhuma é apresentada como nativa brasileira. CustomVoice 0.6B não tem instruction control marcado na tabela oficial. Logo, a presença genérica de `instruct` numa assinatura não basta para equiparar variantes. [Tabela e vozes oficiais](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#released-models-description-and-download), [API de VoiceDesign/CustomVoice](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L635-L816).

Pedir uma voz que fale português brasileiro por descrição é um uso compatível com VoiceDesign. Não encontrei, nas fontes oficiais consultadas, uma garantia específica ou benchmark de controle Brasil versus Portugal. Os exemplos oficiais de descrição estão em inglês e chinês. Usar inglês no ensaio mantém proximidade com esses exemplos; não prova que escrever a descrição em português seja proibido. [Exemplo executável do autor](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/examples/test_model_12hz_voice_design.py).

O runtime MLX preservado também implementa esse caminho: linhas 1184–1203 passam `instruct` e `lang_code` para `generate_voice_design`. O config da revisão MLX `7d3824abff87e49756bb0f83fb5411de75d160c4` declara `tts_model_type='voice_design'`. A verificação aqui foi leitura de código/config, sem carregamento de pesos ou inferência. [Implementação MLX 0.5.9](https://github.com/Blaizzy/mlx-audio/blob/v0.5.9/mlx_audio/tts/models/qwen3_tts/qwen3_tts.py), [model card MLX](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16/tree/7d3824abff87e49756bb0f83fb5411de75d160c4).

## Referência brasileira: evidência útil e limites

Uma referência humana limpa, em português brasileiro e já aceita pelo usuário, permitiria testar a variável que ainda falta nos ensaios de clonagem. O motivo técnico é que ICL usa a fala de referência como contexto acústico e linguístico, não somente como rótulo de identidade. Os autores do Chatterbox também alertam que uma referência em outro idioma pode transferir sotaque. Isso apoia o teste, sem garantir que a referência humana vença o prior do modelo. [API ICL do Qwen](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L355-L390), [orientação oficial Chatterbox](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/README.md#original-chatterbox-tips).

Critério operacional proposto para essa gravação: uma pessoa, fala contínua, sem música, outras vozes, clipping ou reverberação forte; corte em limite de palavra; transcrição literal conferida; licença ou autorização de uso da voz registrada. Separar qualidade técnica do áudio de adequação do sotaque desejado. Esses são critérios do ensaio, não uma duração mínima universal comprovada pelos autores. A divulgação de clonagem em três segundos não significa que qualquer trecho de três segundos tenha a mesma qualidade.

| Evidência de vazamento de sotaque | O que foi realmente confirmado |
|---|---|
| Qwen discussão 332, aberta em 13/06/2026: usuário relata português europeu; resposta de 09/09 apenas reforça o pedido | Relato público compatível com a queixa local. Sem solução ou diagnóstico confirmado por mantenedor até esta consulta. [Discussão](https://github.com/QwenLM/Qwen3-TTS/discussions/332) |
| Qwen issue 134: inglês para italiano permanece americano; comentários citam alemão e fine-tune sem resolver | Relatos de usuários, encerramento por inatividade. Não demonstram que treinamento seja a única solução. [Issue](https://github.com/QwenLM/Qwen3-TTS/issues/134) |
| Chatterbox issue 281: demo parece brasileira, instalação local parece portuguesa; relatos com referência brasileira e palavras nasais | Relatos de 2025. Não são teste da revisão pt-BR V3 atual com nosso runtime. [Issue](https://github.com/resemble-ai/chatterbox/issues/281) |
| Chatterbox README: casar idioma da referência com o idioma pedido; `cfg_weight=0` pode mitigar transferência de sotaque entre idiomas | Orientação documentada pelos autores. Não é garantia de controle regional Brasil/Portugal. Também não remove toda a referência do modelo. [Guia](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/README.md#original-chatterbox-tips) |

Não há confirmação nessas fontes de que baixar temperatura, aumentar repetition penalty ou recortar apenas “Olá” corrija sotaque regional. Esses controles podem afetar outros comportamentos; não devem receber causalidade que o teste não demonstrou.

## Chatterbox e Kokoro: controles já disponíveis

**Chatterbox já está no fine-tune brasileiro oficial.** O card distingue `pt-BR` como locale e `pt` como identificador interno. A revisão atual `b3952f18bc2eaa72b9bd7c17d2c4653bcad4770d` é a mesma fixada no [MODEL_MANIFEST.json](../models/MODEL_MANIFEST.json), não um upgrade ainda ausente. O checkpoint `t3_pt_br.safetensors` tem SHA256 `074aaf65255eb9cb960288f7cc72e09d3b5008f6e0b14868c0d4e5b0bd7cbb6c`. O card declara MIT e descreve otimização brasileira; não publica uma precisão regional que substitua a escuta local. [Card fixado](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-pt-br/blob/b3952f18bc2eaa72b9bd7c17d2c4653bcad4770d/README.md).

O projeto adapta o carregamento dos arquivos V3 ao runtime 0.1.7 em [tts_stage.py](../../apps/worker/runtimes/tts/tts_stage.py). A variável disponível em F é a combinação concreta de checkpoint, implementação, referência e sampler. O resultado não pode ser generalizado como teste de qualquer instalação atual do Chatterbox.

**Kokoro tem um frontend brasileiro explícito.** No código, `p` mapeia para `pt-br`; o G2P usa `EspeakG2P`. O catálogo do autor inclui `pf_dora`, `pm_alex` e `pm_santa` em Brazilian Portuguese. Esse caminho permite examinar fonemas antes de sintetizar, inclusive com pipeline sem modelo. O rótulo brasileiro e o frontend correto não garantem prosódia humana nem todos os traços regionais. [Pipeline fixado](https://github.com/hexgrad/kokoro/blob/dfb907a02bba8152ca444717ca5d78747ccb4bec/kokoro/pipeline.py#L10-L60), [seleção de G2P](https://github.com/hexgrad/kokoro/blob/dfb907a02bba8152ca444717ca5d78747ccb4bec/kokoro/pipeline.py#L140-L144), [vozes oficiais](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/VOICES.md#brazilian-portuguese).

Kokoro 82M é menor e evita a etapa adicional de clonagem, mas sua referência já foi usada nos ensaios. Não proponho outro modelo pequeno nesta rodada. A licença dos pesos/código Kokoro e do Misaki é Apache-2.0; o frontend usa Phonemizer/eSpeak NG, cujos repositórios declaram GPL-3.0. Portanto, a descrição de distribuição da cadeia inteira precisa refletir essas dependências. [Pesos Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md), [licença Kokoro](https://github.com/hexgrad/kokoro/blob/dfb907a02bba8152ca444717ca5d78747ccb4bec/LICENSE), [Misaki e integração](https://github.com/hexgrad/misaki/blob/fba1236595f2d2bf21d414ba6e57d25256afada3/misaki/espeak.py#L1-L70), [licença Misaki](https://github.com/hexgrad/misaki/blob/fba1236595f2d2bf21d414ba6e57d25256afada3/LICENSE), [Phonemizer](https://github.com/bootphon/phonemizer/blob/8eac8d644fb90cb8aea58d9d9808c94040a69dad/LICENSE), [eSpeak NG](https://github.com/espeak-ng/espeak-ng/blob/ba90c8e9f440ad544f674a790bb5f53878b6ffc5/COPYING).

## Existe fine-tune Qwen brasileiro, mas não há correção pronta demonstrada

O pesquisador Thomaz Diniz publicou `QwenTTS/` em `acidente/fala_pb_checkpoints`, partindo do 1.7B Base para sotaque da Paraíba. O card registra 41.952 amostras, cerca de 44,8 h de áudio e checkpoints 5k/10k/15k. O agregador tem licença `mixed`, mas sua tabela declara **Apache-2.0 especificamente para QwenTTS/**. O corpus é proprietário e não acompanha o repositório. Não auditamos direitos individuais ou termos dos dados. [Card do conjunto](https://huggingface.co/acidente/fala_pb_checkpoints/blob/2a35881bcb7996d46533f88914c18b386b9d1ee3/README.md), [card Qwen](https://huggingface.co/acidente/fala_pb_checkpoints/blob/2a35881bcb7996d46533f88914c18b386b9d1ee3/QwenTTS/README.md).

A página do próprio autor relata **ausência de ganho perceptível no sotaque paraibano** em escuta informal, apesar da queda de loss e de aproximadamente três dias de treino. Ele registra uma diferença importante: baseline em clonagem, pós-treino em CustomVoice com slot treinado. Isso limita atribuir o resultado apenas aos pesos. É um caso de adaptação regional brasileira, não uma avaliação controlada Brasil versus Portugal e nem prova de que fine-tuning sempre falha. Não justifica assumir custo de treinamento agora. [Experimento 18, condições e resultados](https://thomazdiniz.github.io/fala_pb/18/).

O projeto Qwen oferece treino de locutor único e recomenda referência constante no conjunto para estabilidade. Não publica nesse guia uma receita validada de sotaque brasileiro ou estimativa de custo para nosso hardware. [Guia oficial de fine-tuning](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/finetuning/README.md). Nenhum peso desse experimento foi baixado nesta pesquisa.

## Ensaios: VoiceDesign encerrado e uma próxima comparação

### 1. VoiceDesign: par concluído e rejeitado pelo usuário

O coordenador executou o par L/M, apresentado como Nova A/B, com artefatos em `video-generation-amostras/p06-sotaque-20261015/out`. O usuário ouviu e informou que **nenhuma atende**. O desenho comparava descrição feminina genérica com a mesma descrição acrescida da cláusula brasileira, sem referência Kokoro. A avaliação negativa é feedback explícito do usuário; esta pesquisa não ouviu os WAVs nem atribuiu notas próprias.

Objetivo: verificar se a instrução específica altera a percepção do início e do restante da fala mantendo inteligibilidade e naturalidade. É um controle suportado pela interface e implementação de VoiceDesign. Um par com a mesma seed é um diagnóstico inicial: não mede taxa de sucesso, estabilidade entre seeds ou repetição em várias frases. O desenho também cria a voz por descrição; não preserva automaticamente a identidade de `pf_dora`. [Exemplo oficial](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/examples/test_model_12hz_voice_design.py), [implementação MLX](https://github.com/Blaizzy/mlx-audio/blob/v0.5.9/mlx_audio/tts/models/qwen3_tts/qwen3_tts.py).

O resultado não autoriza repetir cláusulas ou seeds para procurar uma amostra favorável. VoiceDesign permanece documentado como capacidade de interface que não atingiu o objetivo nesta comparação. O próximo controle usa uma gravação humana e o Base já disponível.

### 2. Base ICL: trocar a referência sintética por uma humana brasileira

Comparar `sem-ola.wav` com uma das gravações humanas públicas OHF descritas abaixo no **mesmo Qwen Base MLX já ensaiado**, cada uma com a própria transcrição literal. Manter texto de saída, seed, sampler e restante do runtime iguais a J. A autorização pública CC0 e a finalidade declarada de TTS permitem preparar esse controle sem exigir um novo contrato individual privado do locutor. A adequação da voz/sotaque continua sujeita à escuta do usuário, como avaliação de qualidade. As amostras encontradas têm aproximadamente 6–8 s; isso é uma oportunidade concreta de diagnóstico, não um limite obrigatório do modelo.

Objetivo: medir se o contexto humano brasileiro reduz a percepção de português europeu. Ao trocar o locutor, também muda identidade/prosódia; registrar isso como parte da intervenção de referência, sem chamar o par de isolamento exclusivo de fonética. Comparar sotaque e naturalidade separadamente. O suporte é o modo ICL real e o alerta dos autores sobre transferência a partir da referência. Não incluir x-vector, CFG ou outra troca de modelo nessa rodada. [Contrato ICL](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/qwen_tts/inference/qwen3_tts_model.py#L355-L390).

## Caminho curto encontrado: gravações humanas OHF/Nabu Casa

O repositório **OHF-Voice/voice-datasets**, antes NabuCasa, publica doações de voz coletadas para criar TTS no Year of Voice do Home Assistant. Declara os datasets sob **CC0** e oferece, no próprio GitHub, a primeira amostra de Cadu, Faber e Jeff em `pt_BR`. São amostras do dataset de gravação, não o resultado de chamar um modelo Piper. A orientação oficial de contribuição pede um falante nativo para gravar o dataset e verificar a voz treinada. A classificação pt-BR vem do fornecedor; não foi feita uma avaliação auditiva nova por esta pesquisa. [Finalidade, licença e amostras na revisão fixada](https://github.com/OHF-Voice/voice-datasets/blob/8ed76fa9001fafc77db32bd682f434938c679e3e/README.md), [processo de doação](https://www.home-assistant.io/voice_control/contribute-voice#donate-your-voice-to-piper).

CC0 permite copiar, modificar e distribuir o material, inclusive para fins comerciais, sem pedir permissão adicional de copyright. Aqui, essa licença vem acompanhada da finalidade explícita de criar TTS; a ausência de um formulário privado individual publicado não será transformada em impedimento novo para o ensaio. A licença não significa endosso do locutor ao texto gerado. O próprio resumo CC0 distingue outros direitos que não são abrangidos pela dedicação, como direitos de personalidade. Isso descreve o alcance do instrumento; não há neste repositório uma exigência publicada de contratar novamente cada doador para usar os dados em TTS. A citação do repositório é pedida pelo fornecedor e será preservada na origem. [CC0 oficial](https://creativecommons.org/publicdomain/zero/1.0/).

Downloads desta investigação: **312.870 bytes no total**, contando três MP3 e o README de 6.342 bytes. Nenhum ZIP/corpus, modelo, autenticação ou inferência. Revisão do fornecedor: `8ed76fa9001fafc77db32bd682f434938c679e3e`, de 20/02/2026. Cada hash Git blob dos MP3 corresponde à árvore publicada. Evidência privada em `video-generation-amostras/p06-sotaque-20261015/referencia-ohf-readonly/source-record.json`, com URLs, SHA256, tamanhos, horário e ffprobe.

| Gravação de origem | Download público fixado | Bytes | Duração de contêiner pelo ffprobe | Perfil |
|---|---|---:|---:|---|
| Cadu, primeira amostra | [MP3](https://raw.githubusercontent.com/OHF-Voice/voice-datasets/8ed76fa9001fafc77db32bd682f434938c679e3e/pt_BR/cadu/0000000001.mp3) | 112.768 | 6,984 s | Mono, 48 kHz |
| Faber, primeira amostra | [MP3](https://raw.githubusercontent.com/OHF-Voice/voice-datasets/8ed76fa9001fafc77db32bd682f434938c679e3e/pt_BR/faber/0000000001.mp3) | 89.440 | 7,560 s | Mono, 48 kHz |
| Jeff, primeira amostra | [MP3](https://raw.githubusercontent.com/OHF-Voice/voice-datasets/8ed76fa9001fafc77db32bd682f434938c679e3e/pt_BR/jeff/0000000001.mp3) | 104.320 | 6,456 s | Mono, 48 kHz |

Os arquivos locais são `cadu-0000000001.mp3`, `faber-0000000001.mp3` e `jeff-0000000001.mp3`. O diretório tem modo 0700 e os arquivos, 0600. O MP3 permanece intacto para rastreabilidade. A duração inclui o contêiner MP3, não uma medição manual de fala útil ou aprovação de limpeza acústica.

SHA256 das amostras intactas:

- Cadu: `3ae10ab7b89c99941c2cddeb7b1656a52b1af134c50045e8767baddb3977b4d1`.
- Faber: `7c855959fa4013f00b933f016b8cd360bc35f460816868c9ea97017ba9647b8b`.
- Jeff: `655aa986f0147a1551affd574edde40014f2f0392fe0e38d4a3e31665fc4cc13`.

Não é necessário usar Mozilla Data Collective para obter essas amostras. O fluxo oficial **MDC** exige conta, aceite dos termos específicos do dataset e API key para download programático. Isso é uma condição daquela rota de distribuição, não um bloqueio para a amostra que o próprio fornecedor publica por outra rota pública. Nenhuma conta, credencial ou aceite foi criado nesta tarefa. [Guia oficial de download MDC](https://community.mozilladatacollective.com/using-the-mdc-python-sdk-library-to-download-datasets/), [SDK oficial](https://mozilla-data-collective.github.io/datacollective-python/).

### Preparação mínima para o controle Base

A árvore GitHub contém os MP3 de exemplo, mas não publica junto um CSV/TXT de transcrição. O passo que falta é **conferir a transcrição literal da amostra escolhida**, por escuta e, se útil, pelo ASR já disponível. Esta pesquisa não inferiu essa transcrição nem executou ASR. Isso é uma necessidade de entrada do ICL, não um impedimento de licença. Não baixar o corpus inteiro só para obter uma frase que pode ser conferida na amostra.

Depois de escolher uma única referência, uma cópia PCM mono de 24 kHz/16 bits pode ser preparada com o FFmpeg existente. Exemplo, executado dentro da pasta da amostra e com nome de saída novo:

```sh
rtk proxy ffmpeg -nostdin -hide_banner -loglevel error -hwaccel none \
  -i cadu-0000000001.mp3 -map 0:a:0 -ac 1 -ar 24000 \
  -c:a pcm_s16le -n cadu-reference-24k.wav
```

Esse comando é preparação proposta; não foi executado por esta pesquisa. Calcular e guardar o novo hash, duração medida e comando de conversão. Criar um request a partir de J, trocando somente os campos da referência humana, sua transcrição/hash e os caminhos de saída novos. Texto da Ana, idioma Portuguese, pesos Base, seed e sampler continuam iguais a J. Preservar o MP3 e o request original. A mudança de identidade é esperada e não representa homologação da personagem final. Não há novo pacote ou modelo necessário para esse controle.

## Latência, precisão e custo: o que é conhecido

| Medida local de 15/10/2026 | Qwen J | Chatterbox F |
|---|---:|---:|
| Duração do WAV | 8,16 s | 9,4 s |
| Tempo de processo no monitor, incluindo inicialização | 33,034 s | 168,278 s |
| Razão tempo de processo / duração, calculada dos monitores | 4,05 | 17,90 |
| Tempo interno registrado pelo estágio/wrapper | 31,257 s | 153,481 s |

Essas medições são das execuções locais MLX/MPS, não de Linux/CUDA. Não são previsão de VoiceDesign. O valor `peak_vram_mb=0` de F mede o ramo CUDA do estágio; não significa uso de memória MPS zero. J registrou pico MLX de 8.020.278.329 bytes, que também não deve ser renomeado como VRAM CUDA. Os monitores registram execução com sandbox de rede negada e flags offline. Esta pesquisa leu os registros; não reexecutou o smoke nem os modelos.

A latência de 97 ms anunciada pelo Qwen é para o primeiro pacote em condições de streaming dos autores, não para um WAV inteiro neste Mac. A precisão textual publicada usa WER; sotaque exige a avaliação humana pedida aqui. Manter EOS, duração, hash do WAV e checagem de fala literal como controles de integridade, sem converter ASR correto em aprovação de sotaque. [Avaliação dos autores](https://arxiv.org/html/2601.15621v1).

Qwen oficial e as conversões MLX selecionadas declaram Apache-2.0; Chatterbox declara MIT. Isso não substitui a licença da referência humana, que foi verificada separadamente para as amostras OHF, nem garante equivalência das saídas entre runtimes. A comparação restante usa a máquina local e os caminhos definidos pelo coordenador. Não há estimativa nova de gasto em nuvem, recarga, compute ou autorização de lote neste documento. [Licença Qwen](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/LICENSE), [card MLX](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16/blob/7d3824abff87e49756bb0f83fb5411de75d160c4/README.md), [licença Chatterbox](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/LICENSE).

## Revisões e limites da pesquisa

| Fonte | Revisão consultada |
|---|---|
| Qwen3-TTS código | `022e286b98fbec7e1e916cb940cdf532cd9f488e`, 17/03/2026 |
| VoiceDesign oficial | `5ecdb67327fd37bb2e042aab12ff7391903235d3`, 29/01/2026 |
| VoiceDesign MLX bf16 | `7d3824abff87e49756bb0f83fb5411de75d160c4`, 25/01/2026 |
| Qwen Base MLX de J | `a6eb4f68e4b056f1215157bb696209bc82a6db48`, registrado no request |
| Chatterbox guia atual / runtime local | `5de7a54aa4e5e2baadb0182dde554908b48b85c2` / 0.1.7 `59bc590b3cad826e5d5987745bf6844627a21ad5` |
| Chatterbox pt-BR | `b3952f18bc2eaa72b9bd7c17d2c4653bcad4770d`, 10/06/2026 |
| Kokoro código / pesos-vozes | `dfb907a02bba8152ca444717ca5d78747ccb4bec` / `f3ff3571791e39611d31c381e3a41a3af07b4987` |
| Misaki | `fba1236595f2d2bf21d414ba6e57d25256afada3` |
| Fala PB checkpoints | `2a35881bcb7996d46533f88914c18b386b9d1ee3`, 07/07/2026 |

Busca dirigida a controles e causas, sem inventário amplo de modelos. As páginas de issues são relatos de primeira mão, não prova independente de acerto nem instruções para o projeto. Não foram ouvidos novos áudios, baixados pesos ou executadas inferências nesta tarefa. A percepção local vem do feedback explícito do usuário; o restante distingue capacidade documentada, medição já preservada e hipótese de teste.
