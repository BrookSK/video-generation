# P06 — revisão de qualidade e próxima rodada

Registro de 15/10/2026. **P06/T06 continua incompleta.** A rodada retestou falas
na GPU, gerou duas opções adicionais de prosódia no Mac e preparou uma amostra
curta de vídeo, que não iniciou após preempção.
Cada resultado precisa ser avaliado;
checks locais e ASR não aprovam voz, movimento ou cenário. A receita de produção
permanece `draft`.

## Resultado usado como base

Preview `calibracao-d001-preliminar-01/feminina-escritorio-9x16/run-1/final.mp4`,
preservado no diretório privado de amostras do projeto.

- SHA-256: `ca29e2b64dcbd48b476d711f61d4c822b7c3824a81f440982b8419903ffbccaa`.
- Imagem do worker: digest
  `sha256:f2814d283009ef7ebcb941367b531631e5008623ef2667cc92eadd8d1c4f06ff`.
- Vídeo: 25,96 s, 1080 × 1920, H.264/yuv420p, 25 FPS; áudio AAC a 48 kHz.
- Render nativo: 448 × 832. A saída 1080p é ampliada; não representa inferência
  nativa em 1080p.
- Avatar: 2.304,575 s de processamento, pico de 49.328 MiB de VRAM.
- Pipeline medido: 91,05 s de computação por segundo de vídeo.

Quadros em 0, 13 e 25,9 s, além de uma grade em 3, 9, 15 e 21 s, mostram pessoa
frontal em plano de busto, com variação de boca, olhos e expressão. Os ombros mudam
pouco. O escritório é visível, mas o avatar ocupa grande parte do quadro.
Inspeção de quadros não permite aprovar sincronia labial ou naturalidade temporal.

A fala de entrada mistura apresentação, pedido, preço, parcelas, telefone,
horários e negativas. É útil como teste de C1, mas tem pouca continuidade como
mensagem de demonstração.

O áudio desse preview também foi transcrito offline em 15/10 com
`mlx-community/whisper-large-v3-turbo`, revisão
`a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb`, sem fornecer a fala esperada como prompt.
O WAV analisado tem SHA-256
`ec66519f8cb198f92e020597eb5c42d9c567e5a4322a580a620b81b05d8e8c17`.
O diagnóstico está preservado como `asr-latest-preview-20261015.json` no diretório
privado de amostras.

| Trecho | Entrada | Diagnóstico automático |
|---|---|---|
| 3,78–8,16 s | Preço de R$ 149,90 em três parcelas | Valor reconhecido como “R$ 29,09,13 parcelas” |
| 11,38–16,46 s | Telefone 0800 721 4400; nove às dezoito horas | Dígitos e horário divergentes |
| 19,94–25,26 s | Verificar valores e conferir todas as informações | Palavras e números sem correspondência com a entrada |

Um segundo transcritor offline, `mlx-community/whisper-small-mlx`, revisão
`45f3915923c7a79a5a5b5a7d909d39aeb0e5630e`, apontou divergências nas mesmas
janelas. A transcrição exata difere, mas os dois recuperam trechos limpos e
encontram problemas nos valores, telefone e cauda. Registro privado:
`asr-latest-preview-small-20261015.json`.

Também foi transcrito o WAV de pré-medição `candidate-d001/v4/speech.wav`, do
mesmo texto/referência/digest, com seed documentada 20261014. O final e o telefone
foram reconhecidos de forma mais coerente, embora o preço ainda divergisse.
Registro privado: `asr-candidate-d001-20261015.json`. O piloto sintetiza de novo
a cada execução; a qualidade da pré-escuta não garante a qualidade do próximo WAV.

ASR pode errar e não substitui audição humana. Essas divergências, junto da queixa
do usuário, impedem tratar C1 como atendido após D001. Há problema de fidelidade
da fala a investigar, além de texto pouco natural. A próxima etapa elegível é TTS
isolado, antes de outro render longo. A comparação visual deve reutilizar o WAV
exato que foi revisado.

## Diagnóstico no código

O produto recebe a fala literal em `script_text`. Não há modelo que transforme
briefing em roteiro. Não normalizar ou reescrever a fala do cliente silenciosamente.
O corpus de demonstração pode ser editado, preservando a amostra anterior.

