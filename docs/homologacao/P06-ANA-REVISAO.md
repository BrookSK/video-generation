# P06 — correção da Ana após avaliação do vídeo

O usuário rejeitou o vídeo completo da Ana por ritmo ruim e som percebido como “dentro de um copo”. Marina ficou “ok”. A alteração se limita à Ana; o arquivo aceito de Marina será preservado por SHA. Não se infere aprovação do cliente.

Artefatos externos: `video-generation-amostras/p06-ana-v3-20261016/`. O feedback literal e os hashes avaliados estão em `FEEDBACK.json`. A voz A teve retorno positivo isolado antes, mas a apresentação audiovisual foi rejeitada agora. SyncNet com residual estimado zero não representa aprovação de prosódia, timbre ou naturalidade.

A investigação compara referência humana, áudio raw, ganho de escuta, MP3 e áudio do MP4. O Astra e o agente de voz foram retomados para revisar a causa antes de uma nova síntese. O plano prioriza comparações controladas e uma amostra de voz revisável antes de novo render pago.

O encerramento da instância Verda anterior permanece bloqueado por autenticação expirada. O login foi testado novamente nesta sessão, inclusive após reload, e ainda exibe Sign in. Foi solicitado ao usuário entrar no Chrome normal pela extensão. Não se declarou a instância excluída ou o custo encerrado. Nenhum novo render pago foi iniciado nesta revisão.

## Retorno posterior: corrigir somente a abertura

O usuário informou que “Olá, eu sou a Ana” continua ruim, mas o restante da N1 ficou muito bom. Esse retorno é parcial: não aceita a N1 inteira e preserva a avaliação positiva do corpo. A correção seguinte fica restrita à abertura, em `video-generation-amostras/p06-ana-abertura-20261016/`. Marina continua intacta. O plano é gerar duas apresentações isoladas com o mesmo texto e referência N1 e concatenar cada uma ao corpo original, sem alterar suas amostras.

## Evidência de origem e controles

A auditoria `audio/CADEIA-AUDIT.json` confirma a pausa em baixa energia no raw A: aproximadamente 4,190–5,948 s, interrompida por somente 1,96 ms acima de −45 dB. O ganho de escuta é constante (+0,880001 dB), sem mudança de duração ou lag. A variação por bandas entre WAV e áudio do MP4 é de cerca de +0,0009 a −0,0213 dB entre 80 e 10.000 Hz. A finalização não explica a pausa e tem pouco suporte como origem da forte coloração relatada; esses números não diagnosticam timbre por si só.

O controle anterior com penalidade 1.5 e o mesmo input/seed já existe. Ele não é reapresentado como solução, pois também foi rejeitado. A comparação com A1.05 examina o sampler sem nova inferência. Um controle adicional altera apenas o intervalo central quieto, sem EQ ou aceleração global, para separar ritmo de timbre. A próxima síntese deverá testar outra referência com parâmetros fixos, depois de registrar a origem e a triagem.

