# P06 — ensaio de dinâmica

Atualização de 16/10/2026: o usuário informou o aceite do vídeo masculino anterior e solicitou três novos pares de avatar/voz. O [lote adicional](P06-LOTE-ADICIONAL.md) registra os novos materiais e a situação atual do acesso à GPU. Os estados de recursos abaixo descrevem a rodada anterior, nas horas registradas.

O cliente gostou da demonstração anterior e pediu zoom e gesticulação. Esta rodada preserva a voz D aprovada. A [pesquisa e análise da referência](../research/P06-DINAMICA.md) registra as fontes primárias, a revisão do Astra e os limites de cada hipótese.

Pacote privado: `video-generation-amostras/p06-dinamica-20261015/`. Página de comparação: `revisao.html`. As saídas são candidatas para avaliação do usuário; não são aceite da P06 inteira nem mudança no worker de produção.

## Zoom sobre o vídeo anterior

Arquivo: `zoom/out/video-D-zoom-suave.mp4`, SHA-256 `87b756e50377c2ef0df87ad6fb956702f61b51ca7e42d137d73a83fcb4499a52`, 4.750.492 bytes. A finalização parte novamente do nativo D, mantém o atraso visual de três quadros de B e mapeia explicitamente o WAV D aprovado. Aplica aproximação de 1,00× a 1,06×, curva cossenoidal, âncora (0,5; 0,36), supersampling espacial 2× e `zoompan` com `d=1`, saída 1080×1920 e 25 fps. Plano e comando completos em `zoom/plan.json`.

O QC confirmou H.264/yuv420p, 246 quadros, 25 fps, 9,84 s, AAC/48 kHz e PTS monotônicos. O PCM decodificado é idêntico ao de B: SHA-256 `30e30021479b4e963ef76d79a0b41fd5dd83666e1c7a959228d112daa9eae0f9`. Em relação ao WAV D: lag zero, correlação 0,99997754 e sem clipping. O WAV D e B continuam com seus hashes originais.

O crop facial foi revisto nos quadros novos antes do score, mantendo a geometria oficial usada em B. SyncNet encontrou offsets de **0/0/+40 ms** nas janelas 1–5/3–7/5–9 s, em ambos os cálculos. Todos os controles de ±200 ms foram recuperados exatamente. Não houve regressão nesses critérios técnicos. As janelas se sobrepõem, a resolução é de 40 ms e o instrumento não mede naturalidade.

O agente de QC inspecionou início, meio, fim e folhas densas das junções; a coordenação também viu a comparação início/meio/fim. A aproximação está visível, com rosto e cabelo consistentes nas amostras, sem novo corte grosseiro. Não houve audição nem playback contínuo pelo agente. A suavidade percebida, preferência pelo zoom e naturalidade audiovisual ainda dependem da reprodução pelo usuário.

Relatório e resultados privados: `qc/ZOOM-RESULTADO.md`, `qc/ZOOM-RESULTADO.json`, `qc/zoom_cpu-media/`, `qc/zoom_cpu-syncnet/` e `qc/zoom_cpu-dense/`.

## Protótipo de gestos

A imagem anterior era um busto e o prompt mantinha as mãos fora do quadro. Foi preparada uma edição de meio corpo do mesmo personagem virtual, com cotovelos, antebraços e mãos presentes. A coordenação inspecionou tanto a edição quanto a entrada preparada antes da inferência.

- Edição: `gestos-image/avatar-masculino-meio-corpo-candidato-01.png`, 940×1672, SHA-256 `6bf0bfd0c63d75b854c47dfedad9726b7a549280d665c439798042ae1cc0ef44`.
- Entrada preparada: `gestos-run/render/in/render_input.png`, 1092×2028, SHA-256 `3a99fc0fbc73475becdc338ef14695fd0c3e9b7142e5fb67be6decaaaf8557cc`.
- WAV D: SHA-256 `8af5824b914f83ede697de2235bda56aea5e69d2582ef83bef1eaea1e862e422`, 236.160 amostras, PCM16 mono/24 kHz, 9,84 s. Sem nova síntese ou mudança de entonação.
- Prompt: gesto explicativo único, palma aberta, amplitude moderada, mãos abaixo do rosto e retorno ao repouso; câmera fixa e escritório estável.
- Runtime: mesmo digest `cad3a59ea8afb4197179a02ce6702a48bb9bf8f3f79acb586645291b53c632b4`, A100 existente, bucket 448×832, quatro passos, seed 42, text CFG 1 e audio CFG 2. Sem nova VM ou download de pesos.