O prompt da receita pede movimentos sutis e também proíbe todos os gestos. Ele é
global, sem ações temporizadas por frase. A primeira variante deve pedir presença
mais natural de cabeça e ombros, mantendo as mãos fora do quadro por causa das
distorções observadas nos testes anteriores. Isso é uma hipótese de calibração,
não uma correção visual já comprovada.

O fundo é uma imagem cadastrada, ajustada por `cover` e corte central. Avatar e
fundo são compostos antes de entrar no InfiniteTalk. Alterar o enquadramento muda
quanto do ambiente aparece. Um fundo novo não deve ser confundido com ajuste de
movimento: comparar as variáveis separadamente.

Foram geradas prévias reais de composição em CPU com os materiais existentes,
`ensure_alpha`/BiRefNet portrait e `compose_canvas`. O modelo de recorte foi
conferido por tamanho/SHA-256 do manifesto. A tentativa de reduzir a escala
vertical de 0,8 para 0,72 foi descartada: aumentou o espaço vazio acima da cabeça
e expôs laterais cortadas da foto. O estúdio trouxe microfones ao lado do rosto.

A candidata usa escala vertical 0,9 com base 1,0 para reduzir o espaço acima da
cabeça; a alternativa de fundo é a sala existente. Cada fator tem uma prévia
separada. `comparacao-candidata-9x16.jpg`, no diretório privado
`p06-polimento-20261015`, também mostra a combinação apenas para comparação
estática. Isso não aprova a combinação no modelo de vídeo. O enquadramento 16:9
não foi alterado nesta variante; a foto original tem ombros cortados nas laterais,
o que limita quanto é possível afastar o avatar sem expor esse corte.

A correção D001 já existente foi integrada nesta branch antes das novas
verificações. Ela bloqueia publicação quando T3 termina sem EOS e aplica a política
v3 compatível com a base fixada. EOS confirma conclusão mecânica; não confirma que
o áudio contém todas as palavras corretas.

Foi acrescentado ao piloto um modo opcional de reutilização de TTS para a
calibração de uma amostra/uma execução. Ele exige hash explícito do WAV e confere
texto literal, língua, referência de voz, PCM mono/16 bits/24 kHz, duração medida,
limite e resultado de watermark. Os bytes conferidos são preservados em memória
no preflight e copiados para o render, sem chamar o sintetizador novamente. O
relatório identifica a reutilização; ela não representa um aceite humano.
A imagem do preview anterior não contém as novas flags. O código da alteração
está no commit `ba8659105989d5f32b99c2c8ec82d0fc3299b346`. A imagem nova foi
construída e publicada em CPU pelo Dockerfile canônico:

`vccr.io/5e20534f-f96c-42fb-8a52-deb4f7e28efc/avatar-worker@sha256:cad3a59ea8afb4197179a02ce6702a48bb9bf8f3f79acb586645291b53c632b4`

A tag `p06-quality-ba86591` e o índice remoto autenticado têm o mesmo digest,
conferido por SHA-256 dos bytes crus. O smoke da CLI Linux/amd64 passou sem
rede, com uid 10001, as duas flags presentes e label do commit conferido. Isso
valida publicação/CLI, sem afirmar qualidade de inferência. Logs e hashes de
21 arquivos estão em `p06-polimento-20261015/build/`.

O render preparado durante a janela curta usava a imagem D001 anterior com bind
somente leitura do módulo `pilot.py` desse commit. O overlay e seus hashes foram
registrados separadamente; o preflight passou, mas o render não chegou a iniciar.
Novas tentativas devem
usar a imagem publicada, após conferir disponibilidade e saldo.

## Nova rodada de TTS

As falas curtas foram sintetizadas na A100 em 15/10/2026, com a imagem D001 e as
mesmas referências do manifesto. Os dois WAVs têm watermark detectado e foram
transcritos offline pelos dois checkpoints já usados no diagnóstico, sem texto
esperado no prompt.

| Amostra | Duração real | Diagnóstico dos dois ASRs |
|---|---|---|
| Demo feminina | 8,64 s | Todas as palavras do request recuperadas |
| Demo masculina | 11,44 s | Todas as palavras do request recuperadas |
| Stress numérico feminino | 26,52 s | Divergências em pedido, preço, telefone e oferta |

