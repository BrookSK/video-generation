# P06 — diagnóstico SyncNet em CPU e correção temporal reversível

Ensaio real em 15/10/2026. O SyncNet original estimou **−2 quadros, ou −80 ms**, em três trechos do vídeo anterior. Os controles de áudio deslocados recuperaram exatamente as alterações conhecidas. Uma cópia diagnóstica com o vídeo atrasado em dois quadros passou a apresentar **offset zero nos mesmos três trechos**, com todos os controles preservados. Não houve novo render de avatar ou nova síntese de voz.

Isso verifica correspondência temporal além do mux. Não aprova naturalidade de movimento, voz, palavras, enquadramento ou a P06. O original foi preservado. A cópia corrigida continua sujeita à avaliação humana com som.

## Fontes, pesos e licença conferidos antes do download

- Código oficial: [joonson/syncnet_python](https://github.com/joonson/syncnet_python), revisão `907c0b579c2e2d83f0eae1b2ac9e720cde4e5623`, licença [MIT](https://github.com/joonson/syncnet_python/blob/907c0b579c2e2d83f0eae1b2ac9e720cde4e5623/LICENSE.md).
- Peso exato: `syncnet_v2.model`, indicado pelo [script oficial](https://github.com/joonson/syncnet_python/blob/907c0b579c2e2d83f0eae1b2ac9e720cde4e5623/download_model.sh), obtido por HTTPS no [servidor Oxford](https://www.robots.ox.ac.uk/~vgg/software/lipsync/data/syncnet_v2.model).
- A [página Oxford](https://www.robots.ox.ac.uk/~vgg/software/lipsync/) associa o modelo a pesquisa e aponta a licença [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Este uso ficou restrito ao diagnóstico de pesquisa. A licença MIT do código não foi usada como substituta dos termos do modelo, nem foi declarada homologação para incorporá-lo ao produto.
- Atribuição: Joon Son Chung e Andrew Zisserman, *Out of time: automated lip sync in the wild*, Workshop on Multi-view Lip-reading, ACCV, 2016.

O arquivo recebido tem **54.573.114 bytes**, SHA-256 `961e8696f888fce4f3f3a6c3d5b3267cf5b343100b238e79b2659bff2c605442`. Não foi localizado um checksum independente publicado pelo autor. Esse SHA identifica os bytes obtidos pela URL oficial com TLS; não é uma comparação contra hash externo. O state dict foi carregado com `weights_only=True`, `map_location="cpu"` e correspondência estrita com a rede oficial.

## Ambiente e adaptação

Execução somente em CPU, com Python 3.12.13, PyTorch 2.6.0, NumPy 1.26.4, SciPy 1.17.1, `python_speech_features==0.6` e FFmpeg 9.0.2. Dois threads de computação e um thread inter-op. O ambiente Torch existente foi usado somente para leitura, com `python -B`; nenhum pacote foi instalado nele. A dependência leve de MFCC, com licença MIT nos metadados, foi instalada em diretório temporário próprio.

`sandbox-exec` aplicou `deny network*`. Um smoke separado recusou conexão localhost com `EPERM`. Não foram usados MPS, MLX, CUDA, S3FD ou InsightFace. O código oficial já oferece CPU; não foi necessário modificar a arquitetura ou os pesos.

O adaptador privado importa `S` do `SyncNetModel.py` oficial e replica `calc_pdist` para evitar importar o frontend OpenCV. FFmpeg extrai BGR, sem normalização, e PCM16 mono a 16 kHz; MFCC usa os defaults da implementação oficial. A rede recebe cinco quadros e vinte colunas MFCC por janela. O visual é calculado uma vez por trecho e reutilizado nos controles. [Rede oficial](https://github.com/joonson/syncnet_python/blob/907c0b579c2e2d83f0eae1b2ac9e720cde4e5623/SyncNetModel.py), [extração e score oficiais](https://github.com/joonson/syncnet_python/blob/907c0b579c2e2d83f0eae1b2ac9e720cde4e5623/SyncNetInstance.py).

Foram preservados dois cálculos: o original com padding e outro que considera apenas os centros válidos comuns a todos os offsets, para verificar influência de borda. Não são duas redes independentes. Ambos produziram os mesmos offsets. O adaptador inicial tem SHA-256 `c3b69a8dc5fdd5534b3aeb4e4addcb93d0b1a83a438457b8d730e8f95dfc2825`. A variante da cópia corrigida tem SHA `d261a7a60725b7d99654832df8ee1c3b54b6c1847e871b3b996774cfa6835b1c`; seu diff muda apenas vídeo de entrada e diretório de saída.

## Entrada, recorte e cobertura

Fonte: `diagnostico/baseline-original.mp4`, SHA-256 `ca29e2b64dcbd48b476d711f61d4c822b7c3824a81f440982b8419903ffbccaa`. H.264, 1080 × 1920, 25 FPS, **649 quadros/25,96 s**, AAC mono a 48 kHz. Ambos os streams começam em timestamp zero.

Como o rosto permanece quase fixo, foi usado um recorte manual constante: **x=176, y=610, largura=770, altura=770**, redimensionado para 224 × 224 por interpolação bilinear. Foram inspecionados os recortes de 1, 13 e 24 s: olhos, nariz e boca permanecem dentro da área. Isso substitui a detecção/tracking neste ensaio; não valida um detector automático ou todos os possíveis enquadramentos. A [rotina oficial de recorte](https://github.com/joonson/syncnet_python/blob/907c0b579c2e2d83f0eae1b2ac9e720cde4e5623/run_pipeline.py) também entrega 224 × 224, mas calcula a região por caixas detectadas.

Os trechos foram **1–5 s, 11–15 s e 21–25 s**: doze segundos nominais, 46,2% da duração original. Cada trecho forneceu 95 janelas de características. O cálculo sem bordas reteve 65 centros por trecho, em passos de 40 ms, mais o contexto de cinco quadros. Os intervalos de imagem válidos desse cálculo são aproximadamente 1,60–4,36 s, 11,60–14,36 s e 21,60–24,36 s. Não foi medida continuidade integral dos 25,96 s nem outra voz/formato.

## Controles e convenção do sinal

Busca de offsets de **−15 a +15 quadros**, com resolução de **40 ms**. Cada controle deslocou o áudio real antes do MFCC, usando contexto do vídeo original, sem inserir silêncio artificial nas bordas do trecho. Definição de atraso positivo: `y(t) = x(t − atraso)`. O score usa a distância L2 mínima e `confidence = mediana das distâncias − distância mínima`; confidence não é probabilidade nem nota de naturalidade.

| Atraso de áudio injetado | Offset observado no original | Offset observado na cópia corrigida |
|---|---:|---:|
| −400 ms | +320 ms | +400 ms |
| −200 ms | +120 ms | +200 ms |
| 0 ms | −80 ms | 0 ms |
| +200 ms | −280 ms | −200 ms |
| +400 ms | −480 ms | −400 ms |

Essa resposta ocorreu nos três trechos e nos dois cálculos. O erro entre mudança esperada e observada foi **zero ms nos controles**. Portanto, nesta convenção, áudio adicionalmente atrasado torna o offset mais negativo. O baseline é compatível com áudio atrasado cerca de 80 ms segundo a rede, sem uma referência humana de atraso absoluto zero. A resolução de 40 ms e o viés possível de modelo/recorte continuam existindo.

## Antes e depois

Resultados do cálculo original com padding, na condição sem atraso adicional de controle:

| Trecho | Offset antes | Distância mínima antes | Confidence antes | Offset depois | Distância mínima depois | Confidence depois |
|---|---:|---:|---:|---:|---:|---:|
| Início | −80 ms | 7,1165 | 8,4081 | 0 ms | 7,0088 | 8,7249 |
| Meio | −80 ms | 5,6587 | 9,5574 | 0 ms | 5,4992 | 10,0008 |
| Fim | −80 ms | 7,0134 | 8,2347 | 0 ms | 6,8969 | 8,4967 |

No cálculo sem bordas, os offsets também foram −80/0 ms antes/depois. Suas distâncias mínimas foram 7,1042/7,1128 no início, 5,4549/5,4648 no meio e 6,1221/6,0885 no fim. A mínima já permite procurar o melhor deslocamento; não se espera que ela caia muito apenas por corrigir o tempo. Na posição fixa de offset zero, a distância original foi 15,3877, 15,2160 e 14,9350; após a correção, passou para 7,0088, 5,4992 e 6,8969. Isso sustenta a mudança temporal no critério desta rede.

A coleta inicial levou 13,714 s dentro do adaptador, 16,515 s no subprocesso. A reavaliação levou 16,717 s dentro do adaptador, 19,452 s no subprocesso. Esses tempos incluem extração e controles; não são um benchmark isolado da máquina, que executava outros trabalhos.

## Cópia diagnóstica e preservação do áudio

Por orientação da coordenação, foi aplicada uma mudança reversível somente ao arquivo derivado: **atrasar o vídeo em dois quadros**, clonando o primeiro quadro. O áudio não foi adiantado por corte. Comando registrado integralmente em `correction-command.json`:

```bash
rtk proxy ffmpeg -i baseline-original.mp4 -map 0:v:0 -map 0:a:0 \
  -vf tpad=start=2:start_mode=clone -c:v libx264 -preset fast -crf 18 \
  -threads 2 -pix_fmt yuv420p -fps_mode passthrough -c:a copy \
  -movflags +faststart baseline-video-delay80ms.mp4
```

Não foi usado `-shortest`. Só o vídeo foi recodificado. O novo arquivo tem **651 quadros/26,04 s**, enquanto o AAC mantém **25,96 s**. A decodificação completa do AAC de ambos os arquivos produziu **2.492.160 bytes PCM16 idênticos**, SHA-256 `49c25a59d5bd31f8cdf4219bdb04e1f46995e6b4e219f38172ad8ea4d6c805cc`. O original continua com o mesmo hash. O derivado tem SHA-256 `dfb28957ef5b57921d44c0b4ec244a303f5c2087fe53934ca91a34aee83d207d`.

Essa cópia não contém voz, movimento ou cenário novos. O zero obtido depois não estabelece um limiar universal de aprovação do SyncNet nem confirma naturalidade. Não foi aplicada compensação automática ao pipeline de produção. A comparação humana deve ouvir o original e a cópia, com atenção ao início, meio e fim; não avaliar apenas timestamps ou frames parados.

## Artefatos e reprodução

Área privada: `video-generation-amostras/p06-pesquisa-naturalidade-20261015/syncnet/`, dentro da base de trabalho. Ela contém fonte/licença oficiais, peso recebido, MFCC auxiliar, adaptadores e diff, comandos, probes, checks de PCM, recortes inspecionados, embeddings e curvas completas de distância. Resultados anteriores: `results.json`; posteriores: `after-delay80ms/results.json`. Vídeo de comparação: `baseline-video-delay80ms.mp4`.

O ambiente temporário próprio foi removido às 16:31:24 UTC, após a coleta. O interpretador emprestado foi preservado. Pesos e evidências úteis ficam na área privada, com **79 arquivos conferidos em `SHA256SUMS`**, diretórios com modo `0700` e arquivos `0600`. O interpretador de outra tarefa não deve ser tratado como instalação permanente. Para reproduzir, recriar um ambiente CPU nas versões de `environment.json`, disponibilizar `dependency/` no `PYTHONPATH`, conferir hashes e usar diretório de saída novo. Os caminhos registrados em `scratch.json` e nos comandos descrevem a execução original, sem garantir que continuem existentes.
