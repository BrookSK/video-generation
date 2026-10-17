# P06 — revisão das duas candidatas femininas

Em 16/10/2026, o usuário rejeitou voz e vídeo de Ana e Marina. Pediu nova ajuda do Astra e pesquisa em resultados reais de especialistas, sem atribuir prematuramente a falha a sotaque, gênero, prompt ou modelo. Os arquivos anteriores foram preservados. As vozes A e C receberam retorno positivo e foram usadas nos dois novos vídeos completos. Ambos foram renderizados, finalizados e verificados tecnicamente; o aceite audiovisual continua pendente.

Pacote privado desta revisão: `video-generation-amostras/p06-femininas-v2-20261016/`. O feedback explícito está em `FEEDBACK.json`. O homem D aprovado permanece intacto; o relato anterior de aprovação de vídeo não identifica um SHA de variante.

## Retorno posterior sobre os vídeos completos

O usuário informou: “A primeira ainda está uma merda. Está uma verdadeira bosta. Ficou ruim, o tempo das falas ficou péssimo e parece que ela está falando dentro de um copo. A Marina ficou ok. Só precisa melhorar a Ana agora.” O vídeo Ana SHA `a34d4886d0380085570e337cb8aa4eab2e41b1ccc7b2df33838e96d916cf2720` está reprovado. O vídeo Marina SHA `679275d3574a022f7d3e2de18ba771dde0120214b09772314f76982135963a61` recebeu “ok” do usuário nesta avaliação, sem inferir aceite do cliente. A correção atual fica restrita à Ana. O retorno perceptivo supera o passe técnico descrito abaixo. A investigação está em [revisão da Ana](P06-ANA-REVISAO.md).

## Evidências e hipóteses

O sucesso masculino não comprova a qualidade das referências femininas. D usou Cadu/OHF e teve escuta e aceite. Seu texto sintético é o mesmo roteiro de apresentação das mulheres, trocando o nome. A fala sobre impostos pertence à referência humana e teve avaliação separada. O roteiro pode limitar a avaliação, mas não explica sozinho a diferença percebida. As mulheres usaram clipes FLEURS sem escuta prévia. O nível da referência Marina estava muito abaixo dos demais; isso justifica um controle de nível, sem explicar a rejeição de Ana. Os tempos de referência de cerca de 6–8 segundos não sustentam a conclusão de que duração curta seja a causa única.

O default do checkpoint Qwen é repetition penalty 1,05, mas o caminho ICL do runtime MLX 0.5.9 força no mínimo 1,5. Alterar apenas o request para 1,05 seria um ensaio falso. A nova candidata A instrumenta o sampler no runtime temporário e registra o valor efetivo; preserva pesos, referência, texto e seed. Não altera o worker de produção.

A receita InfiniteTalk de 4 passos com LightX2V T2V rank 32 é suportada pelos autores. O workflow mantido pelo Kijai utiliza outra combinação de LoRA, sampler e parâmetros; trocar somente a LoRA não reproduz esse workflow. A investigação prioriza comparações de um fator por vez antes de assumir que mais passos ou um modelo novo resolveriam.

A inspeção visual do retrato fonte de Marina e dos três recortes do rosto em `qc/marina-base-crop-proposta/faces-antes-score.jpg` mostra perda de detalhe visível no vídeo comparado à imagem fonte. A entrega ampliada não recupera esse detalhe. Isso apoia testar o tamanho do rosto no quadro, mas não prova que enquadramento sozinho resolva atuação ou sincronismo.

Uma medida descritiva dos vídeos nativos não encontrou pares adjacentes exatamente duplicados. Ana mostrou menos atividade no recorte de corpo/mãos que a variante masculina comparada; Marina apresentou atividade na faixa da cabeça semelhante. Isso enfraquece a explicação simples de vídeo congelado, sem medir naturalidade. As regiões fixas, enquadramentos, cabelos e poses diferem. Nenhuma nota perceptiva foi inferida dessas métricas.

## Retorno sobre as novas vozes

Na comparação individual de A, o usuário respondeu “ficou boa”. Sobre B/C, respondeu “ta top! mas a b parece um pouco reporter da globo”. Foram selecionadas A para Ana e C para Marina, sem ressíntese. O registro `vozes-selecionadas/SELECAO.json` preserva o texto exato e distingue o retorno individual de A da interpretação do retorno conjunto B/C. Não é aceite do cliente nem dos vídeos.