O plano de custo foi persistido antes da chamada: uma tentativa de 9,84 s, timeout de 2.400 s, até US$ 1,33067 de compute nesse limite, sem reserva artificial. Esse limite não inclui o período anterior de VM ligada nem storage e não é uma leitura do saldo. O controller iniciou em 16/10/2026 às 00:41:59 UTC; o gerador entrou no carregamento às 00:44:02 UTC.

O controller concluiu com `passed` às 01:03:43 UTC. O preflight levou 108,74 s; o estágio de avatar levou 1.195,29 s (19 min 55 s), exit code 0 e sem timeout. O WAV permaneceu intacto. Todos os arquivos foram copiados e conferidos contra os hashes remotos; `docker ps` estava vazio e a GPU sem memória ocupada após a execução. O scratch de coleta foi removido, inclusive na primeira tentativa, que falhou por indentação no coletor local antes de transferir arquivos. O coletor foi corrigido e a coleta verificada concluiu em seguida.

O nativo tem SHA-256 `6d62b8f7a4b6ed50150264c1fe7eae024e47cb2c5d7540fc3c8453f901e9ea6f`. A versão finalizada `gestos-run/render/out/video-D-gestos-base.mp4` tem SHA-256 `30f5dd22ae0d6ac44e583e65732db64aa9b014b999a088a01478a2e823f884dc`: H.264/yuv420p, 1080×1920, 25 fps, AAC/48 kHz e 9,84 s nos dois streams. A finalização mapeia o WAV D inteiro, sem compensação visual ou `-shortest`.

O tempo do pipeline corresponde a aproximadamente US$ 0,723 de compute à tarifa registrada. É uma estimativa proporcional, sem tempo anterior/posterior, storage ou arredondamento de cobrança; não é saldo nem fatura. Recibo em `gestos-run/execution/cost-receipt.json`.

O QC da base confirmou preservação e alinhamento de áudio. O crop facial novo `(260,240,560,560)` foi fixado a partir da geometria e visto antes do score. SyncNet mediu **−80/−120/−80 ms** nas três janelas, nos cálculos com padding e interior comum. Confidence interior: 6,42/6,74/7,23. Todos os controles de ±200 ms foram recuperados exatamente.

A coordenação escolheu a mediana de −80 ms: duas candidatas com **+80 ms na imagem**, mantendo o WAV D inteiro, 246 quadros e 9,84 s. São dois clones do primeiro quadro e descarte dos dois quadros visuais finais; não há deslocamento do áudio. Ambas partem do nativo, com uma única codificação final. A candidata de câmera fixa e a de zoom usam o mesmo ajuste temporal; sua comparação isola o efeito da câmera. O ajuste de três quadros do vídeo anterior não foi transferido.

| Candidata | SHA-256 | Bytes |
|---|---|---:|
| `video-D-gestos-sincronia.mp4`, câmera fixa | `27eb377931ae146bf1c190b29366cb0676603872b7a14dbb1bedb818e161bb3d` | 4.388.663 |
| `video-D-gestos-zoom.mp4`, aproximação 1,00×→1,06× | `f6db71f3e5e9cf537bde4fb19e1f39c37a92c07bb1523850967b459054479346` | 4.974.679 |

O zoom novo usa âncora (0,5; 0,25), escolhida para preservar margem acima da cabeça nesse plano de meio corpo, supersampling 2× e `d=1`. Os comandos completos estão em `gestos-run/execution/fixed-sync.plan.json` e `combined.plan.json`.

