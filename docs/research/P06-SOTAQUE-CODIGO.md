# P06 — rastreio do sotaque no código e nos artefatos

Data: 15/10/2026. Diagnóstico de leitura. Não houve nova síntese, instalação, download de pesos ou uso de GPU/MPS/MLX nesta investigação.

O rastreio não encontrou configuração acidental de pt-PT, troca de checkpoint nem troca entre os rótulos das quatro amostras. Kokoro recebe `pt-br`; Chatterbox carrega os pesos pt-BR registrados; Qwen recebe o token genérico de português. Isso verifica a cadeia de configuração e os bytes. Não demonstra que a realização acústica soe brasileira.

O feedback humano continua sendo o critério de sotaque: a amostra 2 chegou perto em naturalidade, mas seu início pareceu português de Portugal; a amostra 4 ficou razoável e ainda precisa melhorar. O usuário percebeu pt-PT também em outros áudios, sem classificação individual de cada arquivo. Nenhuma amostra foi aprovada. Esta investigação não incluiu audição direta. ASR lexical não distingue sotaque.

## Fontes locais e nomes usados

Os caminhos abaixo ficam fora do Git. As abreviações permitem localizar cada evidência sem confundir a instalação atual com o código preservado de uma execução encerrada.

| Prefixo | Diretório |
| --- | --- |
| `A` | `/Users/felipebianchini/Developer/video-generation-amostras/p06-pesquisa-naturalidade-20261015` |
| `E` | `A/experimentos` |
| `M` | `/Users/felipebianchini/Developer/video-generation/models` |
| `V` | `/Users/felipebianchini/Developer/video-generation/apps/worker/runtimes/voices/.venv/lib/python3.12/site-packages` |

Os ambientes temporários Chatterbox/MLX dessa rodada já foram removidos. Seus fontes foram preservados em `E/setup/runtime-sources`, com freezes em `E/setup`. As linhas citadas nesses fontes correspondem aos bytes registrados em `E/setup/runtime-code-hashes.json`.

## O que realmente foi comparado

As quatro entradas preservam o mesmo texto alvo:

> Olá, eu sou a Ana. Aqui, sua ideia ganha voz com clareza e atenção. Conte com a nossa equipe para dar o próximo passo.

| Player | Ensaio | Motor e execução | Idioma passado | Referência | Duração |
| --- | --- | --- | --- | --- | --- |
| 1 | G | Qwen3-TTS 1.7B Base bf16, MLX Audio 0.5.9 | `Portuguese` | `pf_dora.wav` integral | 8,88 s |
| 2 | J | Mesmo Qwen/runtime | `Portuguese` | Mesma referência sem os primeiros 0,53 s | 8,16 s |
| 3 | E | Chatterbox Multilingual 0.1.7, D001/policy v3, MPS | `pt` | `pf_dora.wav` integral | 8,24 s |
| 4 | F | Mesmo Chatterbox/runtime | `pt` | Mesma referência sem os primeiros 0,53 s | 9,40 s |

Entradas: `E/inputs/prosody-{E,F}.request.json:2–9` e `E/inputs/qwen-{G,J}.request.json:2–16`. Em E/F: `temperature=0.8`, `cfg_weight=0.3`, `exaggeration=0.4`, `repetition_penalty=1.2`, seed `20261015`. Em G/J: `temperature=0.9`, `top_p=1`, `top_k=50`, repetição efetiva `1.5`, `max_tokens=512`, seed `20261015`. A mesma seed não iguala a amostragem entre motores ou entre durações distintas da referência.

`E/inputs/prosody-mps.py:16–18` confere o hash do stage D001. As linhas 61–70 injetam os três controles de prosódia e o dispositivo MPS; o idioma e o diretório de modelos seguem do request para o stage. O wrapper Qwen confere o hash da referência, exige modelo `base` e encoder do codec (`E/inputs/qwen_probe.py:12–19`), depois passa `lang_code`, `ref_audio` e `ref_text` para `generate` na linha 33.

Os hashes dos quatro arquivos de escuta batem com `A/mapa-comparacao-voz.json`. A ordem de `audio src` em `A/revisao.html` também bate com G/J/E/F. Não apareceu rótulo apontando para os bytes de outro ensaio.

| Ensaio | SHA-256 do WAV bruto | SHA-256 do WAV de escuta |
| --- | --- | --- |
| E | `3c916d3f4163a911e3207f6367377abb829c76951127de5e5e3520ddc892797c` | `4467020acfa529e76abfe921b10ac2d26e3bd451156e97c994a6e0ee598bc0d3` |
| F | `42fce3ca6c433742f46cb2a1bf19b390ebab92484250448a5e035a732b91384c` | `efa868ae21925c547312a285da6d5829682c8c3fd83f07d43889bd293db8e5c5` |
| G | `07c2df37ab53752ae148f95985e77889c24b3d72c5f9fd1eb89e3cc0aa377463` | `d4e3badf3f1088e6b02b52ef6525bb0713868f84fd5de79f553c92eeee8f0c18` |
| J | `4cea5f71b9f8899d0b3c347a74506e9b1e092118204c733bf560645701d5b9f5` | `2251201a2265d951f38a492eafa0e53d0ba0024ba6fd7a2140d6b451d5a80c4e` |

