# P06 — primeira amostra masculina aprovada

Aceite explícito do usuário em 15/10/2026: **Voz D = controle N**, Qwen3-TTS Base 1.7B bf16 com referência humana Cadu/OHF. O usuário considerou a fala brasileira, com boa entonação e naturalidade, dizendo que numa conversa não perceberia que é IA. A gravação humana dos impostos também foi considerada excelente e aceita como alvo.

Na mesma data, o usuário informou que enviou a demonstração ao cliente, que gostou e considerou o áudio adequado. O arquivo disponibilizado para compartilhamento foi `voz-D-aprovada.mp3`, derivado do WAV D, com 9,84 s e SHA-256 `845e7d2819fc5818e15ba6e3451564b0881b6a2adf41cc54190dcbc9d1bb0973`. O retorno foi registrado por relato do usuário; cobre essa demonstração de áudio. O WAV de origem permanece preservado para o avatar. Registro privado: `ACEITE-CLIENTE.json` no pacote aprovado.

## Arquivo aprovado

O arquivo ouvido é o derivado de escuta com ganho constante de +3,7 dB, e não o WAV bruto. Perfil PCM16 mono/24 kHz, 236.160 amostras, 9,84 s.

| Papel | Arquivo no pacote privado | SHA-256 |
|---|---|---|
| Áudio ouvido e aprovado | `speech.wav` | `8af5824b914f83ede697de2235bda56aea5e69d2582ef83bef1eaea1e862e422` |
| Saída bruta da síntese | `speech-raw.wav` | `bc7d8c5ab058770c0fb5bb5423a84e2325b35c0ba6d4746188bc5260c24b4ec8` |
| Referência usada para condicionar o TTS | `voice-reference.wav` | `c4854cc414c890eb546c480c41cd57aa358e6c649ff3b0fc9b9f991ed8fc6bc0` |
| Referência efetivamente ouvida | `voice-reference-listening.wav` | `50ca18f1be7127bdde90d2fb476625159d67c046257767b5468f02d631bc6b34` |

Pacote: `video-generation-amostras/p06-aprovados-20261015/voz-masculina-d/`, fora do Git. Contém `APROVACAO.json`, WAVs e instruções. Os quatro arquivos foram copiados e seus hashes comparados aos originais. O áudio do próximo ensaio de avatar deve ser `speech.wav` exatamente, sem ressíntese.

Texto ouvido: “Olá, eu sou o João. Uma boa mensagem aproxima pessoas. Vamos apresentar sua ideia com calma, clareza e um jeito natural de conversar.”

## Receita experimental aceita nessa amostra

- Qwen Base MLX bf16, revisão `a6eb4f68e4b056f1215157bb696209bc82a6db48`, MLX-Audio 0.5.9.
- Referência Cadu/OHF, publicação humana pt_BR destinada a TTS sob CC0, com transcrição candidata registrada no request N.
- Seed 20261015, temperatura 0,9, top-p 1, top-k 50, repetition penalty 1,5, limite 512 tokens.
- EOS real 2150 observado, sem clipping. Watermark Perth nulo, conforme o ensaio.

A melhora de naturalidade foi obtida sem trocar os pesos Base entre H e N. Isso apoia a utilidade da intervenção de referência neste caso. A mudança também altera locutor, duração e conteúdo; não prova causa única abstrata “humano versus sintético”.

## Confirmação e próximo vídeo

A revisão do Astra após o aceite recomendou uma única confirmação com dois WAVs. Ambos já foram gerados, localmente e com rede bloqueada durante TTS/ASR. O modelo, a referência e o sampler permaneceram iguais. Aprovação dessas novas saídas precisa ser explícita; D continua aprovada mesmo se outra falhar.

| Amostra | Mudança | Duração | Verificação automática | Aceite humano |
|---|---|---:|---|---|
| O | Mesmo texto; seed 20261016 | 9,52 s | EOS real, sem clipping; ASR large corresponde ao texto, small diverge em “aproxima pessoas” | Pendente |
| P | Outra frase; seed original 20261015 | 10,32 s | EOS real, sem clipping; ambos os ASRs correspondem ao texto | Pendente |

A divergência lexical do ASR em O não confirma erro na fala. ASR não avalia sotaque nem naturalidade. As cópias de escuta preservam duração e PCM16 mono/24 kHz, com ganho constante para aproximadamente −23,5 LUFS. Não houve corte, limiter ou alteração de tempo.

