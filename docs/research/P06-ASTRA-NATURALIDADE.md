# P06 — revisão crítica de naturalidade

Revisão em 15/10/2026 por subagente Astra, reasoning medium. Escopo: análise do sistema e fontes primárias. Sem inferência, alteração de runtime ou audição pelo agente. O último veredito humano sobre VoiceDesign L/M foi **“Ainda nenhuma atende”**. Naquele momento ainda não havia voz aprovada.

Atualização posterior: o usuário aprovou explicitamente a referência humana Cadu e a Voz D/N em pronúncia brasileira, entonação e naturalidade. A análise abaixo registra o estado anterior ao ensaio. O [registro de aprovação](../homologacao/P06-VOZ-APROVADA.md) preserva o WAV ouvido e os limites desse aceite. O Astra confirmou depois o próximo passo: O (mesmo texto, outra seed) e P (outra frase, seed original), sem trocar a voz aprovada.

## Parecer

A investigação já demonstrou integridade de arquivos e alguns comportamentos técnicos. Ainda não demonstrou uma receita de fala aceitável nem de atuação humana convincente. O risco agora é otimizar uma explicação confortável — sotaque, referência ou scheduler — sem provar que ela explica a reprovação.

A próxima ação com melhor relação entre custo e informação é **um ensaio curto de Qwen Base com referência humana brasileira, mantendo o restante da receita**, acompanhado da própria gravação humana para escuta. Isso testa uma entrada ainda ausente do conjunto local. Não autoriza concluir que Kokoro é a causa. A mudança também troca identidade, estilo, duração e conteúdo da referência.

O segundo problema é independente: o plano corporal solicitado é incompatível com parte das entradas atuais. Uma foto com ombros cortados e uma instrução contra gestos reduzem a informação disponível. Contudo, ampliar o plano ou permitir gestos não garante atuação natural: gesto plausível, gesto sincronizado e gesto apropriado ao sentido são critérios diferentes.

## O que equipes especializadas realmente implementam

As fontes abaixo foram consultadas em 15/10/2026. São documentos dos autores ou implementadores. Demos mostram capacidade selecionada; não fornecem taxa de acerto no nosso domínio. A convergência de práticas entre equipes não equivale a replicação controlada de resultados.

