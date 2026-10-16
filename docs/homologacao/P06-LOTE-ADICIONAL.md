# P06 — três novos pares de avatar e voz

Em 16/10/2026, o usuário informou que o cliente aprovou o vídeo masculino anterior e combinou mais um avatar masculino e dois femininos, com uma nova voz masculina e duas novas vozes femininas. Esta rodada gerou e entregou esses **três novos pares para avaliação**, preservando os arquivos anteriores. O relato não identifica um SHA específico entre as variantes do homem anterior; não foi atribuída aprovação automática a todas elas.

O aceite dos novos pares e a conclusão integral do projeto ainda estão pendentes. A receita parte das lições documentadas na [voz D](P06-VOZ-APROVADA.md) e no [ensaio de gestos e zoom](P06-DINAMICA.md).

## Entrega local

Pacote privado fora do Git: `video-generation-amostras/p06-novos-avatares-20261016/`. Página conjunta `revisao.html`: três vídeos com gestos e zoom, três novos áudios e a voz D para comparação. Há links para baixar MP4, MP3, PNG e a variante de câmera fixa. `entrega/` reúne três MP4s, três MP3s, três PNGs, página independente, instruções e créditos. O ZIP `novos-avatares-para-cliente.zip` contém somente esses 12 arquivos, por lista explícita. As cópias foram conferidas contra os hashes do QC e os manifestos canônicos de cada par; o ZIP passou em CRC e comparação dos bytes extraídos. Os 24 alvos locais da revisão e os 19 da página do cliente existem. No Google Chrome normal, os três vídeos e quatro áudios carregaram com durações corretas, sem erro de mídia. Não foi realizado playback completo nem audição pelo agente.

Os nomes Rafael, Ana e Marina são nomes de demonstração para as novas combinações. O texto mantém a mensagem aprovada e troca a apresentação: “Olá, eu sou o Rafael/a Ana/a Marina. Uma boa mensagem aproxima pessoas. Vamos apresentar sua ideia com calma, clareza e um jeito natural de conversar.” Os requests de voz contêm cada versão exata, com artigo e nome correspondentes.

| Par | Retrato PNG, SHA-256 | WAV de escuta para o avatar, SHA-256 | Duração / quadros previstos a 25 fps |
|---|---|---|---|
| Rafael — `homem-02` | `9b49e658e8d7cc32396598308cdd66f21d245656cb722c98720a0f23459ed4f8` | `4f138bd55e7489b0c64e2494cfb62fadbb6739c351f94861a6fd1882f1ddbd50` | 9,92 s / 248 |
| Ana — `mulher-01` | `d08173a22656ef15bd39266fa37caa89d0d34fede965c9e2631e7d9a7da25d13` | `dda666229207cd5dd10ea23358f58e0a7651e24ff42c0e001b2244f4bbe6ed7a` | 10,00 s / 250 |
| Marina — `mulher-02` | `373a474d4e0590d1634e84dc2dbd441f148bbdb2dfea1bcd773eeb1068a6a541` | `2b8951530af23b4dda766233e6f235d940c024b21b2191dc8e5c238511d2fff0` | 9,76 s / 244 |

As contagens desta tabela vêm dos WAVs e são o alvo de cada render. A verificação dos MP4s reais está descrita abaixo; não foi inferida aprovação dos novos pares a partir do aceite do homem anterior.

## Imagens e preparo

Três novas identidades adultas virtuais foram geradas pela ferramenta integrada `image_gen`. Os PNGs finais têm 941×1672 pixels, RGB. Escritório claro, plano até as coxas, mãos separadas abaixo do rosto, ambos os punhos, cotovelos e antebraços completos. A coordenação inspecionou os três originais e a grade das entradas preparadas. A inspeção estática não comprova anatomia ou estabilidade temporal na animação.

Rafael e Marina têm cerca de 9% de margem acima da cabeça; Ana tem cerca de 15%. A variante de Ana com mais margem foi escolhida para preservar espaço para movimento e zoom. As alternativas e prompts estão em `assets/`. Nenhuma imagem do homem aprovado foi sobrescrita.

O preparo local usa a mesma geometria do ensaio de gestos: `ImageOps.fit` central com Lanczos para 1092×2028, canvas final 1080×1920 e offset (6,54), bucket 448×832. A área retida supera 90%; mãos e cabeça continuam no quadro nas entradas vistas. Os inputs de cada par ficam em `renders/<id>/in/`, com SHA256SUMS e proteção contra escrita. Os WAVs foram copiados byte a byte das candidatas de escuta. O script `execution/prepare-pairs.py` não acessa rede nem lança inferência.

## Vozes e verificações