A demo feminina diz: “Olá, eu sou a Ana. Aqui, sua ideia ganha voz com clareza e
atenção. Conte com a nossa equipe para dar o próximo passo.” O WAV tem SHA-256
`edc29bf1aa83bb45b7a678b7e7fbcf5614f5ade81654ca0df1f9e4f79f1f4203`.
Os relatórios completos estão em `p06-polimento-20261015/asr/`, na área privada
de amostras. A correspondência lexical foi favorável, mas o usuário ouviu as duas
demos e respondeu **“Ainda precisam de ajuste”**. Ao detalhar o problema, indicou
**“A voz e a entonação”**. As duas estão reprovadas nesses aspectos. Manter os
textos como controle e não avançar ao render como se houvesse aprovação da voz.

No stress original novo, os dois ASRs reconheceram pedido 228 em vez de 218 e
valores diferentes de R$ 149,90. Telefone e trecho Júlia/oferta divergiram nos
dois. O final ficou mais próximo da entrada, mas a literalidade continua
reprovada neste ensaio de TTS. EOS e watermark detectado não impediram o defeito.
O SHA-256 desse WAV é
`9cfdd28201a65bbd3e73aaa3bb84a193620210d23e475210f87a8eb78b28c46d`.

O ensaio por extenso registrou saída zero no comando, mas a cópia não terminou
antes da remoção da instância. Seu WAV e resultado precisam ser recuperados do
volume e conferidos; não há diagnóstico local ou comparação válida dessa fala.
O overlay CUDA com temperatura 0,3 ficou apenas preparado, sem inferência.
Uma experiência local MPS com essa temperatura é registrada separadamente abaixo.

## Ajuste de voz e entonação após a escuta

Uma tentativa na CPU existente usou os cinco pesos TTS e a referência feminina
do manifesto, conferidos por tamanho/SHA, sem rede. Não terminou dentro do limite
de dez minutos e foi encerrada; não produziu WAV. O exit 137 veio do encerramento
explícito do contêiner, sem evento de OOM. O ensaio incluiu importações e ocorreu
durante atividade de disco do build; não é um benchmark isolado de CPU.
Contêiner e pasta temporária foram removidos, preservando os pesos úteis.

Foi então testada a GPU local do Mac, em ambiente descartável, com Chatterbox
Multilingual 0.1.7 e torch/torchaudio 2.6.0. Os mesmos cinco pesos e a referência
`pf_dora` foram conferidos. O estágio TTS D001 e a política v3 canônicos foram
preservados. O wrapper altera o device para MPS e injeta os controles registrados,
sem reescrever texto, aumentar tokens ou relaxar EOS. `sandbox-exec` negou rede;
um smoke permitiu tensor MPS e recusou socket localhost com EPERM. Código e saída
do smoke estão em `mps-tts/network-smoke.json`, na área privada de amostras.

| Opção feminina | Expressividade | Duração WAV | Tempo total do subprocesso | Diagnóstico dos dois ASRs |
|---|---|---|---|---|
| A | 0,40 | 8,24 s | 58,757 s | Todas as palavras recuperadas |
| B | 0,65 | 8,04 s | 31,750 s | Todas as palavras recuperadas |

As duas mantêm o texto da Ana, referência `pf_dora`, CFG 0,3, temperatura 0,8,
seed 20261015 e repetition penalty 1,2. A versus B muda somente expressividade;
comparar qualquer uma à demo CUDA anterior também muda device e outros controles.
Os tempos não isolam efeitos da configuração nem demonstram superioridade de B.
Ambas terminaram com exit zero, WAV PCM mono/16 bits/24 kHz e watermark detectado.

- A: SHA-256 `3c916d3f4163a911e3207f6367377abb829c76951127de5e5e3520ddc892797c`.
- B: SHA-256 `0387f614f54cd3c265119799d69cbdb1068d3c58609c9076ce1f6f241c996f03`.