Os WAVs e MP3s escolhidos foram copiados byte a byte para `vozes-selecionadas/`, conferidos por SHA e protegidos contra escrita. A mantém WAV SHA `e94d0f69402cd2baab1826a89e1345eb615885b1e447c9e9ce04a4f7cb260df0`; C mantém `ef17ac23a952a9e9a627a6be04d1e70edff382bca0b60635f714a703e5328704`. A página e o manifesto de voz anteriores ao retorno também foram preservados.

## Auditoria da finalização anterior

Os logs e as receitas das duas mulheres não mostram BiRefNet, remoção de fundo ou reconstrução facial na finalização. O nativo `out/avatar_9x16.mp4` é ampliado 2,4375× com Lanczos, recortado para 1080×1920 e recodificado. A variante entregue é cópia exata da versão com zoom progressivo até 1,06; não há outro processamento no diretório de entrega. Também há atraso de vídeo de quatro quadros em Ana e três em Marina.

A comparação de dois instantes por mulher, alinhados ao mesmo quadro de origem e à mesma geometria, produziu diferença média RGB abaixo de 1/255. O root inspecionou os pares Ana no quadro 50 e Marina no quadro 150. As comparações sustentam que a finalização preserva o conteúdo amostrado e pode tornar mais visível a limitação de detalhe do nativo. Não demonstram fluidez ou sincronia ao longo do vídeo inteiro. Evidências em `finalization-audit/`.

## Ensaios desta rodada

| Ensaio | Mudança controlada | Estado |
|---|---|---|
| Voz A | Ana, sampler efetivo 1,05, restante igual | Selecionada para Ana; retorno individual “ficou boa” |
| Voz C | Marina, nível da referência corrigido, restante igual | Selecionada para Marina; retorno positivo conjunto B/C |
| Voz B | Nova referência humana brasileira rastreável | Comparação; usuário percebeu tom de repórter |
| Vídeo P1 | Controle curto da receita atual | Concluído, coletado e inspecionado |
| Vídeo P2 | Somente áudio CFG 2→1 | Concluído; boca menos exagerada nas amostras |
| Vídeo P3 | Somente enquadramento mais próximo | Concluído; rosto maior, anatomia preservada nas amostras |

Os três vídeos usam mesmo WAV original de 10 s, texto, seed 42, 4 passos e limite de 81 quadros. As prévias de 3,24 s não são entregas finais nem verificam gesto completo ou estabilidade longa. A imagem mais próxima deriva do mesmo retrato, sem criar outra identidade/cenário. O root inspecionou os dois enquadramentos; mãos, punhos, cotovelos e cabeça continuam visíveis.

O Astra revisou plano, argv e hashes. O controlador passou por 11 testes locais, incluindo deadline e confirmação de ausência dos containers após limpeza. O Astra revisou a correção. A execução usa deadline global real contado da criação da VM, limite de 900 s por job, pelo menos 23 min restantes antes de iniciar outro e 8 min reservados para coleta/encerramento. O plano persistido permite até US$ 2,516 nesta etapa diagnóstica, com A100 individual em FIN-02 a US$ 2,016/h. Saldo observado: US$ 14,36. O clone temporário foi recuperado por US$ 0,05; nenhum disco persistente anterior foi alterado. Foi criada a instância temporária `bb9573ed-d1a5-4ade-aca0-63faa1f1940b`. A aba Activity registra criação às 22:10:02 UTC e execução às 22:10:25 UTC. O controle mantém o piso conservador de `2026-10-16T22:10:00Z`. O deadline da etapa diagnóstica é `23:10Z`; qualquer extensão para os fulls precisa ser persistida antes do lançamento.

## Resultado das provas curtas

O retry concluiu as três provas. A coleta global conferiu os hashes dos 38 arquivos e confirmou a remoção de todos os containers da etapa. Os nativos e painéis estão em `video-research/results/`; a tentativa falha continua separada e preservada. O root inspecionou 16 quadros e recortes de rosto/mãos de cada prova. O Astra fez revisão independente dos nove painéis.

P2 apresenta aberturas menores da boca que P1 em vários quadros. O corpo segue um padrão parecido: as mãos se aproximam no começo e permanecem juntas perto do torso. P3 aumenta a presença do rosto, sem cortar cabeça, mãos ou cotovelos nos quadros vistos. O detalhe dos dedos continua suave. Nenhuma prova demonstrou maior variedade de gestos.

