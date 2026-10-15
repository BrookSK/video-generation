# P06 — sotaque e referências de voz pt-BR

Pesquisa de 15/10/2026. Escopo: encontrar uma referência humana curta de português brasileiro com base explícita para clonagem e saídas comerciais; revisar os dados acústicos já preservados de J/F. Esta frente inicial não executou inferência ou download de corpus. Os ensaios posteriores estão registrados em [P06-SOTAQUE.md](P06-SOTAQUE.md).

A captação abaixo é uma alternativa para um ensaio posterior de clonagem; o par VoiceDesign desta rodada não depende de gravação ou contratação. Os campos propostos de autorização são critérios desta investigação de referências, não uma nova exigência atribuída ao escopo do cliente.

**Caminho recomendado para obter uma referência humana própria:** gravar uma referência nova com um adulto nativo de pt-BR que autorize expressamente a clonagem da própria voz e as saídas comerciais do projeto. Pode ser um colaborador voluntário ou locutor contratado. É o caminho curto que permite controlar simultaneamente sotaque percebido, captação, texto e autorização. Nas fontes públicas consultadas, não encontrei um par feminino/masculino pronto com evidência suficiente para marcar a clonagem comercial como autorizada sem verificar o escopo com o titular/fornecedor.

## Referência pública encontrada na investigação posterior

A busca dirigida localizou as próprias gravações humanas brasileiras no GitHub [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets/blob/8ed76fa9001fafc77db32bd682f434938c679e3e/README.md), sob CC0 e com finalidade explícita de produzir TTS. A publicação direta contém uma pequena amostra para Cadu, Faber e Jeff. Essa rota dispensa conta no Mozilla Data Collective e não exige localizar um contrato individual privado adicional para executar este diagnóstico dentro da finalidade publicada.

Foram preservados README, URLs fixadas, hashes e três MP3: 312.870 bytes no total. A gravação Cadu foi escolhida para o próximo controle por critério técnico prévio, depois do decode/QC e da concordância dos dois ASRs sobre sua transcrição candidata. O repositório não traz uma transcrição oficial ao lado da amostra; os ASRs não substituem escuta humana. O fornecedor identifica o material como pt_BR, sem isso garantir o estilo desejado pelo cliente.

A proposta de captação própria abaixo fica como alternativa posterior, especialmente para uma identidade feminina. Não bloqueia o controle público OHF em preparação. As limitações jurídicas gerais de CC0 não foram convertidas em uma proibição universal de usar dados publicados para TTS.

## O que a avaliação humana trouxe

A coordenação informou que o usuário percebe sotaque de Portugal nos áudios. Na comparação enviada, **amostra 2 = Qwen J** ficou próxima da naturalidade desejada, mas o início foi percebido como português de Portugal. **Amostra 4 = Chatterbox F** foi considerada razoável e ainda precisa melhorar. Este é um relato humano real recebido por intermédio da coordenação, não uma classificação automática de sotaque e não um aceite de qualidade final.

As transcrições favoráveis de J/F continuam sendo diagnósticos de conteúdo. O reconhecedor foi solicitado a transcrever português, sem distinguir pt-BR de pt-PT; acertar as palavras não resolve a queixa de sotaque. F0 e pausas também não são um classificador validado das variedades do português.

## Licença do arquivo e autorização da voz são evidências diferentes

