# Calibração de fala, presença e cenário

Pacote exploratório da P06. Não muda a receita vigente, não aprova qualidade e não congela receita. A imagem candidata do commit `ba8659105989d5f32b99c2c8ec82d0fc3299b346` foi publicada em 15/10/2026 com o digest abaixo. O manifesto remoto autenticado foi conferido, e `pilot --help` passou sem rede/GPU, como uid 10001, com as flags de áudio revisado presentes. Esse smoke valida o CLI; inferência GPU dessa imagem e aceite humano de voz, entonação e vídeo continuam pendentes. As receitas geradas permanecem `draft`.

Preparar e validar entradas não usa GPU; TTS e piloto usam compute e exigem saldo compatível com a janela autorizada. Antes de abrir a janela paga, confira o espaço necessário para as camadas ausentes e os modelos já disponíveis no volume. A imagem antiga não ganha as novas flags por atualizar somente a receita. A execução excepcional com um módulo montado precisa identificar separadamente imagem, commit e hash do módulo no registro do ensaio.

## Preparar

Na raiz do repositório, escolha um diretório novo dentro da base de trabalho:

```bash
CALIBRATION_DIR="$(rtk proxy mktemp -d /Users/felipebianchini/Developer/p06-calibration.XXXXXX)"
WORKER_IMAGE="vccr.io/5e20534f-f96c-42fb-8a52-deb4f7e28efc/avatar-worker@sha256:cad3a59ea8afb4197179a02ce6702a48bb9bf8f3f79acb586645291b53c632b4"
rtk proxy python3 docs/models/calibration/prepare.py --materials "$MATERIALS_DIR" --out "$CALIBRATION_DIR/in" --worker-image "$WORKER_IMAGE"
```

`MATERIALS_DIR` aponta para os seis PNGs existentes: `avatar-feminino.png`, `avatar-masculino.png` e `cenario-{escritorio,estudio,sala,loja}.png`. Reutilize os materiais autorizados; não gere imagens novas neste preparo. O script usa só a biblioteca padrão, recusa saída existente e copia imagens, falas, manifesto e receita atuais. `SHA256SUMS` identifica as entradas geradas. Guarde o pacote em área privada e remova o diretório temporário ao terminar de usar.

O exemplo usa a imagem publicada com o novo CLI necessário ao modo de áudio pré-ouvido. A opção `--worker-image` valida o formato e aplica o mesmo digest às três receitas externas; o script não consulta o registro nem altera `RECIPE-v1.json`. Sem a opção, a base é cópia exata da receita atual, cuja imagem antiga não oferece esse modo. Uma imagem futura exige novo build/publicação, conferência do digest e um pacote novo.

| Entrada gerada | Uso |
|---|---|
| `RECIPE-baseline.json` | Receita draft atual, com imagem opcional substituída em todas as variantes. |
| `RECIPE-composition.json` | Só aproxima o avatar vertical, de escala 0,8 para 0,9. O 16:9 fica intacto. |
| `RECIPE-prompt.json` | Só troca o prompt por postura relaxada, olhar atento, pequenos movimentos e expressão. Mantém mãos abaixo do quadro pelo risco observado de mãos inventadas. |
| `queue-demo-{voz}-{9x16,16x9}.json` | Uma amostra curta, uma voz e um formato. |
| `queue-c1-{voz}-{9x16,16x9}.json` | Uma amostra literal mais longa. |
| `queue-stress-{numerico,extenso}-{voz}-9x16.json` | Fala do preview V4 e sua equivalente por extenso, preservadas para investigar a literalidade. |
| `queue-{demo,c1}-four-samples.json` | Duas vozes × dois formatos, quando houver orçamento. |
| `queue-demo-feminina-9x16-sala.json` | Muda só o fundo, de escritório para sala. |
| `tts-{demo,c1,stress-numerico,stress-extenso}-{voz}.json` | Pré-escuta de TTS isolado, antes de pagar pelo render. |

As demos buscam cerca de 8–12 s e `c1-aprox30s.txt` cerca de 30 s. São metas editoriais, sem duração medida. C1 contém nomes, pedido duzentos e dezoito, cento e quarenta e nove reais e noventa centavos, parcelas, telefone, horários e negativas, todos por extenso. O telefone esperado é 0800 721 4400; ouvir cada dígito.