Página privada: `video-generation-amostras/p06-confirmacao-voz-20261015/revisao.html`. WAVs de escuta: O SHA-256 `972801bc72c604e0ad9b8b8aa98608eeb29bf8922379663878fb01522f272eff`; P SHA-256 `048bbeb93796753b68010a7f78d8b1a8c6de5e781501cd71edd1d3e39297f6bc`. Requests, freeze, pesos verificados, fontes, logs, ASR e dados brutos ficam no pacote privado. Os temporários de execução foram removidos.

O ensaio de avatar pode receber o WAV D diretamente pelo CLI de `avatar_stage.py`, que não ressintetiza áudio. O preparo externo deve conferir hash antes/depois e preservar o WAV ouvido. A finalização deve receber o mesmo D como áudio, com medição posterior da conversão AAC. O vídeo gerado ainda precisa de inspeção de corpo, expressão, boca, cenário e sincronismo.

Prévia masculina preparada em CPU pelo pipeline canônico de recorte/composição, com o modelo BiRefNet local conferido por SHA-256. Comparadas escalas 0,8/0,9/1,0 em 1080×1920. A escala 0,9, centro x=0,5 e base y=1,0, esconde as bordas laterais cortadas da foto e mantém espaço acima do cabelo. A imagem foi inspecionada visualmente. O enquadramento original contém cabeça, ombros e busto, sem mãos ou braços completos; isso limita o movimento que pode ser avaliado.

Pacote privado de preparo: `video-generation-amostras/p06-avatar-d-20261015/`. O áudio copiado para o render é D exato, protegido contra escrita. A prévia estática não é evidência de movimento ou sincronia de um vídeo novo.

## Condição da GPU para o próximo ensaio

Consulta autenticada em 15/10/2026, relógio 17:56:04 UTC, registro 17:58:30 UTC: saldo exibido US$ 0,27; consumo de armazenamento aproximado US$ 0,068/h; recarga automática desativada. A100 80 GB e H100 80 GB Spot sem capacidade. O volume original `OS-fHuXBon4`, 250 GiB, permanece destacado em FIN-01; não havia instâncias.

A extrapolação de desempenho anterior dá 895,932 s de avatar para o áudio D. Na tarifa histórica A100 de US$ 0,998/h, mais armazenamento, seriam aproximadamente US$ 0,2653 sem inicialização/download, US$ 0,3541 com cinco minutos adicionais ou US$ 0,4430 com dez. A tarifa A100 não foi reconfirmada porque não havia capacidade. O saldo exibido deixa apenas cerca de 16 s para todas as etapas adicionais, sem reserva artificial de US$ 1.

Uma RTX PRO 6000 96 GB estava disponível em FIN-03 por US$ 1,151/h, fora do cenário validado e da localização do volume. Não foi provisionada. A próxima execução depende de recarga e GPU compatível disponível. Nenhum recurso, chave, notificação ou recarga foi criado nessa consulta. Evidências privadas: `p06-confirmacao-voz-20261015/verda-consulta/`.

Atualização em 15/10/2026: a recarga relatada pelo usuário foi confirmada no console às 18:35 UTC, com US$ 20,22. A capacidade A100 em FIN-01 desapareceu antes do deploy; um clone temporário para FIN-02 foi iniciado, mas a disponibilidade mudou novamente. Foi criada uma única A100 80 GB On-Demand em FIN-03, por US$ 1,996/h, com OS novo temporário de 250 GiB. O volume original permaneceu destacado e intacto em FIN-01. Os recursos temporários e sua limpeza ficam identificados no [registro do ensaio de avatar D](P06-AVATAR-D.md).

## Limites e integração

Este aceite cobre naturalidade, sotaque/pronúncia e entonação de uma amostra masculina. Não conclui a voz feminina, números/negativas, outros textos/seeds, estabilidade de produção ou a P06 inteira.

O worker ainda executa Chatterbox; `tts.engine` não seleciona Qwen automaticamente. A adoção exige runtime CUDA, transcrição da referência e proveniência humana/CC0 nos contratos e manifestos. Os pesos MLX não constituem um runtime Linux/CUDA pronto.

O procedimento local atual [C7](PROCEDIMENTO.md) exige Perth verdadeiro. Esse critério e o reuso do piloto são centrados em Chatterbox; não declarar C7 satisfeito com D de watermark nulo. O ensaio privado direto de avatar não é homologação integral desse contrato. Alterar a regra ou aplicar watermark exige decisão técnica explícita e verificação; uma transformação que muda o WAV não herda automaticamente o aceite dos bytes anteriores.