O áudio nativo de P1 e P2 tem PCM idêntico. O teste SyncNet pareado usou a mesma ROI nova e uma janela de 0,20–3,00 s, com 35 vetores interiores. Ambas estimaram offset interior de −80 ms; controles de ±200 ms foram recuperados com erro zero. As bordas com padding produziram estimativas diferentes, registradas no relatório. Isso enfraquece a hipótese de perda grosseira de alinhamento em P2 no trecho curto. Não comprova naturalidade, não descarta subarticulação e não define o offset dos vídeos com os WAVs A/C. Evidências em `av-qc/probes-p1-p2/`.

A seleção para o primeiro full é enquadramento próximo + áudio CFG 1. Trata-se de um teste integrado: os fatores foram isolados nas provas, mas a combinação ainda não foi validada. A Ana será renderizada primeiro e inspecionada antes de liberar a Marina. As vozes A/C serão usadas byte a byte, sem nova síntese. O registro `visual-review-root.json` e o parecer `reviews/PROVAS-VISUAIS.md` preservam os limites da revisão por quadros.

## Falha operacional e correção do controlador

A primeira prova P1 terminou em erro no primeiro forward, ainda em 0/4 passos, sem MP4 concluído. A chamada direta ao CLI omitiu `TORCHDYNAMO_DISABLE=1`, que o wrapper canônico `avatar_stage.py` já injeta para evitar compilação C ausente na imagem. O controlador parou a sequência e confirmou ausência dos containers. Os 23 arquivos de evidência foram baixados para `video-research/results/attempt-01-failed/`.

A correção acrescenta somente essa variável ao Docker, sem instalar dependências ou alterar pesos/parâmetros. O Astra conferiu o diff e os 11 testes locais passaram. Launcher corrigido: `1861fc05684375df0279314342c49dc58039fa0ab31dc6fefe2d75e7441edf8c`. O replanejamento foi persistido em `retry-plan.json` antes da autorização explícita da nova tentativa, às 22:23 UTC, com o mesmo teto e prazo absoluto da VM. Não há retry automático.

## Etapa dos vídeos completos

Às 22:56:29 UTC, o root ativou a etapa full após a revisão independente do contrato pelo Astra. Os 12 arquivos congelados conferem por SHA, incluindo imagens close e WAVs A/C. Contrato: `f3a5747062d8da25cf2da67b01804ce5c005845bedaeb70a1ec22b5c1b960555`. Controlador full: `654f5e0f90c89761068db383a2e7a14b8550da8c249dd4557ce72b3938c35e74`. Os 13 testes do controlador passaram. O arquivo `full-authorization.json` vincula a execução ao contrato, à VM e ao horário original de criação.

O plano `full-stage-cost-plan.json` reserva mais US$ 2,25, com teto combinado de US$ 4,766. Mantém a mesma VM e cache, sem novos modelos. O limite total é de 120 minutos desde 22:10 UTC, com exclusão até 00:10 UTC de 17/10. Cada job tem timeout de 1.800 s, reserva de 480 s para coleta/encerramento e exige pelo menos 2.280 s restantes para iniciar. Saldo observado antes do lançamento: US$ 12,10; o saldo não é tratado como fatura exata.

A execução é sequencial: Ana primeiro; Marina exige uma decisão do root vinculada ao SHA do nativo Ana concluído. O controlador aguarda no máximo 180 s por essa decisão e confirma ausência dos containers entre jobs. Não há retry automático. A finalização e o QA AV são locais, com áudio sempre do WAV selecionado; o offset será medido de novo. O aceite dos vídeos continua pendente.

Ana concluiu às 23:19:20 UTC, com 272 quadros e 10,88 s. Nativo SHA `5f84d39a4e9a29b7cd39fd0e2737d3e9681209cfd66290ca5e92c102df913b04`. A coleta inicial conferiu 13 arquivos. O root e o Astra inspecionaram os 16 quadros distribuídos pelo full, recortes de rosto/mãos e 12 quadros em tamanho nativo nas três junções. Identidade, roupa e fundo permanecem reconhecíveis; mãos e cotovelos ficam no quadro. As mãos reabrem na segunda parte e retornam. Persistem dedos suaves/sobrepostos nos contatos. Não houve escuta direta ou reprodução contínua pelo agente.

