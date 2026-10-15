# P06 — ensaio de avatar com áudio D aceito

O usuário aprovou a voz D/N e depois informou que o cliente gostou da demonstração de áudio. O [registro da voz](P06-VOZ-APROVADA.md) identifica os arquivos, parâmetros e limites desse aceite. Este ensaio usa o WAV D preservado como entrada direta do avatar, sem nova síntese.

## Entradas e runtime

- WAV: `speech.wav`, PCM16 mono/24 kHz, 9,84 s, SHA-256 `8af5824b914f83ede697de2235bda56aea5e69d2582ef83bef1eaea1e862e422`.
- Imagem preparada: SHA-256 `d270167a7f3c80e9815735d6ed36d7fccd52ce97eaabd6ebe10321af1167c37e`. Canvas 1080×1920, escala 0,9; frame estendido 1092×2028, offset (6,54), bucket 448×832. Prévia inspecionada visualmente antes de gerar.
- Imagem worker: `vccr.io/5e20534f-f96c-42fb-8a52-deb4f7e28efc/avatar-worker@sha256:cad3a59ea8afb4197179a02ce6702a48bb9bf8f3f79acb586645291b53c632b4`.
- CLI direto de `avatar_stage.py`, perfil `480p-bf16-a100-lightx2v4`, quatro passos, guia de texto 1, áudio 2, streaming. Sem overlay ou mudança de sampler. O gerador registrou seed padrão 42 e `sample_shift=7`.
- Prompt de `RECIPE-prompt.json` descreve pequenos movimentos de cabeça e ombros, expressão ligada à fala e cenário estável. As mãos ficam fora do enquadramento; a foto não contém braços completos.

O ensaio mantém watermark nulo. Não satisfaz automaticamente C7/Perth nem integra Qwen no worker de produção. A saída nativa do avatar é 448×832; a finalização em 1080×1920 aplica a geometria registrada e a receita FFmpeg.

## Preparação verificada em 15/10/2026

O host novo iniciou com Ubuntu 24.04.5, driver NVIDIA 580.178.04, A100-SXM4-80GB e Docker 29.9.1. O digest do worker foi conferido após pull. O probe de tensor bf16 no Python do avatar passou: Torch 2.4.1+cu121, CUDA 12.1. Os hashes das entradas foram conferidos no host. A configuração temporária de autenticação Docker foi removida depois do pull.

Foram baixados apenas os 25 arquivos do perfil bf16, 92.910.998.503 bytes, usando o downloader canônico com tamanho e SHA-256 em streaming. Quatro grupos de arquivos distintos concluíram em 519,33 s. Os pesos quantizados não usados foram excluídos dessa seleção. Uma tentativa sequencial inicial foi interrompida durante download; a cópia parcial foi substituída e verificada na rodada paralela. Não houve geração de vídeo nessa tentativa de download.

Uma segunda conferência dos 25 arquivos em disco levou 69,39 s e validou novamente o WAV aprovado. O estágio de avatar iniciou às **19:03:08 UTC** e terminou às **19:22:48 UTC**, em **1.180,22 s**, com exit code 0 e sem timeout. O controller também concluiu com `passed`. O WAV permaneceu intacto. Os resultados foram copiados e seus hashes locais conferidos contra o manifesto remoto antes de qualquer limpeza.

## Resultado e verificações de mídia

O MP4 nativo tem SHA-256 `679d83d8bc748a6a611ae2f72cb03e2d6346fb1e90ebb9e5c46391cb44186739`: H.264, 448×832, 25 fps, 246 quadros e 9,84 s. Seu áudio interno é AAC/16 kHz, resampleado e normalizado pelo condicionamento do modelo; não é usado como fonte de áudio da versão final.

A finalização canônica usou explicitamente o WAV D preservado, sem `-shortest` ou deslocamento temporal. `video-D-revisao.mp4` tem SHA-256 `af03e7eb1a75f4d27cee497b456bd2aebf320fad839d71d513227de5f39783e1`: H.264/yuv420p, 1080×1920, 25 fps, AAC/48 kHz e 9,84 s nos dois streams. Essa dimensão resulta de upscale da geração nativa. O MP4 ocupa 4.599.782 bytes.