## Referência sintética: origem e recorte reais

[voice_references.py](../../apps/worker/runtimes/voices/voice_references.py) fixa os presets `pf_dora` e `pm_alex` na linha 35. O texto de referência começa com **“Olá!”**, seguido de “Esta é uma voz sintética de referência...” nas linhas 41–44. A frase “Falo português do Brasil” é conteúdo falado; não funciona como uma configuração adicional do modelo.

O mesmo arquivo fixa `lang_code="p"`, `speed=1`, seed `20261014` e CPU nas linhas 37–52. Confere o commit instalado de Kokoro nas linhas 149–154; carrega modelo/config locais nas linhas 161–164; usa explicitamente `voices/{preset}.pt` nas linhas 166–170. A proveniência inclui preset, texto, parâmetros, revisões e hashes das fontes nas linhas 204–221.

E e G usam os mesmos bytes femininos, apesar dos caminhos diferentes. `E/models/references/original.wav` é idêntico a `M/kokoro-voice-references/pf_dora.wav`. F e J usam o recorte desses mesmos bytes. Não houve substituição por `pm_alex`.

| Arquivo | Formato | Frames de áudio | SHA-256 |
| --- | --- | --- | --- |
| `original.wav` / `pf_dora.wav` | PCM16 mono, 24 kHz | 280.200 = 11,675 s | `608f223af6d041f42bd8ea0071e771a75032dc9741422e406592694ef104fa0c` |
| `sem-ola.wav` | Mesmo formato | 267.480 = 11,145 s | `fb086d17f8be82befaa50a367f17e536d906875f05dbe7cace02d570e299be1e` |

O recorte remove exatamente 12.720 frames iniciais, ou 0,53 s. O PCM restante é idêntico, sem ganho ou resampling. A escolha foi registrada em `E/inputs/reference-crop.json:2–9`, com base em limites temporais de ASR e RMS local. Em J, `ref_text` também perde “Olá! ” e mantém a transcrição do trecho restante. Isso preserva a correspondência operacional entre texto e recorte; não é uma nova transcrição humana certificada.

Retirar o começo muda conteúdo, duração e posição inicial das janelas de condicionamento. O par original/recorte não permite atribuir uma diferença apenas à palavra “Olá”, nem provar transferência de sotaque. A queixa de sotaque em J também impede tratar a retirada do cumprimento como solução já demonstrada.

## Kokoro: `p` chega ao frontend brasileiro

O código instalado em `V/kokoro/pipeline.py` declara o alias `pt-br → p` na linha 18 e `p → pt-br` na linha 33. As linhas 87–89 normalizam e validam o código. Nas linhas 142–144, o ramo usado por `p` cria `EspeakG2P(language="pt-br")`.

`V/misaki/espeak.py:8–10` seleciona a biblioteca e os dados empacotados por `espeakng_loader`. As linhas 64–69 passam esse idioma ao `EspeakBackend`. `V/phonemizer/backend/espeak/espeak.py:49` chama `set_voice(language)`. `V/espeakng_loader/__init__.py:6–15` resolve a biblioteca local e `espeak-ng-data` do pacote.

Os dados locais distinguem as variantes:

- `V/espeakng_loader/espeak-ng-data/lang/roa/pt-BR:1–6`: nome `Portuguese (Brazil)`, idioma `pt-br`, `dictrules 2`.
- `V/espeakng_loader/espeak-ng-data/lang/roa/pt:1–7`: nome `Portuguese (Portugal)`, idiomas `pt`/`pt-pt`, `phonemes pt-pt`, `dictrules 1`.

Não foi encontrado fallback explícito de `pt-br` para `pt-pt` nesse caminho. O ramo `EspeakFallback` de Misaki é usado no frontend inglês; seu remapeamento de `ɐ` não se aplica ao caminho acima.

O controle direto já existente, `A/diagnostico/kokoro-direto`, registra o mesmo texto alvo com `p`, `pf_dora`, CPU e `speed=1`. Seu resultado preserva, entre outros, `Ana → ˈɐ̃næ`, `sua → sˌuæ` e `ideia → ˌidˈɛɪæ`. O mapa `e2m` realmente usado está em `V/misaki/espeak.py:71–104`: remapeia ditongos/africadas, como `e^ɪ → A` e `t^ʃ → ʧ`, e remove ties/hífens. Ele não contém conversão `ɐ → æ` nesse ramo.

