# P06 — retorno do cliente e viabilidade de videoaula

Análise de 20/10/2026. O cliente considera a geração competente, mas percebe o
resultado como rígido para treinamentos corporativos. Pergunta se a causa é o
prompt, a forma de geração ou uma limitação técnica. Encaminhou um roteiro de
videoaula para avaliar como ele se encaixa. Isso não registra aceite final das
quatro personas nem uma contratação de funcionalidades novas.

## Retorno posterior: prioridade é a naturalidade do vídeo puro

Nas mensagens de 20/10, entre 13:37 e 13:45, encaminhadas pelo usuário, o cliente
esclareceu que um fundo simples é suficiente. O problema relatado é rigidez nas
falas, expressões e interpretação. Considera as demais partes do roteiro
evoluções posteriores, a alinhar depois de concluir a naturalidade.

Portanto, a proposta de prova com demonstração e montagem, descrita na análise
inicial abaixo, **não é o próximo passo da correção atual**. A referência para
o trabalho passa a ser o vídeo puro do avatar. Voz, sincronia, movimentos e
expressões naturais continuam sendo critérios do escopo contratado. Não há
aceite novo nem autorização presumida para ampliar a aplicação.

O retorno literal está em `FEEDBACK-NATURALIDADE.json` no pacote privado. Em
resposta à consulta desta rodada, o usuário confirmou: **vale para o conjunto
dos quatro vídeos**. Não se deve restringir a correção à Ana ou considerar os
masculinos fora da avaliação. Ainda não há instantes específicos associados à
crítica. Ela não demonstra por si só se a causa está no TTS, no condicionamento
visual ou na combinação. As aprovações anteriores ficam preservadas como
histórico, sem invalidar o retorno atual sobre o conjunto.

A auditoria dos testes anteriores confirma que CFG de áudio e enquadramento
já foram comparados. Houve gesto e variação facial nas imagens examinadas, mas
isso não prova fluidez, intenção ou coerência com a fala em reprodução contínua.
Os registros da Ana I2 e das três provas deixam esse limite explícito. Repetir
o mesmo ajuste ou declarar melhora por SyncNet não resolveria essa lacuna.

A próxima comparação deve começar pela percepção da fala isolada e depois
do conjunto audiovisual, usando trechos identificados e os mesmos insumos.
Assim é possível preservar o que funciona e alterar uma direção de atuação
ou uma configuração por vez. A ausência de corte, trilha e zoom permite avaliar
a interpretação diretamente. A execução posterior desta correção, com inferência
nova e QA do vídeo puro, está em [P06 — naturalidade em 20/10](P06-NATURALIDADE-20261020.md).

`REVISAO-NATURALIDADE.html`, no pacote privado, prepara esse contraste com os
quatro MP4s enviados: cada controle de áudio e de vídeo aponta para o mesmo
arquivo, sem ressíntese, extração ou reencode. Os hashes foram conferidos contra
o manifesto da entrega. A página apenas organiza a avaliação das mídias
existentes; não apresenta melhora já produzida. O Astra revisou esta prioridade
em `ASTRA-NATURALIDADE-PRIORIDADE.md`, preservando o parecer anterior.

## Material e verificação

O pacote recebido contém três OGGs, de 21,82 s, 60,90 s e 14,92 s, e um PDF de
duas páginas. As transcrições foram produzidas localmente com Whisper
large-v3-turbo/MLX, sem texto esperado no prompt e usando o modelo já em cache.
Não houve audição direta pelo agente. As duas páginas do PDF foram renderizadas
e inspecionadas; sua extração textual foi confrontada com a apresentação visual.

Fontes, transcrições completas, hashes, storyboard de dados e verificações ficam
fora do Git, em
`/Users/felipebianchini/Developer/video-generation-amostras/p06-retorno-cliente-20261020/`.
`FONTES.json` vincula as quatro entradas ao ZIP recebido. Os três resultados ASR
vinculam a transcrição ao SHA-256 do OGG correspondente. `STORYBOARD.json`
preserva as seis falas sem reescrita; não é um request de inferência.