`stress-original-numerico.txt` preserva os bytes da fala V4 usada no último preview, incluindo algarismos/símbolo monetário. `stress-original-extenso.txt` conserva as mesmas frases e dados, alterando apenas a representação dos números e as pausas entre dígitos. Esse par compara um fator de texto e mantém visível o caso que motivou a investigação. A versão por extenso pode durar mais e deve ser medida antes de renderizar. A demo ou a fala por extenso não substitui a aprovação da entrada numérica original, nem a regressão do defeito de literalidade.

## Validar sem GPU

Use o ambiente existente do worker. Não passe `--frozen` para estas variantes:

```bash
for RECIPE in baseline composition prompt; do
  rtk uv run --directory apps/worker python -m avatar_worker.recipe validate "$CALIBRATION_DIR/in/RECIPE-$RECIPE.json" --manifest "$CALIBRATION_DIR/in/MODEL_MANIFEST.json"
done
rtk uv run --directory apps/worker python -m avatar_worker.manifest verify --policy "$CALIBRATION_DIR/in/MODEL_MANIFEST.json"
rtk uv run --directory apps/worker python -c 'from pathlib import Path; import sys; from avatar_worker.pilot import load_queue; files = sorted(Path(sys.argv[1]).glob("queue-*.json")); print([(p.name, len(load_queue(p))) for p in files])' "$CALIBRATION_DIR/in"
```

## Ouvir antes de renderizar

Em uma janela GPU com saldo, transfira o pacote `in` e prepare uma pasta `out` nova, privada, gravável pelo uid 10001. Defina `WORKER_IMAGE` com `ref@digest` de `RECIPE-baseline.json`, `MODELS_DIR` com os pesos já conferidos e `CALIBRATION_DIR` com a pasta remota. Execute um TTS por vez:

```bash
rtk proxy docker run --rm --pull=never --gpus device=0 --network none --user 10001:10001 \
  --mount type=bind,src="$MODELS_DIR",dst=/models,readonly \
  --mount type=bind,src="$CALIBRATION_DIR/in",dst=/pilot/in,readonly \
  --mount type=bind,src="$CALIBRATION_DIR/out",dst=/pilot/out \
  --entrypoint /app/apps/worker/runtimes/tts/.venv/bin/python "$WORKER_IMAGE" \
  /app/apps/worker/runtimes/tts/tts_stage.py \
  /pilot/in/tts-demo-feminina.json /pilot/out/demo-feminina.result.json
```

Priorize também `tts-stress-numerico-{voz}.json` e `tts-stress-extenso-{voz}.json` com a mesma voz, antes de mudar prompt ou composição. Ouça as duas vozes separadamente. Não reutilize nomes de saída de uma tentativa anterior. Copie WAV, resultado e log. Ouça a fala completa e compare com o texto, incluindo final, nomes, preço, negativas e cada dígito do telefone. Confira duração real e `watermark_detected`. EOS terminal só prova conclusão mecânica; não comprova literalidade. ASR é diagnóstico auxiliar, e a escuta humana confirma os termos críticos. Preserve resultados reprovados e vincule as novas tentativas. Se houver erro, repetição, pausa ruim, pronúncia incorreta ou recusa D001 por ausência de EOS, investigue antes de renderizar. Uma reformulação em cópia nova pode ajudar a calibrar; não encerra o defeito da fala original. Não aumente orçamento de tokens ou limites para contornar a recusa.

Para renderizar o WAV ouvido sem ressintetizar, copie os três arquivos para um diretório de revisão novo. O request e o resultado podem manter seus caminhos originais: o piloto lê o `speech.wav` local e confere texto, voz, idioma, duração, perfil PCM, watermark e o hash explícito. A cópia não registra aprovação humana automaticamente:

```bash
REVIEWED_DIR="$CALIBRATION_DIR/reviewed-demo-feminina"
rtk proxy mkdir "$REVIEWED_DIR"
rtk proxy cp "$CALIBRATION_DIR/in/tts-demo-feminina.json" "$REVIEWED_DIR/tts_request.json"
rtk proxy cp "$CALIBRATION_DIR/out/demo-feminina.result.json" "$REVIEWED_DIR/tts_result.json"
rtk proxy cp "$CALIBRATION_DIR/out/demo-feminina.wav" "$REVIEWED_DIR/speech.wav"
REVIEWED_AUDIO_SHA256="$(rtk proxy python3 -c 'import hashlib,sys; from pathlib import Path; print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())' "$REVIEWED_DIR/speech.wav")"
```