O gate técnico foi aprovado com vínculo ao SHA real de Ana e enviado atomicamente aos 80 s da janela de 180 s. Marina iniciou às 23:20:40 UTC. Esse gate autoriza a sequência de teste por ausência de bloqueio visual grosseiro; não é aceite de sincronia, naturalidade ou cliente. Evidências: `ana-gate-review-root.json`, `full-renders/gate-upload.result.json` e `reviews/ANA-FULL-VISUAL.md`.

## QA audiovisual e finalização dos novos fulls

Ana foi finalizada a partir do nativo e do WAV A selecionado, com base sem correção, versão fixa e zoom leve de 1→1,06. As três versões mantêm 272 quadros, 10,88 s, 1080×1920 e 25 fps. O PCM AAC é idêntico entre as variantes e à codificação independente do WAV selecionado. A comparação da base com o WAV deu lag zero em todas as janelas contíguas de 1 s, correlação global 0,9999956 e nenhum clipping.

A ROI de cada base/fixo/zoom foi revista por quadros novos antes dos scores. A medição da base retornou −120 ms nas três janelas sobrepostas de 4 s, em ambos os cálculos. Os controles reais de áudio −200/0/+200 ms produziram offsets +80/−120/−320 ms em cada janela e método, com erro zero. O root conferiu a matriz e os hashes; o Astra confirmou o sinal. Foi escolhido atraso visual de três quadros, preservando o WAV. Não se transferiu o valor antigo de quatro quadros.

As versões fixa e com zoom foram medidas novamente: residual estimado 0/0/0 ms nos dois cálculos, com controles ±200 ms recuperados exatamente. O começo mantém os três quadros repetidos planejados; a cauda termina no quadro fonte 268, preservando todo o áudio. O root revisou início/fim e três junções do zoom; cabeça, cotovelos, mãos e punhos permanecem no quadro. Os dedos continuam suaves nos contatos. Os registros ficam em `ana-offset-selection-root.json`, `ana-final-visual-root.json`, `av-qc/` e `finishing/ana/RESULTADO.json`.

Ana com zoom: SHA `a34d4886d0380085570e337cb8aa4eab2e41b1ccc7b2df33838e96d916cf2720`. A cópia em `entrega/video-ana.mp4` é byte a byte idêntica. Foi apresentada ao usuário para avaliação do conjunto audiovisual enquanto Marina estava em geração. O aceite perceptivo continua pendente. As janelas se sobrepõem e os dois cálculos usam o mesmo SyncNet; não são avaliações perceptivas independentes. Não houve escuta direta ou reprodução contínua pelo agente.

Marina e o batch full concluíram às 23:40:54 UTC. O nativo tem 244 quadros, 9,76 s e SHA `6f5057763fb2f15bac9e171496a9138af03ac73e68b075cde17cf3d3e666e605`. Root e Astra inspecionaram os quatro painéis reais, com rosto, mãos e junções: identidade, cabelo, roupa e fundo coerentes nas amostras; gestos abrem, juntam e reabrem as mãos. Persistem detalhes suaves de dedos e boca. O parecer está em `reviews/MARINA-FULL-VISUAL.md`.

A base de Marina preserva o WAV C; a comparação de áudio deu lag zero em todos os segundos, correlação global 0,99999265, amostras completas e nenhum clipping. A ROI própria foi vista antes dos scores. A nova medição retornou −120 ms em todas as três janelas e ambos os cálculos, com controles −200/0/+200→+80/−120/−320 ms e os 18 erros de recuperação iguais a zero. O root escolheu atraso visual de três quadros a partir desses dados, sem herdar o valor de Ana (`marina-offset-selection-root.json`). As variantes finais fixa e com zoom foram medidas novamente: residual estimado 0/0/0 ms nas três janelas e nos dois cálculos. Os controles ±200 ms foram recuperados exatamente. Ambas preservam 244 quadros, 9,76 s, 1080×1920 e 25 fps, com o PCM idêntico à base e à codificação independente do WAV C. O root inspecionou as ROIs separadas, início/fim e as três junções do zoom. Cabeça, cabelo, mãos, punhos e cotovelos permanecem no quadro; os dedos continuam suaves nos contatos. Evidências: `marina-final-visual-root.json` e `av-qc/MARINA-FINAL-QA.json`.