As novas opções estão no topo de `p06-polimento-20261015/revisao.html`.
O usuário avaliou a nova rodada: **melhorou, mas ainda está robótica**, sobretudo
na saudação “olá” e na entonação das frases. Não houve escolha de A/B nem aceite.
Não foi criada uma nova voz masculina nesta comparação. ASR não escolhe a melhor
opção. Este ensaio MPS não
homologa o runtime Linux/CUDA da imagem publicada. O campo `peak_vram_mb=0` do
estágio mede somente CUDA e não representa uso zero de memória no Mac.

Requests, configs, wrapper, estágio original, freeze, logs, monitores, resultados,
WAVs e quatro transcrições ficam em `p06-polimento-20261015/mps-tts/`.
Nenhum vídeo novo foi gerado. Enquadramento, ações e fundo continuam candidatos
estáticos, sujeitos a comparação animada com áudio aprovado.

O diagnóstico numérico foi repetido localmente em MPS com temperatura 0,3,
CFG 0,3, expressividade 0,4, seed 20261015 e os mesmos pesos/referência:

| Caso | Resultado real | Diagnóstico |
|---|---|---|
| C, texto numérico V4 original | Exit zero, WAV 32,24 s, watermark detectado | Ambos ASRs apontaram pedido 2818 em vez de 218; preço e telefone também divergiram. Negativas, horário e trecho dos dois produtos/Júlia foram recuperados. A fidelidade continua reprovada. |
| D, equivalente por extenso | Exit 1, sem WAV nem resultado TTS | D001 recusou a saída porque T3 terminou sem EOS terminal. Não existe comparação auditiva C/D completa. |

O WAV C tem SHA-256
`1c4e23a5801ef18248aff0a3c2f3e843930c25e24b19f7f4af758baa690ef1a5`.
Reduzir a temperatura não resolveu a fidelidade neste ensaio. A versão por extenso
também não demonstrou solução. Nenhum limite ou guarda foi ampliado para contornar
a recusa. Esses resultados não corrigem nem encerram o defeito CUDA original.

Os ambientes temporários e o scratch de acessos foram removidos depois da
verificação. Não restaram processos MPS ou ControlMaster desta operação. Pesos,
referências, caches úteis e o volume original da Verda foram preservados.

## Modelos e responsabilidades

| Parte | Implementação atual |
|---|---|
| Voz | Chatterbox Multilingual 0.1.7 com checkpoint pt-BR e política v3 versionada |
| Referências de voz | Kokoro-82M, vozes sintéticas distintas `pf_dora` e `pm_alex` |
| Avatar e sincronia | InfiniteTalk single, Wan2.1 I2V 14B, Wav2Vec2 e LoRA LightX2V |
| Recorte | BiRefNet portrait por rembg |
| Fundo e composição | Imagem/cor cadastrada e composição por Pillow |
| Arquivo final | FFmpeg |
| Infraestrutura de teste | GPU alugada na Verda, na conta do cliente |

Pelo escopo, o cliente fornece conta, infraestrutura, créditos e materiais
autorizados, além de avaliar as amostras. Implementar, instalar e ajustar o
pipeline faz parte do trabalho técnico do desenvolvedor. Não existe dependência
contratada de SaaS de avatar ou voz. Os modelos podem ser substituídos dentro do
pipeline open-source se a calibração não atender à qualidade combinada.

Conferência no PDF original `lucas-n-avatar-ia-api-v3.pdf`, SHA-256
`5f4b37d34d190a951a65275e7b5d5c12bf049556038b970d2781c3394bba98b5`:
a página 2 deixa a escolha fina de TTS/avatar para a implantação; as páginas
1/5/7 permitem ajustar o provedor dentro do pipeline open-source. A tabela de
responsabilidades da página 6 atribui ao cliente infraestrutura, custos e
imagens/referências/materiais, sem exigir que ele entregue modelos neurais de
voz/vídeo prontos. Modelos na conta do cliente descrevem local e controle, não
fornecimento de um modelo próprio. O Whisper foi apenas transcritor diagnóstico;
os áudios desta rodada foram sintetizados pelo Chatterbox.

## Pesquisa posterior de naturalidade

