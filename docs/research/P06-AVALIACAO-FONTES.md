# P06 — avaliação audiovisual de naturalidade e fontes

Pesquisa de 15/10/2026. Escopo: escolher instrumentos de diagnóstico e um ensaio econômico para voz, movimento, estabilidade e sincronia. Este documento não muda C1–C7, não concede aceite humano e não congela receita.

**A avaliação precisa separar quatro coisas:** texto correto, voz/entonação, sincronismo boca–fala e naturalidade visual. Uma métrica de uma dessas dimensões não aprova as outras. O caminho econômico é resolver a voz antes de renderizar; depois comparar variantes visuais com os mesmos bytes do áudio aprovado.

## Estado real que motivou a pesquisa

O [registro atual da P06](../homologacao/P06-QUALIDADE.md) documenta duas demos CUDA com palavras recuperadas pelos ASRs, mas reprovadas pelo usuário em **“A voz e a entonação”**. As opções MPS A/B também tiveram palavras recuperadas; a avaliação humana posterior foi que melhoraram, mas continuam robóticas, sobretudo em “olá” e na entonação das frases. Não houve escolha ou aceite de A/B. Esse dado humano vale mais para a queixa de prosódia que uma transcrição correta.

No ensaio MPS C, pedido/preço/telefone continuam divergentes no diagnóstico. Em D, por extenso, a guarda D001 recusou publicação por falta de EOS terminal; não há WAV nem comparação auditiva C–D. EOS e Perth são verificações de conclusão/proveniência, não medidas de naturalidade. Não houve nova inferência de avatar nesta rodada; o ensaio temporal posterior deriva do vídeo antigo.

## Inspeção executada do vídeo anterior

O pacote privado está em `video-generation-amostras/p06-pesquisa-naturalidade-20261015/diagnostico/`. Ele contém cópia identificada do MP4 anterior, WAV original, áudio final decodificado, FFprobe, PTS, contato de 12 quadros, waveform/espectrograma, CSVs/JSONs e uma página local `revisao-av.html`. Não substitui a página da rodada anterior.

| Observação local | Resultado | O que não permite concluir |
| --- | --- | --- |
| Identidade do MP4 | SHA-256 `ca29e2b64dcbd48b476d711f61d4c822b7c3824a81f440982b8419903ffbccaa` | Não é vídeo novo nem amostra aprovada |
| Formato | 25,96 s, 649 frames, 1080×1920, H.264/25 fps/AAC 48 kHz | Render nativo era 448×832; exportação ampliada não recupera detalhe |
| PTS de vídeo | 0–25,92 s, passo de 40 ms em todos os intervalos | Cadência regular não prova boca sincronizada |
| WAV TTS versus AAC decodificado | Ambos com 623.040 amostras a 24 kHz; lag de correlação 0 amostras/0 ms; correlação 0,999974 | Isso compara dois áudios. Não mede sincronismo audiovisual |
| Janelas de áudio de 2 s em 0/5/10/15/20/23 s | Lag estimado 0 em todas | Não é teste de alinhamento fonético ou deriva labial |
| Primeiro pacote AAC | PTS −21,333 ms e `skip_samples=1024` | Priming do codec não deve ser confundido automaticamente com atraso perceptivo; o PCM decodificado foi comparado separadamente |
| Contato visual | Boca/olhos/expressões variam, ombros variam menos e fundo mantém a organização | Quadros não aprovam transições, naturalidade contínua ou lip-sync |

Em ROIs manuais, a diferença absoluta média de intensidade, em vídeo reduzido a 160×288/5 fps, foi 0,24/255 no fundo superior, 12,72 na face, 20,18 na região aproximada da boca e 2,70 em ombros/torso. **Isso é variação de pixels, não landmarks, pose ou fluxo óptico.** Não houve compensação de câmera; iluminação, codec e deslocamento dentro da ROI podem contribuir.

No áudio original, RMS global foi −24,90 dBFS e pico −4,93 dBFS, sem amostras com módulo ≥0,999. Um detector exploratório por energia encontrou 11 intervalos ≥150 ms abaixo de −35 dBFS, incluindo cauda. F0 exploratório por autocorrelação filtrada teve percentis 10/50/90 de aproximadamente 145/195/240 Hz. Não é implementação do Praat: faltam seleção dinâmica de candidatos e correção de oitavas. Esses números não demonstram que a voz é natural, robótica ou monótona. Os parâmetros e limites estão nos JSONs/CSV do pacote.