O primeiro áudio pede centralizar as comunicações e reenviar os vídeos no grupo.
O segundo explica o uso em treinamento e pergunta sobre a rigidez. O terceiro
apresenta o roteiro como exemplo para análise. O agente não enviou mensagens ou
arquivos ao grupo.

## O que o roteiro pede

Vídeo horizontal 1920×1080, até 60 s, narração em português brasileiro, professor
com aparência de engenheiro, identidade consistente e seis cenas:

| Intervalo alvo | Conteúdo visual | Palavras na fala |
|---|---|---:|
| 0–8 s | Professor apresenta o assunto | 18 |
| 8–19 s | Projeto e avaliação técnica | 22 |
| 19–29 s | Identificação e isolamento de instalações | 20 |
| 29–39 s | Proteção do ambiente e circulação | 19 |
| 39–51 s | EPIs, ferramentas, riscos e retirada de entulho | 25 |
| 51–60 s | Professor e checklist final | 21 |

Também pede demonstrações realistas correspondentes às falas, legendas, títulos,
trilha discreta, transições e mensagem final. O conteúdo técnico e a representação
dos procedimentos precisam de revisão pelo responsável habilitado do cliente;
uma imagem plausível não comprova um procedimento correto.

São 125 palavras e 822 caracteres ao unir as seis falas com espaços. A contagem
não comprova duração natural. A narração real deve ser medida por cena e no
conjunto antes de gerar os vídeos. Não acelerar artificialmente ou cortar falas
para cumprir a minutagem. Se a leitura não couber, apresentar a divergência antes
de reescrever o texto.

Os tempos reservam 17 s ao professor e 43 s às demonstrações: 28,3%/71,7%. A
proporção 35%/65% aparece como sugestão no PDF, não coincide com esses tempos.
Para uma prova inicial, a sequência e os intervalos explícitos são a referência
de preparo; a eventual redistribuição precisa ficar declarada. Não tratar essa
escolha de preparo como aprovação do cliente.

## Diagnóstico: prompt, modelo e montagem

Há três fatores diferentes:

1. **Atuação do professor.** Imagem, enquadramento, referência vocal e prompt
   influenciam o resultado. Os ensaios de [dinâmica](P06-DINAMICA.md) já
   demonstraram gestos reconhecíveis após mostrar braços/mãos e mudar a direção
   visual. A amostragem de quadros e o SyncNet não certificam naturalidade.
2. **Limite do condicionamento.** InfiniteTalk recebe áudio e imagem ou vídeo.
   O prompt descreve a atuação, mas o contrato atual não contém uma timeline de
   seis ações independentes. Não há evidência local de controle exato de mãos,
   ferramentas e procedimentos apenas por um prompt extenso.
3. **Formato da aula.** Alternar o professor com demonstrações, títulos,
   legendas, checklist e música requer montagem. Essa capacidade está ausente
   no fluxo atual; trocar o texto do prompt não a implementa.

Evidências no código:

- `avatar_stage.py`, `build_input_json`: um `prompt`, uma entrada `cond_video`
  derivada de imagem e uma entrada de áudio.
- `pilot.py`: cada amostra declara imagem, fundo, voz e fala; não descreve cenas
  internas, mídia de apoio ou trilha.
- `finalize.py`, `build_finalize_args`: ajusta FPS, escala, margem e recorte,
  e mapeia o vídeo com o áudio. Não monta cenas, legendas ou música.
- `NewVideo.tsx` e `jobs.py`: o campo recebe a fala literal; não existe parser
  que transforme as instruções visuais do PDF em uma videoaula.

As amostras externas mais recentes usam Qwen3-TTS com referência humana
brasileira e InfiniteTalk/LightX2V, com finalização própria. A receita global
`RECIPE-v1.json` ainda é draft, com Chatterbox e limites de 40 s/600 caracteres/
1000 quadros. Não atribuir a ela os parâmetros ou a voz das amostras aprovadas.
O roteiro completo supera o limite textual desse draft. Os 40 s são configuração
atual, não um limite universal do InfiniteTalk. O suporte oficial a streaming não
comprova a homologação local de 60 s.

## Caminho técnico recomendado

