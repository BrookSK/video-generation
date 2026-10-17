# P06 — correção da Ana após avaliação do vídeo

O usuário rejeitou o vídeo completo da Ana por ritmo ruim e som percebido como “dentro de um copo”. Marina ficou “ok”. A alteração se limita à Ana; o arquivo aceito de Marina será preservado por SHA. Não se infere aprovação do cliente.

Artefatos externos: `video-generation-amostras/p06-ana-v3-20261016/`. O feedback literal e os hashes avaliados estão em `FEEDBACK.json`. A voz A teve retorno positivo isolado antes, mas a apresentação audiovisual foi rejeitada agora. SyncNet com residual estimado zero não representa aprovação de prosódia, timbre ou naturalidade.

A investigação compara referência humana, áudio raw, ganho de escuta, MP3 e áudio do MP4. O Astra e o agente de voz foram retomados para revisar a causa antes de uma nova síntese. O plano prioriza comparações controladas e uma amostra de voz revisável antes de novo render pago.

O encerramento da instância Verda anterior permanece bloqueado por autenticação expirada. O login foi testado novamente nesta sessão, inclusive após reload, e ainda exibe Sign in. Foi solicitado ao usuário entrar no Chrome normal pela extensão. Não se declarou a instância excluída ou o custo encerrado. Nenhum novo render pago foi iniciado nesta revisão.

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