Na inspeção inicial do vídeo anterior, OpenCV, MediaPipe e Praat não estavam instalados no ambiente usado. A extração básica usou FFmpeg, NumPy, SciPy e Pillow existentes, em CPU. A etapa acústica posterior dos WAVs E/F/G/J usou um wrapper Praat instalado em ambiente temporário separado, descrito abaixo. Neste diagnóstico inicial não foram executados SyncNet, landmarks, optical flow ou preditores MOS. Um ensaio SyncNet posterior, com controles reais, está registrado em [P06-SYNCNET-ENSAIO.md](P06-SYNCNET-ENSAIO.md). As imagens foram efetivamente inspecionadas. O agente não dispõe de audição direta nesta sessão.

### Forma legítima de observar áudio e imagem

`revisao-av.html` reproduz o MP4 original com som, permite buscar tempos, compara os dois áudios e apresenta waveform/espectrograma. Um avaliador real pode registrar observações com tempos e exportar o que ele próprio preencheu; nada vem aprovado e a página não calcula MOS. A interface resolve o acesso à mídia para o usuário, não cria audição para o agente. Sem retorno humano ou ferramenta multimodal que efetivamente receba áudio, o agente deve declarar essa limitação. ASR e espectrograma são apoio, não uma escuta substituta.

## Instrumentos e licenças verificadas

Licenças de código e de pesos são separadas. Antes de incorporar um instrumento, registrar commit/revisão, URL exata, SHA-256 dos pesos e licença daquela distribuição. O levantamento inicial não baixou pesos de avaliação. O ensaio SyncNet posterior obteve o peso oficial com proveniência registrada em documento separado.