Use o mesmo diretório/hash ao comparar composição e prompt com a mesma fala. Uma fala ou voz diferente exige outro WAV ouvido e outro diretório/hash. Sem as duas flags de revisão, o piloto sintetiza novamente; ouvir um WAV anterior não valida o áudio novo. Ouça também a saída final e compare o hash do WAV usado. O render de avatar ainda pode variar entre processos.

## Comparar um fator por vez

Somente após o áudio passar pela avaliação humana, comece com uma demo feminina 9:16 em escritório. Faça somente a comparação necessária; os lotes de quatro amostras não são o primeiro comando. Use saída nova para cada execução e registre receita/hash, fila/hash, digest, tempo, VRAM e veredito humano:

| Comparação | Receita | Fila | Referência |
|---|---|---|---|
| Base curta | baseline | `queue-demo-feminina-9x16.json` | Referência das comparações seguintes. |
| Texto literal | baseline | `queue-c1-feminina-9x16.json` | Só muda a fala em relação à base. |
| Stress numérico | baseline | `queue-stress-numerico-feminina-9x16.json` | Preserva a fala V4 para reteste do defeito. |
| Stress por extenso | baseline | `queue-stress-extenso-feminina-9x16.json` | Só muda a representação numérica/pausas em relação ao stress numérico. |
| Enquadramento | composition | `queue-demo-feminina-9x16.json` | Só muda a composição em relação à base. |
| Presença | prompt | `queue-demo-feminina-9x16.json` | Só muda o prompt em relação à base. |
| Fundo alternativo | baseline | `queue-demo-feminina-9x16-sala.json` | Só muda a imagem de fundo em relação à base. |

Exemplo da base exploratória, na GPU, com a mesma montagem da pré-escuta:

```bash
rtk proxy docker run --rm --pull=never --gpus device=0 --network none --user 10001:10001 \
  -e WORKER_IMAGE_DIGEST="$WORKER_IMAGE" \
  --mount type=bind,src="$MODELS_DIR",dst=/models,readonly \
  --mount type=bind,src="$CALIBRATION_DIR/in",dst=/pilot/in,readonly \
  --mount type=bind,src="$CALIBRATION_DIR/out",dst=/pilot/out \
  --mount type=bind,src="$REVIEWED_DIR",dst=/pilot/reviewed,readonly \
  --entrypoint python "$WORKER_IMAGE" -m avatar_worker.pilot \
  --recipe /pilot/in/RECIPE-baseline.json --manifest /pilot/in/MODEL_MANIFEST.json \
  --models /models --queue /pilot/in/queue-demo-feminina-9x16.json \
  --runs 1 --out /pilot/out/demo-base-01 \
  --reviewed-tts-dir /pilot/reviewed --reviewed-audio-sha256 "$REVIEWED_AUDIO_SHA256"
```

Mantenha guias texto 1.0/áudio 2.0, referências, LoRA, passos, FPS, TTS e limites. Observe boca/sincronia, cabeça/ombros, expressão, enquadramento, fundo, mãos/objetos inventados, cor e final da fala. Não junte variantes antes de avaliar cada diferença. O teste estático real rejeitou escala 0,72 por espaço excessivo sobre a cabeça e bordas dos ombros aparentes; o estúdio mostrou microfones junto ao rosto. Escala 0,9 e sala são candidatas, ainda sujeitas a avaliação GPU. A comparação estática não aprova animação.

O modo revisado aceita exatamente uma amostra e `--runs 1`; serve à exploração econômica. A aprovação P06 ainda exige as durações medidas, duas vozes/dois formatos, `--runs 2`, 60 s vertical, 720p condicional, teste GPU e avaliação humana C1–C7/vozes/desempenho descritos no plano. O piloto chama processos novos em cada execução; “warm” significa repetição com recarga, não modelo residente. Não carregar estas receitas draft na API nem substituir o registro de homologação por esta comparação.