CC0 permite usos comerciais sob direitos autorais, mas o próprio Creative Commons ressalva direitos de terceiros, inclusive privacidade e direitos sobre voz/imagem. CC BY 4.0 também avisa que pode não fornecer todas as permissões necessárias ao uso pretendido. A avaliação deve considerar a finalidade e os termos concretos do fornecedor, além da licença. Isso não exige um termo privado adicional quando a própria publicação autoriza a finalidade TTS desta experiência. A rota OHF descrita acima é distinta de usar aleatoriamente uma gravação de um corpus genérico de ASR. [CC0: direitos que permanecem](https://creativecommons.org/publicdomain/zero/1.0/), [CC BY 4.0: permissões adicionais](https://creativecommons.org/licenses/by/4.0/).

Separar no registro: licença da gravação, permissão para reproduzir a identidade vocal por TTS/clonagem, permissão de uso comercial das novas falas e licença do modelo que as produzirá. Um campo de metadados ou a disponibilidade de um player não substitui os demais documentos.

## Fontes primárias avaliadas

| Fonte | Evidência encontrada | Decisão nesta pesquisa |
| --- | --- | --- |
| **CML-TTS** | Os autores descrevem corpus derivado de MLS/LibriVox, com audiolivros de voluntários e licença CC BY 4.0. A categoria Portuguese não basta para garantir a variedade de cada locutor. [Autores/repositório](https://github.com/freds0/CML-TTS-Dataset), [paper](https://arxiv.org/abs/2306.10097) | Não selecionar uma identidade para clonagem comercial só com essa licença. Não foi encontrado termo individual específico nas fontes consultadas. Nenhum áudio baixado. |
| **MLS** | OpenSLR registra CC BY 4.0 e origem em audiolivros LibriVox. O corpus é de pesquisa de fala e inclui português. [Distribuição primária](https://www.openslr.org/94/) | Domínio público do livro e licença do corpus não demonstram autorização individual para novas falas comerciais com a mesma identidade. Não usar o rótulo Portuguese como prova de pt-BR. |
| **Common Voice** | Os termos publicam contribuições em CC0; o projeto tem foco em dados de fala/ASR. [Termos Common Voice](https://commonvoice.mozilla.org/dav/terms) | Não converter a doação ao corpus em consentimento específico de clonagem comercial. O recorte de idioma/sotaque e o registro de consentimento do uso pretendido ainda precisariam ser verificados. |
| **OHF/Nabu Casa — Cadu, Faber, Jeff** | O repositório oferece doações para TTS, marca os três como `pt_BR` e publica CC0. A Mozilla declara que a coleção OHF não impõe restrição comercial. [Fonte OHF](https://github.com/OHF-Voice/voice-datasets), [declaração Mozilla](https://community.mozilladatacollective.com/open-home-foundation-tts-datasets-on-mozilla-data-collective/) | A investigação posterior confirmou a rota pública GitHub para finalidade TTS e baixou três pequenas gravações. Cadu foi escolhido para o controle, sem exigir conta ou contrato privado novo. As fontes e o hash estão no pacote de evidência. |
| **Cadu 1.0 no MDC** | A página descreve locutor masculino pt-BR, CC0 e uso pretendido de treino/fine-tuning TTS. Também proíbe tentar identificar os locutores. O campo demográfico informa que idade/gênero não foram reportados; não inferir outros perfis a partir do nome. [Card do fornecedor OHF](https://mozilladatacollective.com/datasets/cmiuimd7e01fimf072njn3mbb) | Evidência explícita de finalidade TTS. Não é um par feminino/masculino pronto. O acesso MDC tem termos/conta próprios; a rota usada foi a publicação original GitHub. Não procurar identificar o doador. |
| **Neutral TTS Female Voice Corpus — UFRJ/Globo** | Corpus feminino pt-BR de estúdio. Os termos limitam uso a pesquisa não comercial e dizem que dublagem das vozes não está autorizada. [Página dos autores](https://gpa-smt-ufrj.github.io/sbrt2023/intro.html), [termos primários](https://gpa-smt-ufrj.github.io/sbrt2023/terms_of_use.txt) | Fora do caminho comercial proposto. Nenhum áudio baixado. |
| **Demos de modelo pt-BR, exemplo F5-TTS-pt-br** | O card declara pesos CC BY-NC 4.0 e oferece exemplos de áudio. [Card do autor](https://huggingface.co/firstpixel/F5-TTS-pt-br) | Demo oficial e licença dos pesos não são liberação do locutor da referência. Não usar áudio de demonstração para clonar sem autorização própria do asset. Esse checkpoint também não é candidato permissivo comercial nesta pesquisa. |
| **Kokoro `pf_dora`/`pm_alex`** | O card oficial lista presets de português brasileiro; código/pesos do componente do projeto têm licença Apache-2.0. [Vozes oficiais na revisão usada](https://huggingface.co/hexgrad/Kokoro-82M/raw/f3ff3571791e39611d31c381e3a41a3af07b4987/VOICES.md), [modelo](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md) | Os WAVs locais são síntese do preset, não uma gravação humana doada ao projeto. O nome do preset não identifica uma pessoa autorizante. O rótulo pt-BR não garante a percepção desejada em todo trecho. Não substituir por outra demo de procedência desconhecida. |

O MDC exige observar a licença específica do fornecedor e os termos adicionais de uso. Sua plataforma não garante por si a adequação jurídica de todo dataset. Essa é outra razão para preservar a documentação específica, em vez de usar apenas o selo CC0. [Termos do distribuidor](https://mozilladatacollective.com/terms/consumers).

### Opções de aquisição com escopo explícito

Há fornecedores que anunciam coleta pt-BR com consentimento específico. Isso é uma via para obter o documento necessário, não uma licença adquirida nesta pesquisa:

- **FutureBeeAI:** a página de TTS pt-BR informa vozes adultas femininas/masculinas nativas, consentimentos escritos arquivados e diz que coleta para voice cloning exige licenciamento separado. Essa separação é explícita; o pacote TTS genérico não deve ser assumido como licença de clonagem. [Fonte do fornecedor](https://www.futurebeeai.com/dataset/speech-dataset/tts-monolgue-portuguese-brazil).
- **DMH Voices:** o estúdio brasileiro anuncia material para voice cloning com consentimento e direitos de identidade vocal, vozes femininas/masculinas e licença comercial por contrato. São declarações do próprio fornecedor; não verifiquei contratos ou amostras licenciadas. [Fonte do estúdio](https://dmhvoices.com.br/).

Não houve contato, envio de texto/dados, pedido de orçamento, contratação ou download de áudio desses fornecedores. Não há preço ou prazo garantido por esta entrega. Para o piloto curto, um adulto nativo colaborador com autorização clara evita comprar um corpus de horas.

## Um caminho concreto para a próxima referência

Proposta de captação própria, sem exigir treinamento de modelo:

1. Selecionar um adulto nativo de pt-BR para cada perfil vocal necessário. A pessoa informa a variedade/região que deseja representar; o usuário ou avaliador nativo escuta e confirma se corresponde ao objetivo. Há múltiplos sotaques brasileiros válidos; não existe um único contorno de F0 que defina pt-BR.
2. Antes da clonagem, registrar autorização que mencione **síntese/clonagem da própria identidade vocal, criação de falas novas e uso comercial pelo projeto**, além de finalidade, escopo, prazo, condições de revogação/eliminação e eventuais terceiros que receberão o áudio. A pessoa precisa compreender o resultado pretendido. Não preencher esses campos por inferência a partir de CC0, de uma relação de trabalho ou de uma gravação já disponível.
3. Captar uma tomada de 20–30 s em ambiente silencioso, microfone estável, uma pessoa, sem música/reverberação/compressão forte. Preservar a gravação original e sua transcrição humana literal. Esse tamanho é proposta de captação; o trecho usado deve respeitar as exigências do modelo escolhido. O brief inclui uma frase natural sem saudação para testar o início independentemente do “Olá”.
4. Escolher um trecho curto contínuo, por exemplo 6–12 s se o modelo permitir, após a escuta. Registrar hash, início/fim, transformações, texto exato e identificador da autorização. Não alterar prosódia por pitch/speed/EQ para “fabricar” sotaque. Na síntese futura, manter o texto de controle e mudar apenas a referência; repetir seeds dentro de cada sistema.

O pacote privado `p06-sotaque-20261015/referencias/` contém um brief de gravação e uma ficha de proveniência **em branco**, não um termo assinado nem um asset pronto para clonagem. A autorização concreta e o áudio ainda não existem nesta entrega. Esta pesquisa entrega o caminho e os campos para verificá-los, sem declarar direitos de uma pessoa que não participou.

## Reanálise dos primeiros dois segundos de J/F

Foi usado somente o material já preservado: CSVs Praat e JSONs ASR da rodada anterior. Os hashes dos raws foram conferidos. Não foi importado MLX/PyTorch/Praat, não houve ASR novo e nenhum modelo de sotaque foi executado.

| Dado existente | J — Qwen, amostra 2 | F — Chatterbox, amostra 4 |
| --- | --- | --- |
| F0 mediana vozeada, 0–2 s | 184,0 Hz | 187,0 Hz |
| F0 p10–p90, 0–2 s | 123,0–268,2 Hz | 127,6–229,6 Hz |
| F0 mediana na janela fixa 0–0,45 s | 184,2 Hz | 187,5 Hz |
| Primeiro intervalo de baixa energia, limiar −35 dBFS | 0,475–0,905 s | 0,455–0,905 s |
| Fim aproximado de “Olá”, large / small-q4 | 0,36 / 0,30 s | 0,32 / 0,30 s |
| Início aproximado de “eu”, large / small-q4 | 0,92 / 0,78 s | 0,92 / 0,80 s |
| Fim aproximado de “Ana”, large | 1,68 s | 1,60 s |

**Indícios permitidos:** as hipóteses ASR situam uma saudação curta e o detector encontrou intervalos iniciais de baixa energia muito próximos nos dois arquivos. O large também situa a retomada em 0,92 s nos dois. A distribuição de F0 em J é mais ampla nos primeiros dois segundos nesta realização; as medianas iniciais são próximas. Esses fatos ajudam a localizar a escuta e comparar ritmo/contorno, sem ordenar a qualidade.

**Indícios que não temos:** fronteiras fonéticas validadas, formantes/vogais comparados a controles humanos equivalentes, análise articulatória ou classificação de sotaque calibrada. O Praat 6.1.38 usado antes estima F0 por autocorrelação clássica, com risco de erros de vozeamento/oitava; a configuração e a janela mudam os resultados. Uma sequência ASR correta é compatível com pronúncias distintas. Não é possível concluir pt-PT ou pt-BR desses números. [Limites da configuração de pitch](https://praat.org/manual/Intro_4_2__Configuring_the_pitch_contour.html).

A avaliação humana sobre sotaque permanece como a evidência dessa queixa. A próxima comparação deve pedir separadamente “soa brasileiro?”, naturalidade e inteligibilidade, com o mesmo texto e volume, sem mostrar o nome do modelo. Não usar F0 mais alto/baixo como solução presumida. Uma referência humana autorizada ou uma voz desenhada sem referência são experimentos diferentes; ambos precisam de escuta para confirmar sotaque.

## Artefatos e limites

O diretório privado preserva `J-F-inicio-2s.json`, dois CSVs de 0–2 s, metadados/cards textuais de fontes, URLs/datas/hashes, brief e ficha em branco. Foram baixados apenas metadados textuais dentro do limite da tarefa; nenhum corpus ou áudio humano. Fontes `main/master` podem mudar: os snapshots consultados têm hashes locais.

Nenhuma pessoa foi identificada a partir dos datasets. Nenhuma referência foi usada para clonagem, nenhuma inferência nova foi feita e nenhum ambiente foi recriado para esta pesquisa. A pesquisa não fornece um parecer jurídico nem transforma a documentação incompleta em consentimento presumido.