O QC local confirmou 246 quadros, PTS monotônicos e duração completa. Decodificado para mono/24 kHz, o áudio final tem as mesmas 236.160 amostras de D: lag global e dos três blocos igual a zero, correlação global 0,99997754 e sem clipping. Isso verifica preservação e alinhamento entre áudios; não é uma medida de sincronia labial nem audição humana.

Os três fontes do InfiniteTalk foram copiados do container em execução, sem nova inferência. O algoritmo usa quatro chunks de 81 quadros com contexto de nove; concatena 297 e corta para os 246 quadros do áudio. As junções mantidas ficam em 3,24 s, 6,12 s e 9,00 s, agora derivadas do código e confirmadas pela contagem final. O muxer interno usa `-shortest`; a ausência dessa opção acima refere-se somente à finalização externa. A análise com linhas e hashes está no pacote privado em `execution/runtime-source/ANALISE.md`.

A página privada `p06-avatar-d-20261015/revisao.html` apresenta a base como **A** e a candidata de sincronia como **B**, além do MP3 D aprovado, com reprodução separada. Alvos locais e hashes foram verificados estaticamente. A inspeção dos 12 quadros e das folhas densas nas junções encontrou rosto, cabelo, camisa e escritório consistentes, com pequenas variações de cabeça/expressão e sem salto espacial evidente entre os quadros adjacentes examinados. Essa amostragem não substitui playback contínuo nem comprova naturalidade audiovisual. Mãos e braços completos não estão no enquadramento.

Uma faixa muito fina acinzentada aparece na borda inferior ampliada; a causa não foi isolada e a relevância perceptiva depende de playback. A barba e a camisa ficam suaves após o upscale. Esses achados estão preservados no relatório privado, sem converter inspeção de quadros em nota de qualidade perceptiva.

## Sincronia e candidata comparativa

O primeiro crop quadrado manteve olhos/nariz/boca, mas deixou a boca próxima à borda inferior. O instrumento foi inconclusivo: offsets interiores de −600/−400/+200 ms, confidence de 0,41/0,83/0,56, busca atingindo limite e um controle falhando. Essa execução foi preservada e não orientou correção.

Uma única checagem de sensibilidade usou a geometria do `crop_video` oficial: bbox facial manual, `crop_scale=0.4`, crop quadrado `(56,480,1008,1008)` no MP4 de 1080×1920. A geometria foi fixada antes do score, sem alterar vídeo, áudio, rede ou pesos. O resultado respondeu aos controles e ficou consistente entre janelas. O contraste documenta a dependência do instrumento em relação ao crop; o primeiro score não prova uma falha do gerador.

| MP4, mesmo crop oficial fixado | Offset em 1–5 s | Em 3–7 s | Em 5–9 s | Confidence interior | Controles de ±200 ms |
|---|---:|---:|---:|---|---|
| A — base | −120 ms | −120 ms | −80 ms | 9,54 / 8,76 / 8,56 | Recuperados exatamente nas três janelas |
| B — imagem atrasada em três quadros | 0 ms | 0 ms | +40 ms | 9,30 / 9,17 / 8,83 | Recuperados exatamente nas três janelas |

Os offsets coincidiram entre o cálculo oficial com padding e o interior comum válido. São dois cálculos da mesma rede. Na convenção usada, o sinal negativo da base é compatível com áudio atrasado em relação à boca. A resolução é de 40 ms; as três janelas são sobrepostas. A cobertura efetiva interior aproxima-se de 1,60–8,36 s e não mede cada instante do vídeo nem toda a saudação/cauda.

A coordenação escolheu uma candidata comparativa de **+120 ms na imagem**, sem cortar, deslocar ou ressintetizar D. O FFmpeg partiu novamente do nativo: três clones do primeiro quadro, descarte dos três quadros visuais finais (243–245) e manutenção de 246 quadros/9,84 s. Isso evita uma segunda compressão sobre A. O começo e o fim foram examinados em quadros; há o prefixo estático previsto e encerramento em sorriso, sem corte grosseiro nas amostras. Os 120 ms finais do WAV têm energia muito baixa, mas o áudio foi mantido integralmente.