O Astra consultou o [guia oficial de clonagem MLX-Audio](https://github.com/Blaizzy/mlx-audio/blob/main/docs/guides/voice-cloning.md), que recomenda fala limpa e conversacional, e o [README Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), que descreve preservação de características acústicas ambientais. Isso sustenta investigar a referência; não prova reverberação ou prescreve EQ para a Ana. Os pareceres e seus limites estão em `reviews/ASTRA-DIAGNOSTICO-ANA.md` e `reviews/ASTRA-CURADORIA-REFERENCIA.md`.

## Nova amostra N1

A triagem oficial FLEURS não forneceu outra referência feminina acessível dentro do limite: validation e test eram MALE, train falhou no servidor de preview e o asset individual retornou 403. Nenhum novo áudio FLEURS nem corpus integral foi baixado. Os candidatos CML Mayah/Sandra permaneceram com dialeto não confirmado.

Foi obtido outro trecho da mesma Adriana usada em B, speaker MLS12249, clipe 12249_10229_000455.flac, capítulo IV de Canaã. O streaming oficial foi interrompido após 2.590.720 bytes, dentro do teto de 3 MB. A referência recebeu +0,01 dB constante para coincidir com o nível da referência B; modelo, texto-alvo, seed, temperatura e penalidade 1.5 ficaram fixos. O pacote de referência e sua transcrição são a mudança controlada. Não foi alegada escuta, ambiente seco ou ausência do tom de repórter.

A única síntese N1 autorizada executou localmente, offline, em 30,63 s. Terminou por EOS com sampler efetivo 1.5 e contexto 64. O WAV de escuta preserva 255.361 amostras a 24 kHz, duração 10,6400417 s, sem clipping. Aplicou-se somente ganho constante +9,54 dB, medindo −23,47 LUFS. A maior pausa interna por energia foi 0,422 s a −45 dB e 0,444 s a −35 dB. Isso elimina aquela lacuna específica da A nesta amostra, mas não certifica prosódia, timbre ou estilo. Whisper local transcreveu o roteiro completo, com grafias “anna”/“idéia”; esse diagnóstico não aprova naturalidade.

- WAV N1 SHA `b22d5b1e575d4d9fabb5e9567a1b5e877ed230900dda09974052b06d4d651b63`.
- MP3 N1 SHA `83aa17bac23a9f3466f3f29bce6b38e789647ef4f50508a491d2b3b24f1b178a`.

O controle de pausa preserva a voz A e remove 1,41 s do intervalo quieto; dura 9,47 s. É diagnóstico, sem EQ, pitch ou atempo, e não foi encaixado no vídeo antigo. A página `revisao.html` reúne N1, A, controle de pausa, B e referência humana claramente separados. Os 12 links locais e as cinco mídias foram verificados no Chrome normal pela extensão, sem erro e com durações esperadas. Foi solicitado retorno perceptivo sobre o MP3 N1 exato. N2 não foi executada; nenhum render novo foi iniciado.

## Preparação do próximo vídeo e estado pendente

O pacote `render/` prepara apenas o job Ana, com a receita visual anterior intacta. O teste local do root passou 23/23 casos CPU, com subprocessos simulados e WAVs sintéticos. Não houve SSH, provisionamento, inferência remota ou conferência dos 93 GB de modelos. O WAV N1 real não foi copiado para um driver e não existe contrato executável. Os templates seguem com autorização falsa e aceite pendente.

A duração da N1 contém uma amostra além de 266 quadros exatos. O plano usa ceil inteiro para 267 quadros e prevê 959 amostras de silêncio no fim de um driver separado (39,958 ms), preservando byte a byte o WAV escolhido. Nenhum trecho da fala seria removido. O padding ainda não foi materializado. A futura finalização deve preservar a fala e medir novamente sua sincronia, sem herdar os três quadros de atraso anteriores.

O runner recusa a instância antiga, exige aceite explícito do novo áudio/hash e autorização do root vinculada a uma VM futura, contrato e driver. Os limites preparados são 45 min desde a criação da VM, 1800 s por job e 480 s para coleta/encerramento, sem retry. O runner encerra os containers da tarefa; não exclui a VM nem encerra a cobrança cloud. Essa exclusão continua uma ação distinta e precisa de acesso autenticado.

A página e o MP3 N1 foram apresentados ao usuário. A avaliação de naturalidade e o login continuam pendentes. A tentativa adicional de login não ofereceu preenchimento salvo; o histórico consultado não localizou outro mecanismo atual de autenticação. Os dados temporários do login anterior haviam sido removidos. Foi solicitado preenchimento direto no Chrome. O prazo anterior 00:10 UTC já foi ultrapassado; a exclusão da VM antiga permanece sem execução/confirmação.

O manifesto de áudio tem 50 arquivos conferidos por SHA pelo root. Os ambientes temporários de TTS/ASR foram removidos e 17 arquivos de modelos/fontes/cache preservados. A fonte A e os arquivos da Marina permanecem intactos. Esta revisão ainda não declara a Ana corrigida nem encerra a P06.

O root verificou também os 12 arquivos do manifesto de preparo do render. O servidor local temporário foi encerrado e a ausência do listener confirmada; a revisão permanece disponível como HTML local com referências relativas. Não restaram caches de bytecode ou runtimes temporários desta rodada. O estado atual é amostra vocal pronta para avaliação, vídeo novo não iniciado e encerramento cloud bloqueado por login.

## Montagem das aberturas I1 e I2

O Astra recomendou dois takes isolados da frase exata “Olá, eu sou a Ana.” com a mesma referência N1, em vez de adicionar warmup ou montar um terceiro híbrido com B. I1 usa seed 20261015; I2 usa 20261016; os demais parâmetros ficam iguais. Isso gera opções de apresentação, sem alegar causa comprovada de cold-start. As duas sínteses locais foram autorizadas previamente, offline, com limite de 180 s cada e sem retry.

O corte foi escolhido na passagem por zero próxima ao meio da pausa real de 2,171–2,593 s, revista na onda e no espectrograma. A partir da amostra 57.256 do WAV N1, foram congeladas 198.105 amostras (PCM SHA `05043a594315e04a2a3f58d99cff0f7601131c3b82304fdc8b59cd1b313db2aa`). Isso preserva também cerca de 208 ms da pausa anterior à entrada de “Uma”. O root conferiu o sufixo dos dois WAVs completos: igualdade exata, zero amostras do corpo modificadas. O N1 de origem continua intacto.

O ganho foi aplicado apenas nas novas aberturas (+6,53 dB em I1 e +5,78 dB em I2). Houve fade somente nos últimos 10 ms quietos da intro e preenchimento para cauda quieta de 150 ms. O corpo não recebe ganho, fade, crossfade ou alteração de tempo. Os MP3s são novos encodes; a igualdade de amostras se refere ao PCM/WAV.

| Versão | Duração completa | SHA do WAV | SHA do MP3 |
|---|---|---|---|
| I1 | 10,271583 s |`5e746f7eee1832a3105e0e85928235d85a95dae20ab74e791b5522857fff3f06`|`cc43336ab4dbc9e456de29eda29239e7f9ec41fdec7c758d608ba615aea46ecb`|
| I2 | 9,858042 s |`a2a95ca82f0139f2c5146ab3454aae48155c1012e3e055b62ee9dd2e50913e0f`|`ec8cf845914359f2a06d8520185bb0f03cff05215f67a04ba89f34a68b535007`|

As duas terminaram por EOS, com sampler 1.5/contexto 64 e sem clipping. Whisper local reconheceu a frase exata nas duas, sem texto esperado no prompt. Os tempos de palavras são aproximados e não julgam entonação. A página nova oferece os dois completos, N1 anterior e referência humana. Os 10 links locais e as quatro mídias foram verificados no Chrome normal, sem erro e com durações esperadas. A escolha perceptiva foi solicitada ao usuário. Não houve escuta direta pelo agente.

Ainda não há áudio completo aceito para o próximo vídeo. O plano de render v3 continua apenas como preparo histórico; não deve ser executado com N1 inteiro nem receber um aceite fictício. Depois da escolha, deverá vincular o WAV composto e seu hash reais. A instância antiga continua sem exclusão confirmada por falta do login, e nenhum novo render pago foi iniciado nesta etapa.

O root verificou os 50 arquivos do manifesto desta rodada por tamanho e SHA, sem divergências (`ROOT-MANIFESTO-CHECK.json`). O runtime temporário foi removido e os caches de origem preservados. A aba e o servidor de revisão temporários foram encerrados; a porta 61365 ficou sem listener. O HTML local e seus áudios continuam disponíveis. A última conferência da Verda ainda mostrou “Sign in”; a aba de login foi mantida para o usuário.

## Escolha do usuário: abertura 2

O retorno literal foi “ABERTURA 2 FICOU MELHOR”. I2 fica selecionada como entrada para o próximo teste de vídeo, com o mesmo corpo N1 preservado. O feedback compara as aberturas; não declara aprovação final da entrega nem do cliente. O registro `p06-ana-abertura-20261016/SELECAO-USUARIO.json` vincula o MP3 apresentado e o WAV composto aos hashes I2 da tabela acima. N1 original não recebe aceite.

A conferência seguinte da Verda no Chrome normal ainda mostrou “Sign in”. A instância antiga permanece sem exclusão confirmada. Nenhum novo render pago foi iniciado.

O novo pacote local `p06-ana-abertura-20261016/render/` está vinculado à seleção I2 real. O WAV selecionado foi copiado sem alteração. O driver separado preserva as 236.593 amostras PCM e acrescenta somente 527 zeros finais, totalizando 237.120 amostras e 247 quadros a 25 fps. O contrato tem SHA `6d599a096074ef4d1a061bdfaa1bfcdc4b358ba165317fb4f66b4ea859775bba`; o driver, `b60b42049047574a659f7614c8d06c15d89e1eb70f16efd3dde012d1cd1a17d3`.

O agente passou 24 testes locais. O root confirmou `verify-inputs-only` para os 10 arquivos do contrato, verificou os 20 arquivos do manifesto e comparou o PCM original com o driver, incluindo os zeros finais. O registro de seleção foi copiado byte a byte, sem elevar a preferência a aprovação final. Não restaram temporários ou bytecode. A autorização cloud continua falsa e sem VM; não houve SSH, GPU, inferência ou operação de rede nesta preparação. A próxima etapa é o render real após recuperar o acesso e encerrar a instância antiga.

## Recuperação do login da Verda em 17/10

Após a orientação do usuário para recuperar o acesso na AI Memory, o root consultou as páginas e as observações originais do projeto. O histórico apontou o transcript anterior; os campos de login foram recuperados de dados literais dessa fonte, sem executar código histórico. O preenchimento foi feito somente em `https://console.verda.com`, pelo Chrome normal com extensão. Nenhum valor de credencial foi publicado. O arquivo intermediário privado foi removido após a leitura.

A senha foi aceita e a Verda exigiu um código de seis dígitos enviado ao e-mail da conta. O código foi solicitado ao usuário e a aba ficou aberta nessa etapa. A autenticação ainda não está concluída; a exclusão da GPU antiga e o novo render continuam pendentes. A evidência local fica em `p06-ana-abertura-20261016/verda/RECUPERACAO-ACESSO.json` e `codigo-pendente-20261017.png`.

## Acesso restabelecido e saldo observado em 17/10

O usuário pediu uma nova entrada para solicitar o código ao cliente. A tentativa de reenvio na tela antiga voltou a Sign in. O root preencheu novamente o acesso já recuperado, diretamente no Chrome normal; o painel autenticado abriu sem submissão de código pelo agente. Não é mais necessário pedir código para essa entrada já concluída. A aba autenticada foi mantida aberta.

O saldo observado é US$ 0,60. A lista de instâncias está vazia. O detalhe da instância `bb9573ed-d1a5-4ade-aca0-63faa1f1940b` mostra `Discontinued` e o evento `Instance deleted`, exibido em 17/10 às 01:20:24 no horário do painel. A exclusão já havia ocorrido; não foi executada nesta ação. Isso substitui o estado anterior de exclusão não confirmada.

A lista de volumes ativos também está vazia. Na área recuperável, os originais `OS-fHuXBon4` (`d0c605d0-7589-42f1-95ca-048a8a7e8fb7`) e `p06-avatar-d-fresh-20261015` (`b1bc8e09-8ab6-419e-902d-b4a7aa23a625`) aparecem `Deleted`, com cerca de 86 horas restantes e custo de restauração exibido de US$ 0,67 cada. O clone temporário FIN-02 também já aparece `Deleted`. Não se atribuiu causa ou autoria às exclusões. Nenhum volume foi restaurado, excluído ou purgado pelo root nesta ação. É necessária recarga para restaurar os volumes e executar o próximo render; não foi iniciada operação paga com saldo insuficiente.

O retorno posterior “fico top” confirma a aprovação da voz I2 pelo usuário, sem representar aprovação do novo vídeo ou do cliente. Os arquivos de áudio e o contrato local permanecem intactos. O estado conferido e as capturas estão em `p06-ana-abertura-20261016/verda/ACESSO-RESTABELECIDO.json`.

## Retomada em 18/10: crédito informado ainda não aparece

O usuário informou “cliente recarregou”. O root entrou novamente no Chrome normal, conferiu Billing history e atualizou a página. O projeto único visível, `Cloud Project` (`5e20534f-f96c-42fb-8a52-deb4f7e28efc`), ainda mostra US$ 0,60. O histórico lista US$ 20 em cada data 13, 15 e 16/10, totalizando US$ 60; nenhuma nova entrada aparece na conferência. O usuário não soube confirmar valor/horário do crédito informado. Foi solicitada somente a confirmação do pagamento já feito, sem solicitar outro pagamento ou tentar debitar cartão salvo.

O cache necessário ao próximo render foi identificado no volume FIN-02 `0338dfad-930b-479f-af0b-81b09ff54c0d`, a partir dos recibos de preflight v2. Esse volume ainda aparece recuperável, com cerca de 58 horas restantes e restauração exibida a US$ 2,56. Os originais FIN-01 e FIN-03 também aparecem recuperáveis pelo mesmo prazo. Não houve restauração, criação de VM, alteração de armazenamento ou inferência paga.

O pacote I2 continua imutável. O agente de render deixou a sequência operacional em `p06-ana-video-I2-20261018/operacao/RUNBOOK.md`, incluindo coleta integral antes de excluir a VM e finalização com o áudio I2 exato. Os quatro blocos Bash passaram na checagem de sintaxe; os testes anteriores não foram repetidos. O root conferiu o SHA do runbook (`99ec113296cb5932c937c9e010a1ec7e4d8fad9e9a136b98b7a66be03580caf3`). O estado atual e a captura após atualização ficam em `p06-ana-video-I2-20261018/RESULTADO.json` e `verda/recarga-conferencia-atualizada-20261018.png`. O render real aguarda o crédito aparecer no projeto.