Há um ponto de risco verificável em `V/kokoro/model.py:128`: caracteres ausentes do vocabulário são descartados. Para os fonemas registrados nesse controle, todos os **36 caracteres distintos estão presentes** no `M/kokoro-82m/config.json`. Isso inclui `æ`, `ɐ`, o til combinante, `A` e `ʧ`. Portanto, não houve evidência desse descarte no texto alvo. A presença de `æ` na representação não classifica o sotaque percebido do WAV nem demonstra erro do frontend.

O controle direto usa Kokoro `0.9.4`, commit `dfb907a02bba8152ca444717ca5d78747ccb4bec`; Misaki `0.9.4`; `espeakng-loader 0.2.4`; `phonemizer-fork 3.3.2`. O commit instalado confere com o manifesto e com `direct_url.json`. O modelo e preset locais conferem com a revisão `f3ff3571791e39611d31c381e3a41a3af07b4987`. O manifesto histórico das referências registra código, pesos e parâmetros, mas não registra os fonemas nem toda a versão do frontend daquela geração. O resultado fonético do controle atual não deve ser atribuído retroativamente à referência histórica como uma medição direta dela.

## Chatterbox: o alias genérico aponta para pesos pt-BR

O runtime fixa `chatterbox-tts==0.1.7` em [pyproject.toml](../../apps/worker/runtimes/tts/pyproject.toml). O [manifesto](../models/MODEL_MANIFEST.json) registra o checkpoint `ResembleAI/Chatterbox-Multilingual-pt-br` na revisão `b3952f18bc2eaa72b9bd7c17d2c4653bcad4770d` e os componentes base na revisão `5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18`.

[tts_stage.py](../../apps/worker/runtimes/tts/tts_stage.py):28–36 monta os nomes exigidos por `from_local` desta forma:

| Nome lido pelo Chatterbox | Fonte real |
| --- | --- |
| `t3_mtl23ls_v2.safetensors` | `chatterbox-multilingual-pt-br/t3_pt_br.safetensors` |
| `s3gen.pt` | `chatterbox-multilingual-pt-br/s3gen_v3.pt` |
| `grapheme_mtl_merged_expanded_v1.json` | Mesmo diretório pt-BR |
| `ve.pt`, `conds.pt` | `chatterbox-base` |

As linhas 162–167 criam symlinks temporários para os arquivos resolvidos e chamam `from_local`. Não há fallback para download ou checkpoint genérico nessa função. Os symlinks do diretório privado resolvem os arquivos autorizados em `M`. A conferência atual de tamanho/SHA dos arquivos usados passou, incluindo T3 `074aaf65255eb9cb960288f7cc72e09d3b5008f6e0b14868c0d4e5b0bd7cbb6c` e S3Gen `f7abce4b196dae2d08d9296cbebc6521b046079577643b42a19a03499d08721e`.

O fonte efetivo preservado `E/setup/runtime-sources/chatterbox-mtl_tts-patched.py:178–197` carrega esses aliases e os condicionais base iniciais. Contudo, nas linhas 269–270, a presença de `audio_prompt_path` chama `prepare_conditionals`. Essa função extrai o condicionamento da referência e substitui `self.conds` na linha 247. Assim, a existência de `conds.pt` base não significa que E/F usaram a voz padrão base durante a geração.

O stage confere o hash do WAV em suas linhas 84–102 e passa `language_id=language` e `audio_prompt_path` nas linhas 195–196. E/F declaram `pt`; o tokenizer recebe esse identificador em minúsculas no fonte preservado, linha 285. Não apareceu `pt-pt` nessa propagação. Esse identificador de idioma não oferece um seletor regional independente do checkpoint e da referência.

## Qwen: português genérico, sem seletor BR/PT local

G/J usam `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16`, revisão `a6eb4f68e4b056f1215157bb696209bc82a6db48`. Os 13 arquivos conferem em tamanho/SHA com `E/setup/qwen-weights-verification.json`. O arquivo principal tem SHA `81fb76175ff74e69be25fef2cc3e54f016df3034f1514c8e1c89da06a3510cff`; o codec de fala tem SHA `836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258`.

`M/qwen3-tts-1.7b-base-mlx-bf16/config.json:109–119` contém `portuguese: 2071`. Não há entrada separada para `pt-br`, `pt-pt` ou `PortugueseBR`. As linhas 125–126 têm mapas de speakers/dialetos vazios; a linha 163 confirma `tts_model_type="base"`.

No fonte preservado `E/setup/runtime-sources/qwen3_tts-mlx-audio-0.5.9.py:1231–1255`, `ref_audio` + `ref_text` + encoder ativam o caminho ICL usado pelos dois ensaios. O wrapper fornece os três. Na linha 1246, `lang_code` segue como `language`. Nas linhas 737–741 do preparo ICL, `Portuguese` é convertido para minúsculas e resolve `2071`; as linhas 755–761 colocam esse ID no prefixo do codec. Portanto, não ficou em `auto` por causa da maiúscula inicial.