`video-D-sincronia.mp4` (B) tem SHA-256 `649841b1226f0c770a242a10c0be89b4eddfa575e04a177cff63b09e6f2a83aa`. O novo QC confirmou perfil/duração/PTS e lag zero em relação a D. Seu PCM decodificado é idêntico ao de A, SHA-256 `30e30021479b4e963ef76d79a0b41fd5dd83666e1c7a959228d112daa9eae0f9`. O novo SyncNet passou o critério fixado de residual até um quadro e controles recuperados, sem novo ajuste de crop. A permanece intacta.

Não houve segundo render neural nem uso adicional de GPU para essa compensação. B é uma candidata para avaliação, não um aceite humano de naturalidade. O agente não realizou audição direta ou playback audiovisual contínuo nesta sessão; a página A/B foi entregue ao usuário para esse julgamento. Resultados de mídia, ambas as geometrias, controles, quadros e relatórios estão em `revisao-protocolo/` no pacote privado. Nenhum offset foi propagado ao worker de produção.

Pacote privado fora do Git: `video-generation-amostras/p06-avatar-d-20261015/`. Requests e inputs em `render/in/`; scripts, hashes de pesos, checks e logs em `execution/`; protocolo de mídia/SyncNet em `revisao-protocolo/`. Segredos não fazem parte do bundle enviado à GPU.

## Recursos temporários e encerramento

| Recurso | ID | Uso |
|---|---|---|
| A100 On-Demand FIN-03 | `949b81b0-4b39-4eee-810b-45aa1fc39a0e` | Uma única VM de teste, US$ 1,996/h |
| OS novo FIN-03 | `b1bc8e09-8ab6-419e-902d-b4a7aa23a625` | 250 GiB temporários; modelos baixados e render |
| Clone FIN-02 | `5c8b82c5-f633-4335-a4da-2c0a11f60235` | Cópia temporária não usada, ainda Cloning na última observação autenticada às 18:54:43 UTC |
| Volume original FIN-01 | `OS-fHuXBon4` | Preservado, sem attachment à VM nova; não remover |

O custo exibido/plano com compute e três discos era aproximadamente US$ 2,20147/h. Não há reserva artificial de US$ 1. A limpeza deve conferir os resultados locais antes de remover os recursos temporários. O volume original fica preservado.

O console perdeu sua sessão acessível pela automação depois do provisionamento. A camada nativa falhou ao localizar janelas; os canais DOM do Brave e Chrome chegaram à tela de login. Uma aba de handoff foi aberta para o usuário em `console.verda.com/signin`. O usuário foi avisado e recebeu pedido de conexão. Nenhuma exclusão foi executada: **a VM temporária ainda gera cobrança e depende de acesso autenticado para encerramento**. Não confundir esse bloqueio com falta de saldo.

Depois da cópia verificada, `docker ps` estava vazio: o container `--rm` e a telemetria do render terminaram. O scratch local de upload/coleta foi removido, preservando os resultados e os logs extraídos. Isso não encerra a cobrança da VM. O volume original não foi anexado à nova instância nem incluído em qualquer alvo de remoção.

Após o QC, o ambiente CPU temporário também foi removido, com zero processos de avaliação ativos. Scripts, freeze, bootstrap, resultados e caches/modelos existentes foram preservados. A checagem final do console ainda mostrou Sign in; nenhum shutdown ou delete foi executado. Evidência privada: `verda-recarga/final-cleanup-blocked.json`. O encerramento da VM e a limpeza dos dois discos temporários continuam bloqueados pelo acesso, com os IDs acima para a próxima ação.

Desligar a VM mantém cobrança; o encerramento de compute exige remover a instância temporária. Os discos escolhidos para manter continuam cobrando. [Procedimento oficial de shutdown/delete](https://docs.verda.com/cpu-and-gpu-instances/shutdown-hibernate-and-delete/). A exclusão inicial de storage vai para a lixeira de 96 h; a remoção permanente é a etapa que libera a quota. [Procedimento oficial de storage](https://docs.verda.com/storage/deleting-storage/).

## Aceite pendente

O cliente aprovou a demonstração de voz masculina. O ensaio novo passou pelas verificações técnicas descritas acima; a avaliação humana de movimento e naturalidade audiovisual continua pendente. O ajuste desta rodada foi medido em D e não transferido do vídeo feminino anterior. Voz feminina e integração Qwen de produção permanecem fora do aceite obtido. A P06 inteira continua em andamento.
