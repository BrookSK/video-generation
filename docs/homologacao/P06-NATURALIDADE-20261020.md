# P06 — testes de naturalidade em 20/10/2026

## Retomada de 20/10, 23h — acesso resolvido e nova Ana preparada

O acesso foi concluído pelo usuário no Brave. O console autenticado confirmou
saldo de **US$ 0,20**, lista de instâncias vazia, nenhum volume ativo e cobrança
atual de **US$ 0,00/h**. O detalhe da VM
`e722d027-731e-4df1-aa8d-2932a30350ee` registra `Instance deleted` em 20/10 às
22:40:07 BRT, ou 21/10 às 01:40:07 UTC. Não foi executada uma exclusão nesta
retomada. Esse estado substitui a pendência de confirmação cloud da seção abaixo;
o atraso anterior no encerramento permanece registrado.

O histórico de cobrança mostra **US$ 3,77** para a primeira VM e **US$ 9,04**
para a VM da Ana compacta: **US$ 12,81 só de compute**. O teto anterior de
US$ 12,50 foi ultrapassado em pelo menos US$ 0,31, antes do armazenamento.
Não usar as reservas de US$ 10,39 como custo real. O custo acumulado de US$ 6,94
do clone cobre desde 16/10 e não foi atribuído integralmente à rodada de 20/10.
A parcela exata de armazenamento desta rodada continua sem conciliação completa.

O clone `0338dfad-930b-479f-af0b-81b09ff54c0d` está `Deleted`, recuperável,
com 94 horas restantes e restauração cotada em US$ 0,07 na consulta. Os dois
volumes originais aparecem recuperáveis por cerca de uma hora. O usuário foi
informado desse prazo. Não houve restauração, alteração dos originais, criação
de compute ou recarga. A A100 de 40 GB `1A100.40S.22V`, em FIN-02, estava
disponível por US$ 1,531/h, com cobrança em blocos de dez minutos. A consulta
não contratou recursos. Valores e capacidade precisam de nova conferência
antes de uma execução posterior.

A nova tentativa `ana-wide` está preparada no pacote privado
`visual-ana-aberta-low-vram/`, contrato SHA256
`34d8f039a95f47975411bf9918342800d09b2d1866abbb115b17ee3442424b74`.
Muda apenas a PNG de entrada para a referência mais aberta já existente,
`ana-current-prepared.png`, de SHA256
`e14dde8f4722c8f3294a6089cd51caa5ae049ed4806fa4e2e10268ba7649055b`.
O request e o WAV são idênticos aos da Ana compacta. Prompt, seed, CFG, pesos,
passos, shift e perfil de memória foram preservados. A imagem foi aberta e
inspecionada. É um experimento de enquadramento, sem garantia de correção ou
aprovação de naturalidade.

Os 20 arquivos do contrato foram conferidos e **13 testes CPU passaram**.
A prova de transporte confirmou a presença de `ana-wide/out` vazio e validou
os arquivos depois da extração. Uma cópia temporária passou no bind de uma
identidade simulada e recusou uma segunda vinculação; isso não criou uma VM.
O pacote original continua sem VM e com autorização falsa. O preparo de QA
aceita `ana-wide` somente com seu recibo real e limpeza confirmada; o recibo
antigo foi recusado antes de criar mídia. Quatro contratos de QA anteriores
continuaram válidos.

Os hashes e os metadados dos três MP4s finais existentes foram conferidos
novamente. A entrega permanece **parcial, três de quatro**. A Ana aberta ainda
não foi gerada. Não houve nova escuta, reprodução contínua ou aprovação humana.
O runtime CPU removido não foi recriado sem uma candidata elegível.

Foi solicitado crédito e um **novo limite adicional de até US$ 3,50** para
uma única inferência. Essa proposta continua sem autorização. A recarga mínima
exibida no console é US$ 20; o restante seria saldo da conta, sem autorização
de consumi-lo nesta tentativa. O limite anterior não foi ampliado por inferência.