Marina com zoom: SHA `679275d3574a022f7d3e2de18ba771dde0120214b09772314f76982135963a61`. A cópia `entrega/video-marina.mp4` é byte a byte idêntica. Os dois MP3s entregues são cópias exatas das vozes selecionadas. O pacote `ana-marina-para-avaliacao.zip` tem seis arquivos, 9.945.607 bytes e SHA `3fa41a80ef738daf79e3fec9f7be27a46eaead66e512a99419aea5e0215eeae2`; todas as entradas foram conferidas após a compactação. A página raiz `revisao.html` oferece os dois MP4s, os MP3s, câmera fixa e histórico separado. As 15 referências locais existem. O Chrome normal pela extensão carregou as quatro mídias principais sem erro, com dimensões e durações esperadas. Evidências: `entrega-manifesto.json` e `revisao-final.jpg`.

Os manifestos próprios de Ana e Marina têm 352 arquivos cada e vinculam fontes, decisões, ROI, medições e revisão estática. O runtime temporário local foi removido e sua ausência confirmada; oito arquivos de fonte, modelo e cache foram preservados por SHA (`av-qc/setup/runtime-fulls-cleanup.json`). A ausência de atraso estimado não certifica a qualidade perceptiva. Não houve escuta direta ou reprodução contínua pelo agente.

A coleta global conferiu 41 arquivos e 27.049.757 bytes descompactados. O pacote transferido de 25.265.997 bytes tem SHA `e7f7737dfe07f5459e647971e626667996f0310e678b2a87a7dd13af16281f85`. Não resta dependência remota dos renders. A prova SSH de 23:41:55 UTC confirmou os cinco containers ausentes e nenhum processo de computação na GPU. Os comandos SSH/SCP locais terminaram; chave e pin foram preservados. Recibos em `full-renders/collection-all.json`, `host-cleanup-proof.json` e `host-release.json`.

## Encerramento cloud ainda pendente

O console Verda expirou a sessão durante o render e passou a exibir Sign in. O mecanismo anterior era Chrome normal pela extensão, com MFA concluído pelo usuário; os arquivos temporários de login já haviam sido removidos. Não foi localizada credencial vigente de API/CLI nos locais de acesso do projeto examinados. O usuário foi solicitado a entrar novamente, enquanto os testes locais continuam. Evidência em `verda/auth-block.json` e `login-expirado.jpg`.