Após nova reprovação de voz robótica, foi executada uma investigação em três
frentes: práticas de voz, movimento de avatar e avaliação audiovisual. Código,
papers e demos dos autores foram confrontados com os insumos e comandos locais.
A [síntese com fontes e resultados](../research/P06-NATURALIDADE.md) separa fatos,
hipóteses, ensaios realizados e testes ainda dependentes de GPU.

Foram gerados seis WAVs adicionais em ambiente local isolado: Chatterbox com
referência original/sem saudação; Qwen3-TTS Base 1.7B bf16 com as mesmas duas
referências, mais uma demo masculina e o stress numérico. O controle Chatterbox
reproduziu o WAV A anterior byte a byte. Os doze ASRs desta rodada preservam
divergências: preço/telefone continuam sem aprovação, e duas demos têm diferenças
de transcrição a conferir na escuta. Nenhum score acústico aprovou naturalidade.

Um controle adicional gerou o mesmo texto diretamente no Kokoro `pf_dora`,
sem clonagem posterior: 7,125 s, PCM16/24 kHz, saída zero e sem clipping.
Não houve ASR novo nem audição do agente nessa subtarefa. A API não fornece
EOS, marcado como não aplicável. O controle também está disponível com ganho
constante na página, separado da comparação principal; não há aceite novo.

As quatro opções femininas são apresentadas com rótulos neutros e ganho constante
para volume comum, sem mudar duração/velocidade. A página privada é
`p06-pesquisa-naturalidade-20261015/revisao.html`. Os bytes ouvidos têm hashes
próprios; não são declarados idênticos aos WAVs brutos. O retorno humano posterior considerou a amostra 2 próxima em naturalidade, mas
com início percebido como português de Portugal, e a 4 razoável, ainda precisando
melhorar. Nenhuma foi aprovada. A [investigação de sotaque](../research/P06-SOTAQUE.md)
confere a cadeia pt-BR e testa outra forma de condicionamento. Qwen não foi
integrado ao worker nem ao manifesto de produção; seus WAVs de experimento não
têm watermark Perth.

O áudio do MP4 antigo foi comparado ao WAV TTS: lag estimado zero e correlação
0,999974. Isso verifica a preservação do áudio pela finalização. Um teste SyncNet
posterior, com controles de atraso conhecidos e três janelas, estimou −80 ms
no original. A cópia diagnóstica com vídeo atrasado em dois quadros passou a
offset zero nas três janelas. O AAC decodificado é idêntico, sem corte da fala.
Os controles ±200/400 ms foram recuperados antes e depois. Consulte
[o ensaio completo](../research/P06-SYNCNET-ENSAIO.md). Isso não gera movimento
novo nem representa sincronismo perceptivo aprovado.

O par privado de scheduler passou em três checks de preparo: somente o argumento
`sample_shift` muda entre 7/2, com seed 42, WAV e imagem idênticos. Não houve
inferência desse par. O novo acesso ao console confirmou US$ 0,38 aproximadamente
às 16:16 UTC; A100 de 80 GB e os SKUs H100 consultados estavam indisponíveis.
Nenhum compute ou recarga foi criado nessa consulta.

## Reteste dirigido ao sotaque

O retorno sobre sotaque motivou [nova pesquisa e rastreio](../research/P06-SOTAQUE.md).
Não foi encontrada troca acidental de pesos/locale/rótulos para pt-PT. O Qwen Base
usado na amostra 2 recebe português genérico e não encaminha instruções de dialeto
pelo ramo ICL do runtime escolhido. O fine-tune Chatterbox brasileiro já estava
instalado. O frontend brasileiro correto, sozinho, não aprova a pronúncia percebida.

Foram gerados dois WAVs locais com Qwen VoiceDesign 1.7B bf16: descrição geral
versus a mesma descrição acrescida de pedido explícito de sotaque brasileiro.
Sem referência Kokoro, mantendo texto/seed/pesos/sampler do par iguais. Os dois
concluíram com EOS observado, sem clipping; durações de 9,04 e 9,52 s. Os quatro
ASRs preservam pequenas divergências de artigos e não classificam sotaque.

A nova página `p06-sotaque-20261015/revisao.html` apresenta duas opções A/B com
volume comum e mantém as antigas 2/4 para comparação. Os arquivos têm hashes
próprios. O usuário ouviu as duas opções e respondeu “Ainda nenhuma atende”.
Ambas ficam reprovadas; a coleta não demonstrou correção de sotaque. VoiceDesign não foi
integrado à produção e não houve novo render ou consumo de compute Verda.

