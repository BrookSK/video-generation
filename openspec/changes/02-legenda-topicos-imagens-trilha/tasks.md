# Tasks

## 1. API

- [ ] 1.1 Aceitar o upload da trilha na identidade (MP3, WAV, M4A ou OGG até 20 MB, arquivo novo e imutável) e permitir removê-la; verificar com `uv run --directory apps/api pytest tests/assets/test_brand_identity.py` (formato e tamanho recusados com 422, troca preserva o arquivo anterior)
- [ ] 1.2 Aceitar na criação da aula até 5 tópicos por cena com até 80 caracteres, uma imagem opcional por cena (JPEG, PNG ou WebP pelo validador de avatar) e a trilha ligada ou desligada, gravando tudo na aula e nas cenas e incluindo no payload da montagem; regerar `docs/api/openapi.json`; verificar com `tests/jobs/test_lesson_create.py` e `tests/jobs/test_lesson_queue.py` (limites recusados com 422 indicando a cena, imagem inválida recusada, trilha ligada sem trilha cadastrada recusada, payload com tópicos, imagem e trilha congelados)

## 2. Montagem

- [ ] 2.1 Versionar a fonte OFL escolhida com o arquivo de licença e criar o desenho de legenda e tópicos com Pillow nos dois formatos; verificar com `uv run --directory apps/worker pytest -m "not gpu" tests/test_lesson_text.py` (quebra por largura, até duas linhas, cores da identidade)
- [ ] 2.2 Implementar a divisão da legenda em trechos sem alterar palavras e o tempo por `silencedetect` com fallback por caracteres; verificar com `tests/test_lesson_text.py` (texto concatenado dos trechos idêntico ao da cena; áudio sintético com silêncios conhecidos põe cada trecho dentro da frase; número de intervalos diferente usa o fallback)
- [ ] 2.3 Aplicar legenda e tópicos por cena com `overlay`, e a imagem em tela principal com o apresentador em quadro menor; verificar com `tests/test_lesson.py` usando FFmpeg real (quadros extraídos mostram legenda, tópicos e imagem só nas cenas certas, sem distorção da imagem)
- [ ] 2.4 Mixar a trilha com volume base baixo, `sidechaincompress` pela voz e saída suave, e falhar com mensagem em português quando a trilha é ilegível; verificar com `tests/test_lesson.py` medindo no arquivo final que o nível da trilha é menor nos trechos de fala do que nas pausas, e que a aula sem trilha não tem trilha

## 3. Painel

- [ ] 3.1 Acrescentar à Nova aula os tópicos por cena (um por linha, com contador), a imagem opcional por cena com prévia e a trilha ligada ou desligada; acrescentar à Identidade o upload da trilha com player; verificar com `npm --prefix apps/web run test` (corpo enviado com tópicos, imagem e trilha; limites e erros 422 exibidos no campo certo) e `npm --prefix apps/web run typecheck`

## 4. Jornada local

- [ ] 4.1 Estender a jornada E2E com a tag `@M002-02`: gerar pelo navegador uma aula 9:16 e outra 16:9 com legenda, tópicos, uma imagem e trilha, com dublê só nas fronteiras de TTS e render; conferir que a legenda reconstruída dos trechos confere palavra por palavra com o texto informado e que a trilha fica mais baixa nos trechos de fala; verificar com `npm --prefix apps/web run e2e -- --grep @M002-02`
- [ ] 4.2 Rodar a verificação completa: `uv run --directory apps/api pytest tests`, `uv run --directory apps/worker pytest -m "not gpu" tests`, `npm --prefix apps/web run test`, `npm --prefix apps/web run typecheck` e `npm --prefix apps/web run e2e -- --grep "@M002-01|@M002-02"`, todos verdes