Os processos de render estão encerrados, mas a exclusão da instância não foi feita nem confirmada. Shutdown não é considerado interrupção de cobrança: a [documentação oficial](https://docs.verda.com/cpu-and-gpu-instances/shutdown-hibernate-and-delete/) exige excluir a instância para liberar compute. O deadline planejado continua 00:10 UTC de 17/10, equivalente a 21:10 de 16/10 em São Paulo. Não há extensão, render novo ou retry autorizado. O clone temporário também aguarda retorno à lixeira recuperável. Os dois discos persistentes anteriores não foram alterados por esta revisão.

## Gestos e alternativa V2V

A revisão do Astra confirmou que o contrato V2V do InfiniteTalk condiciona a identidade ao próprio vídeo. Não há entrada separada de foto da Ana mais movimento de outra atriz. Um vídeo motor de outra pessoa não preserva automaticamente o avatar escolhido. Além disso, uma janela de 81 quadros usa apenas o primeiro quadro do driver; um ensaio real de transferência de movimento precisa de pelo menos dois blocos, cerca de 6,12 s, e movimento visível no quadro 72.

O Astra também baixou e inspecionou um resultado real da seção V2V dos autores: [videos/1.mp4](https://meigen-ai.github.io/InfiniteTalk/videos/1.mp4), 27,16 s, 1280×704, 25 fps, SHA `e856acce20c9ebe6e9a81a2483086d14aef24c0431b06ab3a385e401d7920d72`. O root viu a grade de 14 quadros entre 0 e 26 s. Há variação distribuída de gestos, posição do telefone, cabeça e olhar, com rosto, roupa e cenário reconhecíveis. Alguns quadros mostram borrão forte nas mãos/telefone. A demonstração não fornece parâmetros completos associados ao MP4. Sustenta que uma entrada de vídeo pode preservar atuação variada; não prova qualidade do nosso perfil I2V de 4 passos ou português brasileiro. Evidência em `reviews/official-demo/`.

Uma alternativa posterior exige um vídeo autorizado de 6–10 s já mostrando a pessoa final, com boca, mãos e cotovelos visíveis. O controle continua esparso e não garante trajetória exata de dedos/câmera. Não foi usado vídeo motor nem gerada nova identidade nesta revisão. O parecer `INFINITETALK-V2V.md` preserva fontes e limites.

Uma segunda revisão comparou três alternativas. [EchoMimicV2](https://github.com/antgroup/echomimic_v2) recebe retrato, áudio e poses por quadro; é um contraste direto para direção de mãos, mas faltam runtime local, pose compatível e fechamento das licenças de todos os checkpoints. [StableAvatar](https://github.com/Francis-Rings/StableAvatar) publica receita de foto/áudio/prompt, sem driver explícito de mãos no script examinado. [Wan2.2-S2V](https://github.com/Wan-Video/Wan2.2) aceita pose, mas exige outro pipeline e usa 40 passos por padrão. Nenhuma foi instalada ou testada. O parecer `reviews/ALTERNATIVAS-GESTOS.md` distingue demos, receitas, medições dos autores e lacunas. O próximo contraste, caso a rigidez persista no full, é introduzir movimento explícito; uma troca de gerador sem esse controle não isola essa hipótese.

## Limite desta homologação e fechamento da P06

Esta revisão corrige e entrega candidatas externas para avaliação do cliente. Não promove automaticamente uma receita global nem cadastra vozes por identidade na aplicação. O procedimento exige, para encerrar a P06 inteira, congelar/carregar a receita aceita, cadastrar os assets finais e demonstrar geração pelo fluxo da aplicação (`PROCEDIMENTO.md`, seções de pacote inicial e execução).

No código atual, o cadastro escolhe `masculina` ou `feminina`; não oferece identidade A/C por avatar (`apps/api/src/avatar_api/models.py` e `panel.py`). A receita global `docs/models/RECIPE-v1.json` continua draft com Chatterbox. A seleção perceptiva dos pares e a integração são estados distintos. Os contratos privados congelam as entradas desta rodada para reprodução, sem alterar o default dos pares anteriores aprovados. O fechamento da P06 permanece pendente desse fluxo integrado, além do aceite dos novos vídeos.

## Fontes primárias e limites

- [Qwen3-TTS: modelos, clonagem e parâmetros](https://github.com/QwenLM/Qwen3-TTS). Base e VoiceDesign possuem interfaces diferentes; VoiceDesign e Kokoro já foram ensaiados e rejeitados no projeto.
- [MLX-Audio, correção de ritmo PR 914](https://github.com/Blaizzy/mlx-audio/pull/914): a janela de 64 tokens já está presente no runtime usado; não é uma correção nova a aplicar sem teste.
- [InfiniteTalk dos autores](https://github.com/MeiGen-AI/InfiniteTalk) e [demonstrações](https://meigen-ai.github.io/InfiniteTalk/). Suporte a uma receita não comprova preferência pelo resultado gerado.
- [Workflow InfiniteTalk I2V do Kijai](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/088128b224242e110d3906c6750e9a3a348a659b/example_workflows/wanvideo_2_1_14B_I2V_InfiniteTalk_example_03.json): LoRA I2V rank 64, amostrador, resolução e precisão diferem da receita atual.
- [CML-TTS, CEIA-UFG](https://github.com/freds0/CML-TTS-Dataset): corpus e amostras de TTS com locutores rastreáveis, CC-BY 4.0. O conjunto mistura variantes de português; é preciso verificar a referência escolhida.
- [Corpus feminino profissional UFRJ/Globo](https://biblioteca.sbrt.org.br/articlefile/4464.pdf): útil como evidência de curadoria acústica. Os termos do companion restringem uso comercial e transformação; esse corpus não foi usado para clonagem.

A pesquisa e os pareceres desta rodada estão em `p06-femininas-v2-20261016/reviews/`; os pareceres iniciais foram preservados em `p06-novos-avatares-20261016/reviews/reavaliacao-femininas-20261016/`. A página `voz/revisao.html` contém as candidatas A/B/C, os controles femininos rejeitados, o D sintético aprovado e as referências humanas claramente rotuladas. O manifesto `voz/RESULTADO.json` distingue seus textos e hashes. Não houve escuta direta ou reprodução contínua pelo agente. As novas provas de vídeo precisam de comparação perceptiva; ASR, nível, EOS e SyncNet continuam sendo diagnósticos auxiliares.