Recibos e capturas ficam em `verda/retomada-20261021/`; a confirmação cloud é
`ESTADO-CONFERIDO.json`. O manifesto da entrega agora referencia esse recibo
e registra `cloud_cleanup_pending=false`, mantendo os três MP4s e seus hashes.
O preparo e os testes estão em `visual-ana-aberta-low-vram/CPU-VALIDATION.json`
e `qa-local/setup/ANA-WIDE-QA-COMPAT.json`.

## Retomada de20/10,21h27 BRT — histórico anterior à confirmação cloud

Há três vídeos exportados e tecnicamente verificados: João, Rafael e Marina. A
segunda Ana, `ana-compact`, também foi rejeitada. No quadro225,9s, as duas mãos
ultrapassam as bordas laterais do nativo. O prompt de gesto compacto não resolveu
o defeito. O nativo tem SHA256
`dc5fdc16e3e1250e8b819512caec590e820275ab0eaae3a3979797bb2ecf5cbb`.
Nenhuma das duas Anas foi promovida como quarta entrega. A naturalidade do
conjunto continua sem aprovação humana; não houve escuta pelo agente.

A VM2 permaneceu ligada durante a interrupção além do prazo original de
21:15:40UTC (18:15:40BRT). A retomada encontrou a GPU ociosa às00:27:48UTC de21/10
(21:27:48BRT de20/10), sem container em execução. Às00:30:49UTC foi enviado
`shutdown -h now` por SSH, com saída0. Uma conexão posterior expirou. Isso não
comprova exclusão no provedor nem encerramento da cobrança. O painel deslogou por
inatividade; aceitou a senha existente e exigiu código de seis dígitos por
e-mail. A exclusão da VM e o retorno do clone ao armazenamento recuperável
continuam pendentes desse acesso. Nenhum prazo foi reiniciado e nenhuma nova
inferência foi lançada. O custo real precisa ser conciliado; a reserva anterior
não deve ser apresentada como fatura ou prova de cumprimento do limite.

Foi localizada referência existente da mesma Ana com enquadramento mais aberto:
`p06-femininas-v2-20261016/framing/ana-current-prepared.png`,1092×2028, SHA256
`e14dde8f4722c8f3294a6089cd51caa5ae049ed4806fa4e2e10268ba7649055b`.
É uma hipótese de entrada diferente do retrato fechado usado nas duas tentativas.
Ainda não houve nova geração com essa imagem. A etapa depende da limpeza da VM,
conciliação do orçamento e de um novo pacote de execução limitado.

O agente Astra anterior ficou indisponível nesta conta. A inspeção local foi
retomada com o modelo disponível, sem GPU ou chamadas de mídia pagas. O vídeo
anterior de câmera fixa também apresenta dedos cortados na borda inferior e
não foi renomeado como resultado novo.

O estado e os hashes estão em `operacao/INCIDENTE-PRAZO-VM2-RETOMADA.json`,
`operacao/REJEICAO-ANA-COMPACTA-V1.json` e
`operacao/ENTREGA-PARCIAL-RETOMADA.json`. As seções seguintes registram a execução
anterior e não substituem este estado atual.

Os dois diretórios temporários de transporte e runtime CPU foram removidos na
retomada, sem processos próprios em uso. Evidências, fontes e caches originais
foram preservados. O runtime deve ser reconstruído offline antes de nova QA.

## Registro da execução anterior

Execução autorizada pelo usuário após o retorno de Lucas. A correção abrange as
quatro personas e prioriza fala, expressões e interpretação no vídeo puro.
Não há implementação de cenas, trilha, legendas ou montagem do roteiro de aula.

**Situação em 20/10, 19:53 UTC:** candidatas D, Rafael e Marina finalizadas e
verificadas. A primeira candidata Ana foi rejeitada por saída das mãos do quadro.
Um novo teste limita a amplitude dos gestos, mantendo os demais insumos e
parâmetros. A situação será atualizada com os recibos reais e o encerramento dos
recursos antes de concluir.