A referência alimenta tokens do codec e também o embedding de speaker nesse caminho. Isso permite investigar influência da referência; não prova que ela determinou o sotaque. O código não fornece uma garantia regional por escolher `Portuguese`.

Trocar o rótulo para `pt-br` ou `PortugueseBR` sem alterar o contrato não cria um novo token regional. Nesse lookup, um nome desconhecido deixa `language_id=None`, mudando o prefixo usado. Adicionar `instruct` também não é um controle disponível para esse caminho Base/ICL da versão 0.5.9: a chamada das linhas 1242–1255 não o encaminha. Omitir `ref_text` troca de caminho de condicionamento; não mantém o mesmo ensaio com apenas uma instrução regional adicional.

## Hipóteses abertas e menor controle útil

| Hipótese, ainda não comprovada | Evidência compatível | Controle que pode enfraquecê-la |
| --- | --- | --- |
| A referência sintética compartilhada contribui para a realização percebida como pt-PT. | Os dois motores recebem `pf_dora`; ambos usam conteúdo acústico da referência. | O usuário avaliar a referência original e o recorte como claramente brasileiros, mas continuar percebendo pt-PT nas clonagens, enfraquece uma explicação apenas pela referência. |
| O frontend/preset Kokoro já produz uma realização inadequada para o usuário. | Ele é a origem comum; existe controle direto do mesmo texto. | O usuário considerar o Kokoro direto e as referências brasileiros, mas os clones pt-PT, enfraquece a cadeia Kokoro como explicação suficiente. Configuração e IPA, sozinhos, não resolvem essa avaliação. |
| O condicionamento genérico de português ou a interação motor/referência não sustenta o dialeto desejado. | Qwen não tem token regional; checkpoint pt-BR no Chatterbox não elimina a queixa humana. | Uma referência nativa pt-BR autorizada, julgada antes pelo usuário, produzir resultados brasileiros sob os mesmos controles enfraquece uma limitação inevitável do motor. Não isolaria perfeitamente identidade, prosódia e dialeto. |
| Há troca de rótulo, arquivo, locale ou pesos. | Seria uma causa operacional possível. | As conferências desta investigação não a sustentaram: rótulos/bytes, requests, idiomas, aliases e hashes batem. A busca foi limitada a esta cadeia e a estes ensaios. |

O menor controle útil agora não exige nova geração: apresentar para avaliação humana explícita de sotaque os três arquivos já existentes — `M/kokoro-voice-references/pf_dora.wav`, `E/models/references/sem-ola.wav` e `A/diagnostico/kokoro-direto/kokoro-pf_dora.raw.wav` — junto da amostra J. Registrar se a percepção pt-PT já está na referência, se surge apenas no texto alvo, e em quais palavras/tempos. Isso localiza melhor o problema sem presumir que texto, fonema, ASR ou nome de checkpoint classifiquem sotaque.

Se ainda for necessário gerar um controle, o passo seguinte é manter J como base e trocar apenas o par **áudio de referência + transcrição correspondente** por uma referência nativa pt-BR autorizada e previamente avaliada. Manter texto alvo, modelo, runtime e sampler. Essa troca ainda altera identidade e prosódia; uma única amostra não comprova causalidade nem repetibilidade. Não substituir a configuração atual em produção antes de avaliação humana.

## Verificação e limites

Esta leitura reconferiu os 11 arquivos pertinentes do manifesto local — três do Chatterbox pt-BR, dois componentes base, quatro fontes/presets Kokoro e duas referências derivadas — e os 13 arquivos do snapshot Qwen. Conferiu os hashes dos cinco fontes preservados, dos dois WAVs de referência e dos quatro arquivos usados no player. O recorte PCM foi comparado byte a byte ao sufixo da referência original. Não foram alterados runtime, modelos, página de revisão, áudio ou receita.

Os fontes preservados Chatterbox e Qwen têm SHA-256 `117c5ba0ed55812440ff7ed9e0db28b674779ca93b17533c0b6b927a80111cf8` e `0d9437e4f08680d7bf8cb7bf3b44c8e3de37ad9edf025f50dba37dface2e6902`. O stage D001 tem SHA `50727fdb0bea718551fa5ee90ff54793f36eec5b53ae90d008181e330b853983`. Esses registros identificam o código investigado; a instalação temporária removida não foi recriada para este diagnóstico.

Não há parecer fonético especializado, teste perceptivo controlado ou classificação automática de sotaque. A conclusão é restrita: a cadeia local examinada propagou as configurações e os materiais registrados; a causa acústica da percepção pt-PT permanece aberta.