Foi preservada a receita aceita em D: Qwen3-TTS Base 1.7B MLX bf16, revisão `a6eb4f68e4b056f1215157bb696209bc82a6db48`, MLX-Audio 0.5.9, seed 20261015, temperatura 0,9, top-p 1, top-k 50, repetition penalty 1,5 e limite de 512 tokens. O ambiente foi reconstruído com Python 3.12.13 e freeze idêntico, somente por cache offline. Treze arquivos do modelo foram conferidos por SHA. Inferências e ASRs rodaram localmente, em sequência e com rede bloqueada, sem Verda ou outra API paga de voz.

Rafael usa referência humana Faber/OHF `pt_BR`, CC0. Ana e Marina usam dois clipes humanos distintos de [FLEURS, configuração `pt_br`](https://huggingface.co/datasets/google/fleurs), com gênero `FEMALE` e transcrição primária. A licença declarada é CC-BY-4.0; atribuição, revisão, IDs, transcrições e alterações estão em `voices/CREDITOS.md`. FLEURS não expõe `speaker_id` nesses clipes: não foi afirmado que são duas pessoas reais distintas.

As três sínteses terminaram com EOS real. WAVs PCM16 mono/24 kHz, sem clipping. As cópias de escuta receberam apenas ganho constante para −23,5 LUFS: Rafael +0,33 dB; Ana −0,33 dB; Marina +18,42 dB. Não houve corte, denoise, limiter, alteração de pitch ou tempo. Os MP3s de WhatsApp decodificam com as durações esperadas, sem clipping. Os quatro WAVs do pacote D aprovado continuam com os hashes anteriores.

O ganho maior de Marina não prova distorção: o pico final é −4,65 dBTP. Pode tornar fundo e respirações mais perceptíveis; essa candidata merece prioridade de escuta. Whisper large-v3-turbo corresponde à mensagem completa nas três. Small-q4 corresponde Rafael, mas diverge em “aproxima pessoas” nas duas femininas. A divergência pede audição e não foi tratada como prova de erro de fala ou justificativa de ressíntese automática.

Similaridades descritivas do speaker encoder Qwen não têm threshold calibrado e não certificam identidade, diferença perceptual de timbre, sotaque ou naturalidade. A avaliação direta deve comparar Rafael/D e Ana/Marina, desde a saudação até o fim. **As vozes novas ainda não têm aceite humano.** Não houve audição pelo agente.

Os limites anteriores continuam: watermark Perth nulo, sem alegar C7 satisfeito, integração CUDA de produção ou homologação integral do Qwen no worker. O TTS experimental local e a preparação dos três pares não alteram o worker de produção.

## Recarga, recuperação e execução real

Após o usuário informar a recarga, o console autenticado confirmou **US$ 20,27** no projeto. O acesso ocorreu pela extensão do **Google Chrome normal**. O usuário concluiu o MFA; nenhum pagamento foi submetido pelo agente.

A instância anterior foi excluída pelo provedor em 16/10/2026 às 03:50:08 UTC por `due_to_zero_balance`. O IP antigo apresentou outra chave SSH e não foi reutilizado. O pin original foi preservado.

Foram recuperados `OS-fHuXBon4` e `p06-avatar-d-fresh-20261015`, a **US$ 1,13 cada**. Como a capacidade de uma A100 e uma H200 deixou de estar disponível antes do deploy, foi clonado o último ambiente para FIN-02 antes de ligar a GPU. Não houve deploy das opções indisponíveis nem download de pesos durante o período de compute. O cache de modelos e o digest da imagem foram conferidos.

A VM temporária `p06-novos-avatares-20261016`, ID `f0a3627d-5df9-4f59-a146-bc8c14db1eb5`, foi criada às **20:28:52 UTC**: **2× A100 80 GB SXM4**, 44 vCPU, 240 GB de RAM declarados, **US$ 4,032/h**, cobrança em blocos de dez minutos. O plano de consumo foi persistido antes das ações pagas em `execution/cost-plan.json`. A recarga é crédito da conta, não o preço dos vídeos. Recuperações e storage são adicionais ao compute.

O perfil usa o mesmo digest `cad3a59ea8afb4197179a02ce6702a48bb9bf8f3f79acb586645291b53c632b4`, InfiniteTalk bf16, LightX2V de quatro passos, seed 42, text CFG 1/audio CFG 2. Fonte nativa 448×832, saída final 1080×1920/25 fps. O upscale não cria detalhe nativo em Full HD. O prompt mantém gesto moderado, mãos abaixo do rosto e câmera fixa. O zoom suave de até 6% é aplicado depois, preservando o áudio.

Uma falha no controlador (`Path.chown`) ocorreu antes da primeira inferência. Foi corrigida para `os.chown`, com recibo e falha original preservados. O primeiro render real foi Rafael. Seu uso de RAM foi acompanhado por 97 amostras a cada 15 segundos, até a remoção do container. O máximo reportado pelo cgroup (`memory.peak`) foi de **89.668.550.656 bytes**; não é uma estimativa do pico por interpolação das amostras. Após sua inspeção visual e revisão do Astra, Ana e Marina iniciaram em paralelo às **20:57:57 UTC**, uma por GPU.

O paralelo só foi liberado após guardas reais de RAM, smoke bf16/FlashAttention/xformers na segunda GPU, limites de memória por container e entradas/modelos somente leitura. O controlador pré-cria ambos os containers e coordena início, aborto e limpeza. O Astra revisou a implementação e as correções da corrida de aborto. Nenhum offset de outro personagem foi copiado para a finalização.

## Verificação por candidata

Rafael terminou a inferência às 20:56:08 UTC. A base e o nativo têm **248 quadros e 9,92 s**. O áudio AAC decodificado corresponde ao WAV próprio, com lag de 0 ms, sem mudança de duração e sem clipping. A comparação do PCM entre base, câmera fixa e zoom é idêntica.

O crop facial geométrico de Rafael foi revisto antes dos scores: x=286, y=190, 487×487. SyncNet mediu −80/−80/−120 ms na base, em três janelas. Os controles artificiais de ±200 ms responderam exatamente, nos cálculos oficial com padding e no interior válido. Atrasar somente o vídeo em **dois quadros** resultou em **0/0/−40 ms** tanto na câmera fixa quanto com zoom. Não foi recomendado outro ajuste automático.

| Rafael | SHA-256 |
|---|---|
| Nativo | `08d36387c0531e6f9874daa60ddb8107307fc3af624ca7d5b6fff14d1ec3aa0e` |
| Base | `9b6cc35c1a9adbb9607f7f96368cdb2286e0126f1a7a3490448a23e4e5491e4d` |
| Câmera fixa, +2 quadros visuais | `74998013fb5c2f8c2becb097829d0ce31adf62ad9140b595194adb465c0575f4` |
| Gestos e zoom, +2 quadros visuais | `a599a4d004ca34d9e78145e4c5da7f9d22f90f4eb14544a7d6f9183a2e7dc5b1` |

A coordenação, o QC e o Astra inspecionaram folhas reais do Rafael. Cabeça, cabelo, cotovelos e mãos permanecem no quadro com zoom. Não foi visto salto grosseiro de rosto, corpo ou fundo nas junções amostradas. Os dedos ficam suaves e sobrepostos quando as mãos se juntam; a inspeção de quadros não certifica anatomia fina, continuidade perceptiva ou naturalidade. Evidências: `qc/RAFAEL-FINAL-RESULTADO.md/.json`, `reviews/RAFAEL-GATE-VISUAL.md` e `preview/homem-02/`.

Ana e Marina também terminaram sem erro. Foram exatamente **três inferências de vídeo**, sem render repetido. Os nativos, as bases e 22 arquivos globais de evidência foram baixados e tiveram os hashes locais e remotos conferidos. `execution/batch-results-index.json` consolida os três pares; `execution/host-release.json` registra ausência de containers e de dependência remota.

| Par | Quadros / duração medidos | SHA-256 da base, sem offset ou zoom |
|---|---|---|
| Ana | 250 / 10,00 s | `45f35f4ba7dd7ec939eafeb246b02592512ca6764cff605a7a5d92e1486218d2` |
| Marina | 244 / 9,76 s | `6c58a1fb4634b177b6c31dbb0e61171d33229d34001d751534660cb6488c94df` |

A coordenação e o Astra viram as grades nativas das duas: mãos, cotovelos e cabeça permanecem no quadro; identidade, roupa, cabelo e cenário coerentes nas amostras. Há gestos reconhecíveis, com dedos suaves e sobrepostos nos contatos. Não foi demonstrada razão visual grosseira para repetir a inferência. Parecer: `reviews/ANA-MARINA-VISUAL.md`.

O QC confirmou 250 quadros/10 s em Ana e 244 quadros/9,76 s em Marina, sem alteração da contagem de amostras ou duração do áudio. Lag do áudio frente ao próprio WAV: 0 ms global e nos três blocos, sem fullscale.

Os crops geométricos foram revistos antes dos scores: Ana x=330/y=322/438×438; Marina x=311/y=204/471×471. Ana mediu −160/−160/−160 ms no interior válido e −120/−160/−160 ms no cálculo oficial com padding. A mediana de ambos foi −160 ms; a diferença inicial é de um quadro. A candidata aplica **+4 quadros somente no vídeo**, mantendo os 250 totais e o WAV em zero. Marina mediu −120/−120/−120 ms nos dois cálculos: candidata de **+3 quadros visuais**, 244 totais, WAV em zero. Os controles de ±200 ms responderam exatamente, com erro 0 ms nas duas candidatas e nos dois cálculos. Os crops não foram reajustados para melhorar os scores.

As quatro variantes femininas foram finalizadas e medidas novamente. Ana, câmera fixa e zoom: **0/0/0 ms no interior válido e +40/0/0 ms no cálculo oficial**. Marina, câmera fixa e zoom: **0/0/0 ms nos dois cálculos**. Todos os controles de ±200 ms responderam exatamente, com erro 0 ms. Os crops próprios foram mantidos, sem retuning. Não há indicação de outro ajuste automático.

| Par | Atraso visual próprio | SHA-256 da versão com gestos e zoom |
|---|---|---|
| Rafael | +2 quadros / 80 ms | `a599a4d004ca34d9e78145e4c5da7f9d22f90f4eb14544a7d6f9183a2e7dc5b1` |
| Ana | +4 quadros / 160 ms | `12b2bc330f44680b83511890823bdfd13d8df46599867ab1401e27871ab79163` |
| Marina | +3 quadros / 120 ms | `ed23ffbaa7436bfb61089ceeaa78bf0659aaeb24b77e1df170e7674afa98f94b` |

A finalização manteve duração e número de quadros por par. O PCM AAC decodificado é idêntico entre base, câmera fixa e zoom de cada voz. Os nativos, bases e WAVs próprios permaneceram intactos. Índice das seis variantes: `finishing/variants.index.json`.

A coordenação e o Astra inspecionaram as grades finais com zoom das duas mulheres. Cabeça, cabelo, mãos e cotovelos permanecem no quadro; não foi visto problema novo causado pelo zoom. O Astra também viu três folhas de junção de cada base: sem salto espacial grosseiro de corpo, mãos ou cenário nas amostras. Marina alterna gestos mais abertos; Ana mantém gestos mais contidos. O QC concluiu a inspeção densa das quatro variantes femininas, incluindo prefixo, cauda e pares imediatamente antes/depois das três junções. A coordenação também viu as folhas dirigidas das duas versões com zoom. Sem truncamento grosseiro nas amostras; Ana mantém sorriso/boca entreaberta na cauda e Marina termina com sorriso de boca fechada. Isso não comprova defeito de fala nem certifica o fechamento labial no final. Relatórios finais: `qc/ANA-FINAL-RESULTADO.md/.json` e `qc/MARINA-FINAL-RESULTADO.md/.json`. As vozes e os novos vídeos ainda não têm aceite humano.

## Encerramento e limites

A VM temporária foi **excluída após a conferência dos downloads**, antes de terminar o QC CPU local e sem esperar aceite humano. A lista de instâncias ficou vazia. O clone criado nesta tarefa foi colocado na lixeira recuperável; o produto declara 96 horas para restauração, com 95 horas restantes na consulta. Não houve exclusão permanente nem esvaziamento da lixeira.

Os dois discos anteriores, `OS-fHuXBon4` e `p06-avatar-d-fresh-20261015`, foram preservados, desanexados. **Compute encerrado; storage preservado continua custando US$ 0,13698/h no total**, pelos preços observados dos dois volumes de 250 GiB. O saldo observado após o encerramento foi **US$ 13,77**, frente aos US$ 20,27 iniciais. A variação de US$ 6,50 inclui recuperações, compute e storage e não representa uma fatura fechada só de inferência. Nenhuma nova recarga foi necessária para os três renders.

Evidências privadas: `verda/cleanup-result.json`, `verda/instances-empty.jpg` e `verda/volumes-preserved.jpg`. Os temporários de upload e coleta e os watchers desta tarefa foram removidos. O runtime temporário CPU de QC foi removido ao terminar as análises, com zero processos correspondentes antes/depois. Nenhum cache, modelo, voz ou render foi removido. O servidor HTTP usado só para verificar a página também foi encerrado e a porta foi conferida sem listener. Nenhum container ou watcher desta tarefa permaneceu ativo.

O Astra revisou o protocolo, os retratos, a execução paralela e folhas reais nativas, finais com zoom e junções dos três pares no modelo **gpt-6-astra**, esforço **medium**. Isso não substitui audição ou aceite do cliente. O QC usa runtime CPU offline, com duas threads, sem novas chamadas pagas. Os registros anteriores de saldo insuficiente e preparo sem MP4 ficam preservados nos recibos históricos do pacote privado.


O pacote técnico preserva scripts, planos anteriores às chamadas pagas, recibos, modelos de configuração, entradas, outputs, métricas e limitações. O ZIP destinado ao cliente exclui esses registros de operação. O manifesto geral é regenerado somente após encerrar os trabalhos dos agentes. A entrega adicional foi concluída tecnicamente; o aceite humano das novas vozes/vídeos e os demais critérios de homologação integral continuam abertos.