| Instrumento | Medida útil e execução possível | Código/pesos e limites |
| --- | --- | --- |
| **FFmpeg/FFprobe** | Timestamps, extração de PCM/frames, waveform/espectrograma e diagnóstico de silêncio em CPU, sem pesos | Licença depende do build. O executável local 9.0.2 foi compilado com `--enable-gpl --enable-version3` e declara GPL-3.0 ou posterior; não representa automaticamente a licença de outro build. [Licenciamento oficial](https://ffmpeg.org/legal.html) |
| **SyncNet original** | Offset, distância e confiança entre embeddings de áudio e face; repositório inclui rota CPU | Código MIT. A página Oxford oferece modelos sob CC BY 4.0 e descreve uso em pesquisa. Fixar o modelo e dependências de detecção separadamente. [Código](https://github.com/joonson/syncnet_python), [distribuição Oxford](https://www.robots.ox.ac.uk/~vgg/software/lipsync/) |
| **MediaPipe Face Landmarker** | 478 landmarks, 52 blendshapes, transformação facial; boca, olhos e pose rígida da cabeça | Código Apache-2.0; cards Face Mesh V2/Blendshape V2 declaram Apache-2.0. Fixar o bundle exato. É um estimador com jitter/domínio próprio, não detector de naturalidade. [Guia](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [Face Mesh card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf), [Blendshape card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf) |
| **MediaPipe Pose Landmarker/BlazePose GHUM** | 33 pontos, incluindo ombros, com presença/visibilidade; opções Lite/Full em CPU | Card dos pesos declara Apache-2.0. Foi otimizado para corpo inteiro/fitness; busto cortado limita o uso e pode gerar estimativas de partes invisíveis. [Guia](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker), [card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) |
| **OpenCV ≥4.5** | Lucas–Kanade, Farnebäck e registro de movimento em CPU; esses algoritmos não exigem pesos neurais | Apache-2.0 nas versões ≥4.5; versões anteriores usam BSD de três cláusulas. [API](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html), [licença](https://opencv.org/license/) |
| **Praat** | F0, intensidade, vozeamento, espectrograma e TextGrid/pausas em CPU | GPL-3.0 ou posterior; não precisa de pesos. A análise preferida de entonação atual é autocorrelação filtrada. [Método](https://praat.org/manual/how_to_choose_a_pitch_analysis_method.html), [licença](https://praat.org/manual/License.html) |
| **Whisper + JiWER** | ASR e cálculo de WER/CER; modelos já usados só como diagnóstico | Modelo oficial Whisper turbo MIT; JiWER Apache-2.0 e sem pesos próprios. Fixar também a conversão MLX utilizada. ASR pode errar; WER mede a hipótese transcrita, não timbre/entonação. [Modelo](https://huggingface.co/openai/whisper-large-v3-turbo), [JiWER](https://github.com/jitsi/jiwer) |
| **UTMOS22** | MOS predito para fala sintética, como triagem relativa | Repositório MIT; demo oficial declara MIT. A cadeia de checkpoints SSL/bundle deve ser fixada e conferida. O strong learner público do main track foi treinado em inglês; o paper também avalia OOD em chinês. Isso não calibra o score para esta voz pt-BR. [Código](https://github.com/sarulab-speech/UTMOS22), [demo/licença](https://huggingface.co/spaces/sarulab-speech/UTMOS-demo/blob/main/README.md), [paper](https://arxiv.org/html/2204.02152v2) |
| **DNSMOS P.835** | Scores preditos SIG/BAK/OVRL para sinal, ruído e conjunto; ONNX permite CPU | Código MIT em `LICENSE-CODE`; repositório traz licença geral CC BY 4.0. Não atribuir MIT automaticamente ao ONNX sem conferir o artefato. Foi desenhado para ordenar supressores de ruído, com desempenho agregado melhor que por clipe; não é avaliador dedicado de prosódia TTS. [Código/README](https://github.com/microsoft/DNS-Challenge/tree/master/DNSMOS), [licença do código](https://raw.githubusercontent.com/microsoft/DNS-Challenge/master/LICENSE-CODE), [licença geral](https://raw.githubusercontent.com/microsoft/DNS-Challenge/master/LICENSE), [paper](https://arxiv.org/html/2110.01763v4) |
| **NISQA / NISQA-TTS** | NISQA mede degradações de transmissão; `nisqa_tts.tar` estima naturalidade sintética | Código MIT, mas **os três pesos oficiais são CC BY-NC-SA 4.0**. Não levar esses pesos para o produto comercial como se fossem MIT. Escolher o checkpoint do domínio correto. [Código/pesos/licenças](https://github.com/gabrielmittag/NISQA#paper-and-license), [paper TTS](https://www.isca-archive.org/interspeech_2020/mittag20_interspeech.html) |

O framework de avaliação Wav2Lip popularizou LSE-D/LSE-C usando SyncNet. Seu README restringe resultados do código/modelos open-source a pesquisa/uso acadêmico/pessoal; não confundir com a licença do SyncNet original nem copiar a cadeia inteira para produção sem revisão. [Avaliação](https://github.com/Rudrabha/Wav2Lip/blob/master/evaluation/README.md), [restrição declarada](https://github.com/Rudrabha/Wav2Lip#disclaimer).

## Como usar as medidas sem criar falsos gates

### Sincronia: SyncNet/LSE

O código original trabalha com 25 fps/áudio 16 kHz, compara janelas de cinco frames e procura deslocamentos. A distância mínima é menor quando os embeddings se aproximam; a confiança é a mediana das distâncias sobre os deslocamentos menos o mínimo. Não é uma probabilidade de “vídeo aprovado”. [Implementação primária](https://github.com/joonson/syncnet_python/blob/master/SyncNetInstance.py).

Usar face crop e pré-processamento fixos, relatar offset com convenção de sinal testada, LSE-D/LSE-C, cobertura e falhas por janela. A 25 fps, um passo visual é 40 ms. Validar o instrumento com áudio deslocado em ±200/±400 ms e vídeo com boca congelada, além de referência audiovisual autorizada. O ensaio posterior executou os controles de deslocamento de áudio; o controle de boca congelada continua proposto. Os detalhes e limites estão no registro SyncNet separado. Não adotar “LSE acima/abaixo de X” como aceite universal sem calibrar o mesmo checkpoint/crop/domínio. A recomendação [ITU-R BT.1359](https://www.itu.int/rec/R-REC-BT.1359-1-199811-I/en) trata tempo relativo de som/imagem; suas tolerâncias de broadcasting não viram automaticamente critério de naturalidade deste avatar.

### Face, boca, cabeça e ombros

Proposta de extração: abertura labial normalizada por distância interocular, piscadas/olhos, ângulos de cabeça e deslocamento dos ombros normalizado pela largura do torso. Registrar velocidade, aceleração, interrupções e erro de tracking. Separar transformação rígida da cabeça de deformação da boca. Mais movimento ou maior variância não implica melhor atuação. A card do Face Mesh relata normalização interocular e aumento de jitter com condições adversas; isso precisa aparecer como incerteza, não como defeito do avatar automaticamente. [Card primário](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf).

Não converter landmark ausente em zero, interpolar longas falhas ou atribuir pose a ombros/mãos fora do quadro. Registrar confiança, cobertura, smoothing e frames perdidos. A suavização do detector também pode esconder tremor. Para uma interpretação de naturalidade, comparar a distribuição de movimentos a vídeos humanos autorizados de enquadramento e tarefa semelhantes e confirmar com pessoas.

### Fluxo óptico e compensação de câmera

Proposta: detectar features no **fundo**, excluindo a pessoa; estimar transformação global robusta (afim/homografia conforme a cena), alinhar frames e medir fluxo residual em face/ombros/fundo/bordas. Lucas–Kanade e Farnebäck estão na API oficial; `findTransformECC` oferece registro por intensidade. [OpenCV tracking](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html).

Relatar movimento global separado do residual, inliers e casos de falha. Estimar a câmera usando o rosto pode apagar o movimento de cabeça que se quer medir. Parallax, iluminação, oclusão e compressão confundem o fluxo. Métricas úteis são cobertura, mediana/p95 do residual, picos localizados e mapas temporais; um score global não diz se o gesto combina com a frase. Nada disso foi executado no baseline atual.

### F0, pausas e voz

Usar Praat com faixa de pitch registrada e revisão de saltos de oitava; comparar F0 em semitons relativos à mediana do próprio locutor, contorno de saudação/fim de frase, duração e localização de pausas, intensidade e ritmo. Manter o texto e o sistema de reprodução como controles. O manual explica como faixa e janela mudam o resultado e recomenda autocorrelação filtrada para entonação. [Método](https://praat.org/manual/pitch_analysis_by_filtered_autocorrelation.html), [configuração](https://praat.org/manual/Intro_4_2__Configuring_the_pitch_contour.html).

Não usar uma faixa de F0 “ideal feminina/masculina”, nem equiparar F0 estreito a voz robótica. Timbre, articulação, coarticulação e expressividade não se reduzem ao pitch. Detectores de silêncio por limiar são úteis para localizar regiões, mas não delimitam palavras ou pausas linguísticas sozinhos. [FFmpeg silencedetect](https://ffmpeg.org/ffmpeg-filters.html#silencedetect).

### WER/CER e conteúdo crítico pt-BR

WER = (substituições + exclusões + inserções) / palavras de referência; CER usa caracteres. Calcular contra transcrição humana validada quando a finalidade for medir erro real da fala. Contra hipótese ASR, chamar de **divergência ASR**, mantendo texto bruto e normalizador versionados. [JiWER](https://github.com/jitsi/jiwer).

Para pt-BR, separar apresentação de números por extenso/dígitos, valores, telefones, datas e negativas. Um normalizador pode reconhecer representações equivalentes, mas nunca apagar “não”, trocar um valor ou aproximar dígitos para melhorar score. Acrescentar checagem de entidades críticas e escuta palavra por palavra. Dois modelos da família Whisper têm erros correlacionados; concordância entre tamanhos não equivale a dois avaliadores humanos independentes. A correspondência lexical já favorável das demos e a queixa humana de voz/entonação mostram por que WER/CER não são gates de naturalidade.

### MOS predito e MOS humano

UTMOS, DNSMOS e NISQA retornam **predições**, não opiniões humanas novas. Usar coluna `mos_predito_modelo_revisao`, nunca preencher C1–C7 ou `MOS_humano` com esses números. Não comparar scores de modelos diferentes como se compartilhassem escala/calibração. O estudo UTMOS explicita diferenças de domínio/listener e dados inglês/chinês; DNSMOS destaca domínio limitado de degradações e agregação. O paper NISQA-TTS propõe independência de língua, mas isso não demonstra calibração para Chatterbox/pt-BR, esta referência e esta queixa específica. [UTMOS](https://arxiv.org/html/2204.02152v2), [DNSMOS](https://arxiv.org/html/2110.01763v4), [NISQA-TTS](https://www.isca-archive.org/interspeech_2020/mittag20_interspeech.html).

Nenhuma das fontes consultadas fornece um limiar validado de aprovação para esta instalação. Para usá-los como triagem, primeiro medir concordância/ranking com ouvintes pt-BR no pequeno corpus local, incluindo falhas conhecidas. Um áudio limpo e robótico pode pontuar bem em uma medida de ruído.

## Desenho econômico proposto

Os números abaixo são uma proposta de piloto, não exigência numérica da ITU nem cálculo de poder concluído. [P.808](https://www.itu.int/ITU-T/recommendations/rec.aspx?id=14665) cobre material, ouvintes, ambiente e análise; [P.910](https://www.itu.int/rec/T-REC-P.910) é a referência atual para avaliação audiovisual (edição 07/2026 aparece como em vigor/prepublicada na consulta). P.913 foi retirada em 2024 e incorporada à P.910; não usar uma cópia antiga como norma vigente. [Estado P.913](https://www.itu.int/rec/T-REC-P.913).

1. **Triagem sem render:** duas variantes TTS, três textos curtos fixos e três seeds predefinidas = 18 WAVs. Incluir saudação, frase informativa e números/negativas. Preservar referências, backend, versões, volume e parâmetros que não estão sob teste. Se houver falha de literalidade ou EOS, registrá-la, sem descartar seeds ruins silenciosamente. Um texto/seed não demonstra robustez.
2. **Audição A/B cega:** inicialmente 8–12 ouvintes nativos pt-BR, fones e volume de reprodução constante. Randomizar identidade e ordem A/B; usar os mesmos pares por texto/seed, com opção empate. Pedir preferência de voz/entonação separada de inteligibilidade; recolher exemplos com tempo. Reutilizar uma demo já reprovada como controle de falha, uma referência humana autorizada quando disponível e repetição oculta de parte dos itens para consistência. O piloto com poucos ouvintes é exploratório.
3. **Separar fatores:** para voz/prosódia, manter texto e referência; para variante visual, usar **o mesmo WAV exato e hash**, mesmo cenário/foto/canvas e seeds pareadas. Alterar apenas prompt ou composição por comparação. Não normalizar ou recortar arquivos silenciosamente. Se uma versão para escuta com loudness ajustado for criada, identificá-la como derivada e aplicar a mesma regra a todas; preservar originais.
4. **Render por etapas:** só após direção vocal satisfatória, fazer primeiro um par visual de 8–12 s. Se houver melhora sem defeito material, ampliar a três seeds (seis clipes). Assistir com som a 1×, além da inspeção quadro a quadro. Avaliar boca, cabeça/olhos/ombros, transições, objetos/mãos inventados, identidade e fundo. Clipes congelados e offsets conhecidos servem para validar detectores, não para fingir amostras do produto.
5. **Estatística com unidade correta:** publicar número de ouvintes, textos, seeds, votos, empates, falhas e distribuição por item. Estimar diferença pareada/preferência e IC de 95%, com reamostragem por ouvinte e item (texto×seed), ou modelo de efeitos mistos quando houver dados suficientes. Frames, palavras e várias notas do mesmo ouvinte não são observações independentes. Se o intervalo for amplo, concluir “inconclusivo” e ampliar o piloto conforme regra definida antes, sem escolher só o melhor seed. [NTIA: precisão e IC em qualidade audiovisual](https://its.ntia.gov/publications/details?pub=3253).
6. **Aceite e MOS:** uma fala do usuário é feedback real e pode reprovar uma direção, mas não deve virar MOS inventado. Um MOS humano exige notas reais e método declarado, com contagem e incerteza. O texto completo da P.808 recomenda considerar ICs e teste estatístico apropriado ao desenho. [P.808, análise e reporte](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-P.808-202106-I%21%21PDF-E&lang=e&type=items).

Critérios propostos para a rodada: zero trocas humanas confirmadas de entidades/negativas no pequeno corpus; nenhuma publicação sem EOS; ausência de defeitos graves de identidade/bordas; preferência humana de voz/movimento sem regressão de conteúdo/sync e com incerteza exposta. **Não há threshold universal proposto de LSE, F0, fluxo, UTMOS, DNSMOS ou NISQA.** Os critérios finais continuam sujeitos ao contrato C1–C7 e ao cliente.

## Referências de voz: apoio ao contrafactual solicitado

Em janela explicitamente autorizada pela coordenação, Whisper large-v3-turbo transcreveu `pf_dora.wav` e `pm_alex.wav`, com timestamps por palavra. O processo terminou antes de liberar a GPU local para novas inferências. Os dois textos reconhecidos começam com “Olá, esta é uma voz sintética de referência...”. JSONs completos, hashes e probabilidades estão no diagnóstico privado para reutilização da transcrição em ICL.

Nas duas referências, ASR marca fim de “Olá” em 0,40 s e início de “esta” em 0,66 s. Isso é estimativa ASR, não fronteira fonética humana exata. O ponto sugerido de 0,53 s (frame PCM 12.720 a 24 kHz) fica no meio do intervalo e tem energia de 10 ms de −53,9/−53,2 dBFS nas referências feminina/masculina. A análise não recortou as referências. Um contrafactual pode preservar exatamente o PCM restante, sem normalização, resampling ou fade, registrando novo hash e transcrição correspondente. Uma melhora após remover a saudação seria indício local a repetir, não prova geral de causa.

## Etapa acústica real: E/F/G/J

Os quatro WAVs publicados foram medidos em CPU com `praat-parselmouth==0.4.7` e `numpy==2.2.6`, instalados por wheels em ambiente temporário privado. Parselmouth acessa o código do Praat; a versão estável usada embute **Praat 6.1.38**. Sua autocorrelação clássica não é o método filtrado recente recomendado acima. Faixa 75–500 Hz, passo 10 ms e demais parâmetros foram fixados e salvos. [Distribuição PyPI](https://pypi.org/project/praat-parselmouth/0.4.7/), [API/versão embutida](https://parselmouth.readthedocs.io/en/stable/api_reference.html).

E/F são Chatterbox MPS com referência original versus o corte de 0,53 s; G/J fazem a mesma comparação de referência no Qwen MLX, com o texto ICL correspondente ao áudio. O texto de saída é idêntico. Há uma realização por célula. O mesmo inteiro de seed entre sistemas não produz amostras aleatórias equivalentes. O corte altera o condicionamento completo; não identifica sozinho a causa da queixa vocal.

| Célula | Duração | F0 mediana vozeada | LUFS raw | Ganho constante da cópia de escuta |
| --- | --- | --- | --- | --- |
| E | 8,24 s | 202,0 Hz | −24,84 | +1,34 dB |
| F | 9,40 s | 182,8 Hz | −24,17 | +0,67 dB |
| G | 8,88 s | 185,2 Hz | −26,26 | +2,76 dB |
| J | 8,16 s | 186,3 Hz | −29,34 | +5,84 dB |

F0, intensidade e proxies de pausas estão em `diagnostico/acustica-ab/`, com CSVs, parâmetros e freeze. Maior extensão de F0 ou menor duração não implica naturalidade. A janela inicial de 1,5 s não delimita a palavra “Olá” sem alinhamento posterior. Não se calculou taxa fonética de articulação sem fronteiras validadas.

Foram criadas cópias **somente para escuta**, com alvo comum seguro de −23,5 LUFS e ganho fixo por arquivo. O medidor FFmpeg `loudnorm` teve saída descartada; os WAVs salvos passaram apenas por `volume`, sem compressor, limiter, resampling ou alteração de tempo. Os arquivos PCM24 e PCM16 derivados têm hashes próprios, contagem de amostras/duração conferidas e true peak abaixo de −2 dBTP. Os raws permanecem intactos. O futuro reuso precisa empregar os bytes do WAV efetivamente ouvido, sem chamá-los de raw idêntico. Volume comparável facilita a escuta e não demonstra melhora de timbre/entonação. [FFmpeg volume](https://ffmpeg.org/ffmpeg-filters.html#volume), [medidor loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm).

## Limites desta entrega

Pesquisa baseada em fontes primárias e documentação consultadas em 15/10/2026. Implementações/modelos devem ser fixados antes de uso; páginas `main/master/latest` podem mudar. Não houve instalação pesada, execução de preditor MOS, novo render, alteração da produção ou audição fictícia. Os dados automáticos expostos apoiam observação e planejamento; o feedback humano existente permanece preservado.