A documentação da [Synthesia sobre roteiro por cena](https://help.synthesia.io/en/articles/13214011-how-do-i-create-a-script-in-synthesia)
separa cada trecho falado e suas pausas. O [guia de treinamento da equipe](https://www.synthesia.io/post/training-videos)
organiza objetivo, roteiro, elementos visuais e revisão. São referências de
processo de um fornecedor, não benchmarks que aprovam nossa implementação nem
uma recomendação para contratar SaaS.

A proposta mínima é preparar uma prova de 15–20 s que contenha uma apresentação
do professor e a passagem para a primeira demonstração. Usar a mensagem do
roteiro, a mesma voz selecionada e um plano horizontal próprio. Avaliar esse
conjunto antes de renderizar a aula inteira.

O Astra fez revisão independente dos materiais e do código, com pesquisa em
fontes primárias. Seu parecer está em `ASTRA-PARECER.md` no pacote privado.
Convergiu com o diagnóstico e recomendou começar com áudio cronometrado e um
animatic local antes da inferência visual. O animatic pode marcar materiais
ausentes, mas não satisfaz o critério de demonstrações realistas. Ainda não há
demonstrações de obra aprovadas identificadas no projeto. O [guia da TechSmith](https://assets.techsmith.com/docs/How_to_Create_Employee_Training_Videos.pdf),
consultado pelo revisor, também separa roteiro, storyboard, materiais e edição.

Para a aula completa:

1. Preparar a narração das seis cenas, com a mesma referência vocal e configuração.
   Medir tempo e conferir palavras e junções; áudio de dez segundos aprovado não
   aprova automaticamente novas falas.
2. Gerar o professor onde aparece. Manter identidade, roupa, cenário e direção
   visual coerentes. Não renderizar um minuto inteiro de avatar para depois
   descartar quase todo esse vídeo sob as demonstrações.
3. Selecionar demonstrações próprias ou licenciadas e conferir sua aderência.
   Cenas sintéticas seriam candidatas sujeitas à inspeção técnica; não tratá-las
   como prova automática de uma prática segura. Movimento de uma foto ou esquema
   não equivale à demonstração realista de um procedimento.
4. Montar a sequência com a narração preservada; acrescentar legendas derivadas
   da fala correta, títulos, checklist, aviso técnico e trilha licenciada.
   O [FFmpeg](https://ffmpeg.org/ffmpeg-filters.html) oferece os mecanismos de
   composição, legendas e mixagem, mas ainda falta ligá-los a esse fluxo.
   Antes da implementação, conferir os filtros disponíveis no runtime real;
   `subtitles` depende de uma compilação com libass.
5. Conferir o arquivo real: tempo até 60 s, sequência completa, 16:9, decodificação,
   fala integral, sincronia onde há rosto, legibilidade, inteligibilidade e
   correspondência entre imagens e explicação. Solicitar avaliação do cliente.

Preservar os materiais aprovados e registrar a mudança de cada prova. Não
prometer qualidade final com base apenas em demos dos autores, score ou exit 0.
As [interfaces oficiais do InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk)
e de [clonagem do Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) sustentam o
reaproveitamento desses componentes, sem comprovar a nova montagem.

## Fronteira de implementação e situação

A qualidade de voz, movimento, sincronia e formato do apresentador continua
sujeita às correções e à homologação já previstas. A necessidade de montagem de
videoaulas é distinta. O escopo selado trata a entrada como fala literal; a
aplicação não oferece editor de cenas. Uma demonstração montada manualmente e
uma funcionalidade automática disponível no painel/API são entregas diferentes.

O roteiro recebido não deve ser interpretado como aprovação de um novo escopo,
de prazo ou de custo. Também não torna toda crítica de rigidez um pedido extra.
A análise prepara a decisão sobre o resultado esperado e uma prova pequena;
não altera a receita, os contratos ou a matriz de homologação existente.

Na análise inicial houve leitura, transcrição, análise do código e pesquisa,
sem geração de vídeo ou operação na Verda. Depois da instrução do usuário para
executar os testes, começou a rodada de [naturalidade do vídeo puro](P06-NATURALIDADE-20261020.md).
Os quatro arquivos enviados anteriormente permanecem preservados. Essa execução
não implementa a montagem da videoaula descrita no roteiro.