O usuário pediu uma revisão ampla por Astra; foi chamado o modelo Astra com
reasoning medium. O [parecer](../research/P06-ASTRA-NATURALIDADE.md) recomenda um
controle com referência humana, sem atribuir causa única ao sotaque ou ao motor.
O controle N preservou a receita Qwen Base/H e trocou somente referência e sua
transcrição por gravação Cadu/OHF, publicada para TTS sob CC0. Uma saída de
9,84 s concluiu com EOS e sem clipping; large recuperou a sequência esperada,
small manteve a divergência “aproxima”/“a próxima” já presente em H.

A página `p06-sotaque-20261015/controle-referencia/revisao.html` mostra a fonte
humana e a comparação masculina H/N sob rótulos C/D, com volume comum.
O usuário aprovou a Voz D/N e a referência humana em sotaque, entonação e
naturalidade. O [registro de aprovação](P06-VOZ-APROVADA.md) fixa os bytes ouvidos.
Depois, o usuário informou que o cliente gostou da demonstração de áudio D.
Esse aceite masculino não aprova a voz feminina nem o vídeo novo.
A mudança de locutor/duração/conteúdo da referência impede chamar esse par de
isolamento exclusivo de “humano versus sintético”. Esse controle comparou apenas
áudio. Depois do aceite do cliente e da recarga, foi executado o [ensaio de
avatar D](P06-AVATAR-D.md), mantendo o WAV aprovado como entrada.

## Ordem econômica de validação

Usar o [pacote de calibração](../models/calibration/README.md). Cada comparação
precisa ter amostra base, mudança declarada e saída nova. Não substituir os
arquivos anteriores.

1. Gerar apenas o TTS das falas curtas. Ouvir e comparar palavra por palavra.
   Conferir nomes, negativas, números e fim da frase. ASR é apoio diagnóstico.
2. Se a voz falhar, corrigir e repetir só TTS. Não iniciar render de avatar com
   áudio já reprovado. Não aumentar o orçamento neural só para esconder repetição.
3. Renderizar a fala curta validada com a receita base. Comparar depois composição
   e prompt, um fator por vez, mantendo guia de áudio, voz e perfil do modelo.
4. Inspecionar começo, meio e fim, assistir com som, conferir mãos/bordas, rosto,
   expressão, cor e estabilidade do fundo. Uma execução com `status: ok` não aprova
   qualidade.
5. Só com a direção visual e a voz satisfatórias executar o lote de 30 s nas duas
   vozes e formatos, com duas execuções, seguido de 60 s vertical, 720p e teste GPU.
   O runner chama a primeira de fria e as seguintes de quentes, mas recarrega os
   modelos em cada subprocesso: são repetições com possível cache de disco, não
   inferência com modelo residente. Duração vem do áudio real, não do nome do arquivo.
6. Registrar C1–C7 e desempenho com veredito humano antes do freeze. Depois seguir
   os demais cenários da [homologação](PROCEDIMENTO.md).

## Saldo e acesso

O último fechamento, às 03:49 UTC de 15/10/2026, registrou US$ 1,41 de saldo,
reserva de US$ 1 e apenas o volume original preservado, a US$ 0,06849/h.
Compute e clone temporário foram excluídos. **Esses valores são históricos.**

Nesta conversa, o usuário atualizou a orientação: usar os créditos restantes nos
testes antes de solicitar recarga. Portanto, a reserva anterior de US$ 1 não
bloqueia esta rodada. Isso não autoriza recarga automática nem exclusão do volume
original. Priorizar TTS isolado e confirmar o saldo atual antes de criar compute.
O acesso existente ao console e ao registro foi recuperado. O saldo real era
US$ 0,80 antes da criação da instância. Nenhuma recarga foi feita. O alias SSH
antigo foi descartado como evidência de instância atual.