## Prova controlada

As amostras preservam os WAVs, retratos, seed42, quatro passos, shift7,
LightX2V T2V rank32, BF16 e ausência de quantização. D e Rafael usam CFG de áudio2;
Marina e Ana usam1. O texto falado não foi reescrito nem ressintetizado.

A direção anterior prescrevia um gesto suave e retorno à posição neutra. A nova
candidata pede interpretação de conversa, variações moderadas de gestos,
expressões e pequenos movimentos de cabeça acompanhando fala e pausas. O teste
não considera maior quantidade de movimento uma aprovação de naturalidade.

A10080/H100/H200/B200 estavam indisponíveis na consulta inicial. Foi usado o
perfil oficial de baixo consumo de VRAM, com `num_persistent_param_in_dit=0`, em
A10040. Isso muda a residência dos parâmetros entre CPU e GPU, mantendo o mesmo
digest do worker e os pesos conferidos. Não é quantização. A guarda de30min por
inferência e a reserva de480s preservam coleta e exclusão do compute. A janela
inicial de2h foi ampliada, por contrato separado e testes novos, para3h desde
a mesma criação real. Isso permite concluir a fila na mesma máquina após medir
23min de render e3min de preflight por job. O relógio não foi reiniciado; a
reserva de US$5 para a janela completa substitui a de US$4 dessa mesma VM. O teto total reservado para a tarefa é US$12,50; não houve
recarga de saldo.

Referência de implementação: [README fixado do InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk/blob/50aa0a94184315407a991ae804d9b58d6d311ba8/README.md).
As fontes e a comparação do código ficam em `PROFILE-EVIDENCE.md` no pacote privado.

O controle D foi gerado novamente nesse perfil antes de mudar o prompt. Em
relação ao histórico, não houve quadros decodificados idênticos e o SSIM global
foi0,969833. Isso demonstra similaridade, não equivalência exata do fallback.
A comparação de prompt em D usa a dupla nova no mesmo hardware e modo de memória.
As outras personas têm bases históricas próprias; eventuais diferenças também
incluem a mudança de hardware/residência. Não atribuir toda diferença ao prompt.

## Base real e finalização

O D de controle terminou com246quadros,25fps,9,84s,448×832. Recibos do job e do
lote passaram; ausência dos containers foi confirmada. Nativo SHA256:
`f896c0b98cfed80c5b581acb424b9fc78dc7528bfa11489bd6c55d7762857a06`.
A conexão SSH inicial caiu durante o processamento. O controlador e o render
continuaram ativos e ambos os recibos finais passaram. Não houve repetição da
inferência. Os lançamentos seguintes usam controlador limitado, desacoplado da
conexão, com stdout e stderr em arquivo na própria VM.

O WAV integral foi mapeado novamente, sem corte, aceleração ou `-shortest`.
O PCM decodificado foi confrontado com encode AAC independente da mesma fonte.
Mídia e quadros densos passaram. A ROI facial foi escolhida por geometria e as
imagens reais foram abertas antes do score.

O SyncNet novo da base apresentou−2quadros nas três janelas e nos dois métodos;
os controles de±200ms foram recuperados. O root selecionou+2quadros de atraso
visual a partir dessa medição. A variante alinhada preserva o quadro inteiro em
1080×1920, sem crop/zoom e com áudio idêntico à base após decode. Mídia, densos,
ROI revista e SyncNet foram repetidos nesse arquivo: residual0 nos seis casos,
controles recuperados. O finisher com atraso não zero foi assim executado e
verificado, além do smoke anterior com atraso zero.

Base alinhada SHA256:
`1022d7733f399898d1a7c11236240c4de9071b2bfafc8c2da2ebfbed61ff4228`.
Serve de comparação, não é uma candidata de nova atuação nem aceite do cliente.