A coordenação viu o contato de 12 quadros e as três folhas densas da base. As mãos mudam de posição, abrem e se aproximam do abdômen; rosto, roupa e escritório parecem consistentes na amostragem. Não foi visto salto espacial grosseiro nas três junções examinadas. O Astra inspecionou 13 quadros e quatro recortes de mãos: confirmou gesto reconhecível e ausência de pose congelada nas amostras. Não viu membro extra ou punho desconectado. Os dedos ficam suaves nas sobreposições; isso impede certificar anatomia fina e exige playback para avaliar fusão e velocidade. Não houve audição ou reprodução contínua pelo agente.

O ensaio combina nova imagem e novo prompt; não isola a contribuição de cada um. O movimento observado enfraquece a hipótese de que trocar o modelo seria necessário apenas para conseguir gestos, sem provar naturalidade completa.

O QC final confirmou **0/−40/0 ms** nas duas candidatas e nos dois cálculos SyncNet. Todos os controles de ±200 ms foram recuperados exatamente, mantendo o mesmo crop geométrico, revisto antes dos scores. O residual máximo foi de um quadro, dentro do critério fixado. Mídia: 246 quadros, 25 fps, 9,84 s e PTS monotônicos. O PCM decodificado das duas versões é idêntico entre si e ao das anteriores: SHA-256 `30e30021479b4e963ef76d79a0b41fd5dd83666e1c7a959228d112daa9eae0f9`, lag zero em relação a D. A checagem de áudio não equivale a ouvir a voz.

O QC examinou início/meio/fim, mãos/cotovelos e pares das junções finais. A coordenação também viu as comparações finais de corpo e mãos. Cabeça, mãos e cotovelos permanecem no enquadramento com o zoom. Os contatos continuam suaves. A página reúne quatro versões: B anterior, B com zoom, gestos com câmera fixa e gestos com zoom. Os alvos locais existem; não foi declarado teste de playback do HTML.

**As candidatas passaram pelos critérios técnicos executados. O aceite humano de naturalidade audiovisual continua pendente.** A versão de câmera fixa permanece disponível para avaliar se o zoom ajuda. Não foi aplicada nenhuma alteração ao worker de produção.

## Recursos e encerramento

A VM temporária é `949b81b0-4b39-4eee-810b-45aa1fc39a0e`, `p06-avatar-d-temp-20261015`, US$ 1,996/h. Os discos temporários são `b1bc8e09-8ab6-419e-902d-b4a7aa23a625` (FIN03) e `5c8b82c5-f633-4335-a4da-2c0a11f60235` (clone FIN02 não usado). O volume original `OS-fHuXBon4` deve continuar preservado.

O Chrome for Testing foi encerrado. O acesso ao console passou a usar a extensão do Google Chrome normal. O login foi aceito e a Verda exigiu autenticação adicional: código de seis dígitos enviado ao e-mail da conta. A página não explica por que solicitou o código nessa sessão. A consulta de saldo e a exclusão dos recursos pelo painel dependem desse código. O teste usa o SSH existente.

Nenhuma exclusão foi executada até este registro. A VM continua cobrando. Desligar não basta para encerrar compute: é necessário excluir a instância, conforme [documentação oficial](https://docs.verda.com/cpu-and-gpu-instances/shutdown-hibernate-and-delete/). A [exclusão de storage](https://docs.verda.com/storage/deleting-storage/) mantém lixeira por 96 h; remoção permanente é uma etapa distinta. Coletar e conferir resultados antes da limpeza, sem incluir o volume original nos alvos.


O ambiente CPU temporário de QC foi removido ao terminar, com zero processos de avaliação ativos. Scripts, freeze, bootstrap, resultados e pesos/cache existentes foram preservados. Os scratchs de upload/coleta e os dois fragmentos inválidos da primeira aquisição da referência também foram removidos. Relatórios finais: `qc/GESTOS-RESULTADO.md`/`.json` e `qc/ZOOM-RESULTADO.md`/`.json`; limpeza e inventário em `qc/setup/cleanup.json` e `inventory-final.json`. Os hashes dos MP4s, do nativo e do WAV D foram conferidos novamente, e os nove alvos de mídia/download da página existem. Não houve nova execução de GPU além do protótipo descrito.