| Prática observada | Fontes primárias independentes | Consequência para este projeto |
|---|---|---|
| Clonagem usa uma referência acústica e sua transcrição; descrição de voz é outra modalidade. | [Qwen3-TTS, Voice Clone e Voice Design](https://github.com/QwenLM/Qwen3-TTS); [F5-TTS, CLI e API de inferência](https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/infer/README.md). | Trocar adjetivos não substitui testar um alvo acústico adequado. A existência desse padrão não prova que uma referência específica será boa em pt-BR. |
| A preparação do texto e os limites de segmentos fazem parte da receita. | [F5-TTS, regras de pontuação e duração](https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/infer/README.md); [CosyVoice, exemplo zero-shot e nota sobre text_frontend](https://github.com/FunAudioLLM/CosyVoice). | Uma comparação entre motores precisa registrar o texto efetivamente recebido. Não importar limites de duração ou parâmetros de um modelo para outro. No F5, a orientação sobre referência curta é específica daquela implementação. |
| A atuação de entrada é um controle concreto de movimento. | [InfiniteTalk, preservação de movimento no vídeo de origem](https://meigen-ai.github.io/InfiniteTalk/); [Runway, guia de Act-Two](https://help.runwayml.com/hc/en-us/articles/42311337895827-Performance-Capture-with-Act-Two). | Uma demo com atuação filmada não prova que uma foto estática com áudio produzirá o mesmo corpo. Comparar modalidades equivalentes. |
| Sincronia labial é só uma dimensão da animação humana. | [VASA-1, trabalho da Microsoft](https://arxiv.org/abs/2404.10667); [InfiniteTalk, artigo dos autores](https://arxiv.org/abs/2508.14033). | Validar também cabeça, expressão, corpo e consistência temporal. Um offset zero não resolve essas dimensões. |

No Act-Two, a documentação especifica mãos visíveis, pose inicial compatível e movimento moderado para transferência de gestos. Também distingue imagem de personagem e vídeo de personagem: os controles não são intercambiáveis. Isso oferece uma referência de método, sem recomendar compra ou migração para esse serviço.

O F5-TTS documenta referência com transcrição, cuidado com cortes no meio da palavra, pontuação e geração por segmentos. O CosyVoice registra que reproduzir suas demos pode exigir desativar seu frontend de texto. São exemplos de equipes tornando a receita explícita. Não são evidência de superioridade desses modelos em português brasileiro.

O Qwen documenta clonagem Base, VoiceDesign e o fluxo de desenhar uma voz e depois cloná-la. A tentativa local de VoiceDesign reprovada impede tratar a etapa de desenho como já resolvida. Reutilizar uma saída reprovada como nova referência apenas propagaria um alvo não aceito.

## Hipóteses que continuam abertas

| Alegação | O que a evidência atual permite | O que falta separar |
|---|---|---|
| “É o modelo.” | Duas famílias e várias receitas falharam no aceite. | Isso não esgota referências, estilos nem implementações. Qwen local usa port MLX; falha local não identifica sozinha limite dos pesos oficiais. |
| “É a referência sintética.” | E/F/G/J compartilham origem Kokoro; falta controle humano. | Cortar 0,53 s altera vários atributos. Uma referência humana de outro locutor também altera vários. Testar o pacote antes de atribuir causa. |
| “É pt-PT.” | O usuário percebeu traços de Portugal, sobretudo no início. | Isso é evidência perceptiva válida, mas não prova troca de idioma no código. Pronúncia, entonação, ritmo e timbre podem contribuir para a mesma descrição. |
| “É o texto.” | A queixa menciona saudação e entonação; o texto é parte do condicionamento. | Primeiro manter o texto fixo. Depois usar outra frase curta para testar generalização. Reescrever tudo junto com a referência eliminaria a comparação. |
| “É o enquadramento.” | Há limitação observável na foto e no prompt. | Não está demonstrado quanto da rigidez vem disso, do gerador, do áudio ou da aceleração. |
| “É o scheduler.” | Existe diferença entre configuração atual e um exemplo oficial de outra receita. | O exemplo FusionX de oito passos não estabelece ótimo LightX2V de quatro. O par preparado testa um parâmetro, não naturalidade inteira. |
| “SyncNet resolveu.” | A cópia compensada zerou o offset nas janelas medidas e preservou o áudio. | Não prova alinhamento fonema a fonema, ausência de artefato, emoção ou movimento corporal adequado. |
| “Falta resolução.” | Houve ampliação de 448×832 para 1080×1920. | Mais pixels podem melhorar detalhe; não há evidência de que corrijam a atuação ou voz. |

## Próximo ensaio: uma rodada, com decisão explícita

**Entrada:** uma gravação humana pt-BR do conjunto [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets), após a conferência em andamento de origem, transcrição e arquivo. O repositório declara doações para TTS e CC0; suas gravações não devem ser confundidas com saídas de modelos Piper. A revisão conferida pela frente de fontes é `8ed76fa9001fafc77db32bd682f434938c679e3e`. Selecionar Cadu por critério técnico prévio é aceitável para triagem; ASR coerente e ausência de clipping não garantem estilo adequado. Fixar arquivo e hash. Não escolher entre dezenas de vozes após ouvir apenas os resultados bons.

**Geração:** uma saída Qwen Base com o texto de H, seed, pesos, sampler e implementação mantidos. H usa a referência masculina sintética `pm_alex`; é o controle mais próximo para o ensaio masculino Cadu. Trocar somente o pacote referência + transcrição. Sem mudar pontuação, velocidade, instrução ou pós-processamento no mesmo ensaio. Se a referência tiver outra identidade vocal, registrar isso como variável concomitante.

**Comparação:** mostrar a saída nova e H, com rótulos neutros e ganho constante, após conferir equivalência nos manifests. J permanece referência histórica de preferência do usuário, mas não entra como par causal com outra identidade e possivelmente outro texto. Exibir também o áudio humano original em bloco identificado. Este último serve para julgar o alvo, não para uma disputa cega entre textos diferentes.

**Veredito humano curto:** (a) a própria referência tem pronúncia/ritmo desejados? (b) a saída atende, melhora mas não atende, empata ou piora? (c) o defeito está no início, no restante ou em ambos? Manter “nenhuma atende”. ASR verifica palavras e números; não decide sotaque. Não converter F0, LUFS ou duração em nota de naturalidade.

| Resultado | Decisão e hipótese enfraquecida |
|---|---|
| Referência humana atende e saída melhora claramente. | O pacote de referência influencia este caso. Enfraquece a afirmação de que esta implementação nunca consegue melhorar. Ainda não prova que a síntese da referência antiga era a causa. |
| Referência humana atende, saída continua reprovada. | Enfraquece a suficiência de trocar apenas essa referência. Encerrar a busca por adjetivos/recortes nesta rodada. A próxima decisão deve distinguir implementação/modelo com controle equivalente, não repetir ajustes sem hipótese. |
| Referência humana já não atende. | O alvo acústico foi mal escolhido para o produto. Não usar sua saída para condenar o modelo. Selecionar outra referência por critério explícito, sem geração em massa. |
| Saída melhora no sotaque, mas segue artificial. | Sotaque e naturalidade são critérios distintos. Registrar o ganho parcial e o defeito restante; não promover para produção. |
| Saída atende na frase de triagem. | Fazer apenas confirmação pequena: outra frase relevante e uma repetição com outra seed. Preservar falhas. Uma amostra aprovada não estabelece robustez. |

**Regra de parada proposta:** uma nova referência nesta rodada; no máximo uma confirmação se houver ganho claro. Sem ganho, mudar a pergunta experimental. A referência humana masculina pode validar uma rota, mas não cumpre sozinha eventual requisito de voz feminina.

## Como retomar o vídeo sem confundir causas

A voz deve passar pelo aceite de áudio antes de consumir render caro para avaliá-la no avatar. Para estudar movimento separadamente, pode-se usar áudio humano autorizado como controle, identificado como tal; isso não constitui entrega TTS aprovada.

Com GPU disponível, manter o par de scheduler preparado como diagnóstico estreito. Se ele não der ganho perceptivo, não continuar varrendo parâmetros por inércia. O próximo contraste relevante é entrada e direção de atuação: primeiro remover a proibição de gestos mantendo a imagem; depois comparar enquadramento adequado da mesma identidade. Uma modalidade com vídeo de atuação é uma alternativa arquitetural posterior, não uma correção garantida por prompt.

Revisar três apresentações do mesmo trecho ajuda a localizar a reprovação: áudio sozinho, vídeo sem som e vídeo com som. O julgamento final continua audiovisual. Avaliar também estabilidade do cenário, coerência de luz/identidade e gestos durante pausas; “mover mais” não é critério de sucesso.

## Limite desta conclusão

Não houve audição pelo agente, benchmark novo nem demonstração de taxa de sucesso. A evidência local vem dos registros e do feedback humano; as fontes externas mostram práticas e capacidades publicadas. O avanço recomendado é reduzir uma incerteza concreta com uma entrada humana rastreável, preservando a possibilidade de o resultado refutar a própria recomendação. A P06 continua incompleta.