A candidata D terminou com os mesmos 246 quadros e 9,84 s. Seu nativo tem SHA256
`7b8a84e634a07729eb3c5ed886ab5cd92e672ad18645791af3982af812d59193`.
O SyncNet dessa nova amostra também mediu −2 quadros nas três janelas e nos dois
métodos. A seleção explícita de +2 quadros usou essa medição própria, com controles
recuperados. O arquivo final passou novamente em mídia, densos, revisão da ROI e
SyncNet, com residual zero nos seis casos e áudio decodificado idêntico ao da base.
SHA256 final: `eabfaddff277307a7d8720bb81cfd83803d233fedf6d402990567e4bfa705cf9`.

O contato mostra outras inclinações de cabeça e momentos diferentes de abertura
e contato das mãos. A candidata ainda repete contato de mãos. Não há demonstração
de que o prompt eliminou essa repetição ou melhorou a naturalidade percebida.

A candidata Rafael terminou com 248 quadros, 9,92 s e nativo SHA256
`321b08047e606918b4e008a458d0897f57054ccd0455b79793ea38ea131d6055`.
Os scores novos apresentaram início −2/−2, meio −3/−2 e fim −3/−3 quadros,
respectivamente nos métodos oficial/interior. Os controles passaram.
O root selecionou +2 quadros usando essas curvas próprias. A soma das distâncias
nos seis pares foi menor em −2 que em −3; a escolha preserva o tempo da fala e
deixa os resíduos previstos dentro de um quadro.

O arquivo final do Rafael passou novamente em mídia, densos, nova ROI HD aberta
antes do score e SyncNet. Resíduos reais: início 0/0, meio −1/0 e fim −1/−1;
controles recuperados e PCM idêntico à base. O critério técnico aceito é residual
absoluto de até um quadro e diferença de até um quadro entre métodos, com os
controles válidos. Há, portanto, um resíduo de até 40 ms; não se declara zero em
todas as janelas. Não houve correção temporal por trecho. SHA256 final:
`bf43d76a781e5aef66b632881bfc5d69b8ca14f3f2c819081d975a2803b77ac8`.
As mãos também retornam à posição unida várias vezes nessa candidata.

A candidata Marina terminou com 244 quadros, 9,76 s e nativo SHA256
`05a0469bc3ffc7c401f9895a0692a4765dc760f61d410fde2057da07058e5965`.
As três janelas e os dois métodos mediram −3 quadros, com controles recuperados.
O root selecionou +3 quadros dessa medição. Após a exportação, mídia, densos,
nova ROI HD e SyncNet foram repetidos: seis resíduos zero, controles válidos e
PCM decodificado idêntico à base. SHA256 final:
`92e0dc83691fd8695986164325f642857c5c8f227e9ee90e406e8049f432e518`.
O contato repetido das mãos também permanece nessa candidata.

## Ana: defeito encontrado e teste corretivo

A primeira candidata Ana terminou com 247 quadros, 9,88 s e nativo SHA256
`c70ad1ee51e82486d9dac88927d8ee9f95f5a54ff3ad9f1400b73182ea465247`.
O render e a coleta passaram. Isso não bastou para aceitar a amostra: no quadro
225, perto de 9 s, as duas mãos ultrapassam as bordas laterais do nativo. O root
e o Astra abriram o PNG real e rejeitaram essa candidata para entrega. O defeito
não seria resolvido por escala, faixas pretas ou alinhamento labial.

O teste `ana-compact` mantém retrato, WAV, seed, CFG, pesos, passos e perfil A10040.
Altera somente a direção de atuação: gestos pequenos à frente da cintura e do
tronco, cotovelos próximos ao corpo e mãos dentro da silhueta lateral do tronco.
A instrução de evitar contato repetido das mãos também permanece. Um prompt não
garante obediência; a nova mídia precisa ser inspecionada antes de ser aceita.