Foi criada uma A100 de 80 GB spot em FIN-01, às 13:50 UTC de 15/10/2026:
`avatar-p06-quality-ba86591`, ID `d17d0320-7a6a-4b1b-b9ba-2ff365dbe729`,
US$ 0,998/h. O volume original `OS-fHuXBon4`, 250 GiB, foi reutilizado,
sem clone, a US$ 0,06849/h. A política de remoção preserva o armazenamento.
O limite operacional planejado era 14:27 UTC, para salvar as saídas e excluir
compute antes de esgotar o saldo e perder o volume.

O preflight confirmou A100/80 GB, CUDA, hashes de 40 arquivos de modelos e duas
referências, além das 38 entradas do pacote. A imagem D001 `f2814d2…` foi obtida
do registro autenticado e conferida. Os estágios de inferência rodam sem rede,
com uid 10001 e modelos/entradas montados somente para leitura.

Às aproximadamente 14:02 UTC, o console indicava US$ 0,44, 25 minutos estimados
e uso total de US$ 1,07/h. A [cobrança da Verda](https://docs.verda.com/welcome-to-verda/pricing-and-billing/)
antecipa blocos de dez minutos e pode remover instâncias e volumes ao zerar o
saldo. Usar o saldo restante não significa provocar a perda do volume original.

O log de auditoria autenticado confirmou `discontinue_reason:
evicted_by_on_demand` às 14:04:59,294 UTC. A instância foi excluída e o volume
desanexado às 14:05:08 UTC. A tentativa de render às 14:06:20 UTC foi recusada
pelo SSH, cuja chave não correspondia ao pin. Nenhum comando do render chegou
a executar. Não trocar o pin para acessar o IP já reassociado.

A recuperação consultou A100 de 80 GB/H100 sob demanda e spot, além de CPU
Turin de 8/16 vCPUs. Não havia capacidade compatível disponível; nenhuma
instância de recuperação foi criada. O console confirmou lista de instâncias
vazia e volume original `Detached`. Às aproximadamente 14:10 UTC, o saldo era
US$ 0,44 e o uso era apenas US$ 0,06849/h do volume. Não foi possível usar
todo o saldo nesta janela por falta de capacidade. Não há MP4 novo, comparação
animada, aprovação de movimento/sincronia ou receita congelada nesta rodada.

Com o desempenho anterior de 91,05 s/s e o preço desta janela de US$ 1,06649/h
(GPU e volume), oito execuções de 30 s custariam cerca de US$ 6,47; incluindo uma
de 60 s, cerca de US$ 8,09. Essa projeção não
inclui 720p, preparação, espera por clonagem, repetições ou a matriz final. A
reserva de armazenamento vem além disso. Preço, capacidade e saldo devem ser
conferidos antes de contratar a próxima janela.

O saldo restante deve ser aproveitado quando houver compute compatível. Ele
não cobre a matriz completa. A recarga não resolve sozinha a indisponibilidade
de capacidade. Avisar o usuário quando o saldo real não cobrir a próxima janela,
sem solicitar novo login já restabelecido.

## Verificação desta alteração

- Suíte local do worker: **282 testes passaram; um teste GPU não selecionado**.
- Ruff do worker e do preparador: sem erros. Formatação dos três arquivos Python
  alterados/novos: sem diferenças pendentes.
- Nova bateria de 15 casos verifica reuso dos bytes, ausência de ressíntese,
  rejeições no preflight e preservação do fluxo antigo. A reprodução anterior à
  implementação falhou como esperado. Revisão independente: nenhum finding aberto.
- Novo pacote privado `in-publicado`: três receitas e quinze filas válidas,
  oito requests coerentes e hashes dos 38 arquivos conferidos. Usa o digest
  publicado `cad3a59e…632b4`; somente a imagem muda no baseline. O pacote anterior
  `in` e o stress numérico anterior foram preservados byte a byte.
- Seis WAVs reais salvos localmente e comparados com dois ASRs offline cada:
  três na A100 e três no MPS. As demos A100 foram reprovadas
  pelo usuário na voz/entonação; A/B tiveram melhora parcial, ainda sem aceite
  por fala robótica. O stress A100 também
  apresentou divergências lexicais, assim como o novo caso C. O caso D foi
  recusado sem EOS e não gerou WAV. O ensaio por extenso anterior da A100 precisa
  ser recuperado do volume; o render não iniciou.