A VM da primeira rodada já estava excluída e a exclusão foi conferida no painel.
Foi restaurado apenas o clone de cache, com cotação observada de US$0,00, para uma
nova VM A10040 de mesmo perfil. A criação real é 19:45:40 UTC, com prazo máximo de
exclusão às 21:15:40 UTC. Não houve reinício do relógio da VM anterior nem repetição
de uma inferência após falha de conexão. O contrato novo permite uma inferência.
A reserva de US$3,50 foi persistida antes da restauração e criação; somada à
reserva anterior inteira de US$6,89, conservadoramente mantida, totaliza US$10,39,
dentro do teto de US$12,50. Não houve recarga. Esses valores são limites de reserva,
não uma conciliação da fatura.

O primeiro preparo na nova VM parou após o preflight: o arquivo de transporte
continha os arquivos do manifesto, mas omitiu a pasta vazia `out`. Nenhuma
inferência começou (`jobs=[]`, sem diretório de execução do job, log ou nativo).
A falha e os hashes foram preservados. A reprodução mínima em CPU confirmou a
omissão; cinco testes conferiram a recuperação e a recusa diante de qualquer
indício de render anterior ou limpeza inconclusiva. O preparo corrigido copia os
mesmos 17 arquivos e contrato para uma pasta nova, cria `out` vazio e exige nova
autorização explícita para a primeira inferência. A VM, a criação real, o prazo e
a reserva permanecem os mesmos.

## Limites de avaliação e fontes

O agente inspecionou contatos e quadros reais, incluindo mãos, rosto, começo,
cauda e junções. Não houve escuta direta nem avaliação contínua da fluidez.
As métricas verificam alinhamento e integridade; não medem prosódia, intenção de
gesto ou naturalidade percebida. A crítica do cliente ao conjunto continua válida;
aprovações anteriores de voz não encerram essa avaliação.

O Astra confirmou a mesma limitação de áudio do root em uma única tentativa
com o WAV real da Marina: a ferramenta omitiu o áudio por ausência de suporte de
entrada. Não se substituiu escuta por transcrição. As janelas de SyncNet têm 4 s
e se sobrepõem; não são avaliações independentes nem cobrem integralmente as bordas.

O pacote privado fica em:
`/Users/felipebianchini/Developer/video-generation-amostras/p06-naturalidade-execucao-20261020/`.

- `visual-low-vram/`: dupla D, contrato `f76eeb7c996952570934e3dc50a155343b47477c6363d1d37f10aea5bb80b1c3`.
- `visual-personas-low-vram/`: preparo inicial de2h, preservado sem inferência.
- `visual-personas-low-vram-3h/`: Rafael, Marina e primeira Ana, contrato `35068e771ea5603888bcf44eb9764548320033f1e494e2cf6cc617775bcabb48`; a Ana desse pacote foi rejeitada.
- `visual-ana-compacta-low-vram/`: teste corretivo da Ana, contrato `e385536860247a9ebc4d165a3d7aa1b0b50207494b26b252fb8ff9405204422d`.
- `operacao/`: reservas, autorizações por job, gates de revisão e coletas por SHA.
- `qa-local/`: preparação, fontes, imagens de inspeção, scores, seleção e finalização.
- `verda/`: acesso recuperado, restauração do cache e identidade real da VM.

Os testes CPU dos controladores passaram: 27 no pacote D, 31 no preparo das outras
personas, 33 na continuação de 3 h e 10 no teste corretivo da Ana, incluindo vínculo
à criação real de cada VM. Os manifests foram verificados antes do envio. Pesos e worker foram
reutilizados do cache; não houve pull, instalação ou download de modelos na GPU.
O runtime CPU de QA foi reconstruído offline e posteriormente removido na retomada, conforme registrado acima.

Os MP4s do pacote enviado em19/10 permanecem intactos. A receita global draft e
a aplicação não foram promovidas com base nestes ensaios.
