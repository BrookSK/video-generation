# P06 — fontes e ensaios de naturalidade em pt-BR

Pesquisa em 15/10/2026. Este documento registra fontes e propostas de teste, sem aprovar modelo ou alterar produção. O usuário ouviu as opções Chatterbox A/B e ainda percebe voz robótica, com destaque para o “Olá” e a entonação das frases. Texto correto no ASR não resolve essa avaliação. O estado de execução e os vereditos ficam em [P06-QUALIDADE.md](../homologacao/P06-QUALIDADE.md).

A decisão proposta é testar duas rotas: **Chatterbox atual com uma ablação da referência** e **Qwen3-TTS Base no MLX, com a mesma referência original**. A primeira testa uma causa possível dentro da configuração atual. A segunda oferece um rival de implementação. Não há evidência local nesta pesquisa para ordenar a naturalidade dos modelos.

## Como as fontes foram avaliadas

Foram lidos repositórios dos autores, código dos loaders/geradores, model cards, licenças, exemplos e o paper Qwen3-TTS. O port MLX tem fonte primária própria, mantida por seus implementadores; não é o runtime oficial PyTorch da Qwen. As APIs públicas de GitHub/Hugging Face/PyPI foram usadas para conferir revisões e metadados, sem baixar pesos ou instalar pacotes. Nenhuma inferência foi executada nesta frente de levantamento. Os ensaios posteriores estão registrados em [P06-NATURALIDADE.md](P06-NATURALIDADE.md).

“Fato” abaixo significa algo verificável na fonte citada. Declarações de qualidade dos autores e amostras de demonstração são evidência de capacidade apresentada, sem equivaler a uma avaliação controlada das nossas falas. “Hipótese” e “proposta” indicam interpretação ou trabalho ainda necessário. Issues são relatos de seus autores, sem presumir confirmação do mantenedor.

## O que a implementação especializada mostra

**Chatterbox condiciona mais do que identidade vocal.** A demo oficial descreve transferência de características de voz e estilo a partir do áudio, oferece referência por idioma e recomenda que sua língua corresponda à saída. O README orienta CFG próximo de 0,3 para certas referências rápidas; suas dicas de expressividade estão identificadas como dicas do Chatterbox original. Não há justificativa para tratar uma combinação de sliders como receita universal para pt-BR. [Demo dos autores](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/multilingual_app.py), [README dos autores](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/README.md).

O código 0.1.7 usa os primeiros **seis segundos** para o condicionamento de fala do T3 e até **dez segundos** para a referência do decoder. O começo da referência tem, portanto, presença concreta no caminho da síntese. O código também normaliza pontuação e espaços; o contrato literal do produto não deve ser confundido com ausência de qualquer transformação interna do modelo. [Implementação fixada de `prepare_conditionals` e `generate`](https://github.com/resemble-ai/chatterbox/blob/59bc590b3cad826e5d5987745bf6844627a21ad5/src/chatterbox/mtl_tts.py).

No projeto, a referência sintética foi gerada com um texto que começa **“Olá! Esta é uma voz sintética de referência…”**, em `pf_dora`/`pm_alex`, velocidade 1,0. Isso é verificável em [voice_references.py](../../apps/worker/runtimes/voices/voice_references.py). A coincidência com a queixa sobre “Olá” sustenta a hipótese de transferência de prosódia, mas não demonstra causalidade. Cortar o cumprimento da referência, mantendo o cumprimento no texto de saída, é um teste mais informativo que continuar variando expressividade sem controle.

Há um relato histórico de pouco efeito do parâmetro `exaggeration` em Multilingual v1/v2, com análise da camada de emoção. É motivo para medir o efeito real, não para declarar o parâmetro quebrado no nosso checkpoint V3 pt-BR. Também há relatos antigos de sotaque português e nasalização inadequados no modelo multilíngue amplo; eles não substituem avaliação do finetune brasileiro atual. [Issue #355](https://github.com/resemble-ai/chatterbox/issues/355), [issue #281](https://github.com/resemble-ai/chatterbox/issues/281).

**Qwen separa clonagem e instrução de estilo em variantes distintas.** O exemplo oficial Base usa áudio e transcrição da referência. O modo que utiliza apenas o vetor de locutor dispensa transcrição, mas os autores alertam para possível perda de qualidade de clonagem. O reuso de um prompt de voz já preparado é uma implementação documentada para várias frases. [Exemplo Base dos autores](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/examples/test_model_12hz_base.py), [descrição oficial dos modos](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#voice-clone).

CustomVoice e VoiceDesign oferecem instruções de estilo; Base é a variante para clonar `pf_dora`. As vozes prontas documentadas são nativas de chinês, inglês, japonês e coreano, sem uma voz nativa brasileira declarada. O suporte a `Portuguese` não prova sotaque pt-BR. Usar uma referência brasileira no Base é uma hipótese a validar com audição. [Modelos e locutores oficiais](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#custom-voice-generate).

O paper Qwen3-TTS apresenta avaliações objetivas e subjetivas dos autores, treinamento multilíngue e síntese controlável. Não foi localizado ali um confronto que reproduza nossas falas, referências e avaliação humana pt-BR. Seus resultados e demos não sustentam uma promessa de superioridade neste projeto. [Qwen3-TTS Technical Report, v1, 22/01/2026](https://arxiv.org/abs/2601.15621v1).

## Português, licenças e viabilidade

| Modelo/implementação | Português verificável | Código | Pesos | Implicação para esta rodada |
|---|---|---|---|---|
| Chatterbox Multilingual 0.1.7 + finetune `pt-br` | Card específico para Brasil, idioma interno `pt`; já usado no projeto | [MIT](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/LICENSE) | [MIT no card pt-BR](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-pt-br) | Manter como controle; a rejeição atual não isola referência de modelo. |
| Qwen3-TTS 12Hz Base 0.6B/1.7B | Dez idiomas incluindo português; card não distingue Brasil/Portugal | [Apache-2.0](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/LICENSE) | [Apache-2.0, Base oficial](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) | Rival elegível para ensaio; pt-BR ainda precisa de escuta. |
| Port `mlx-audio` + Qwen Base convertido | Implementa o modelo Qwen; não adiciona garantia de sotaque | [MIT do port](https://github.com/Blaizzy/mlx-audio/blob/0fe0b9cd21d3a528892a4e2e2e98d8cd2b9b2d08/LICENSE) | [Apache-2.0 no snapshot MLX 1.7B bf16](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16) | Execução local em Apple Silicon; port e precisão precisam constar na proveniência. |
| Fun-CosyVoice3-0.5B-2512 | A lista oficial de nove idiomas **não inclui português** | [Apache-2.0 no repositório](https://github.com/QwenAudio/CosyVoice) | [Apache-2.0 no card](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) | Não apresentar como solução pt-BR pronta. Clonagem entre idiomas não demonstra suporte ao idioma ausente. |
| Kokoro-82M v1.0 | `lang_code='p'`, frontend `pt-br`, vozes `pf_dora`, `pm_alex`, `pm_santa` | [Apache-2.0](https://github.com/hexgrad/kokoro/blob/main/LICENSE) | [Apache-2.0](https://huggingface.co/hexgrad/Kokoro-82M) | Controle barato por síntese direta, sem a segunda etapa de clonagem. Não presumir que soará melhor. |
| XTTS-v2, alternativa conhecida | Card inclui português | [MPL-2.0](https://github.com/coqui-ai/TTS/blob/dev/LICENSE.txt) | [CPML 1.0.0, uso não comercial](https://huggingface.co/coqui/XTTS-v2/raw/main/LICENSE.txt) | Não é substituto comercial equivalente aos modelos permissivos acima sob essa licença de pesos. |

MIT e Apache-2.0 permitem exploração comercial sob suas condições de licença e avisos. A coluna de código não licencia automaticamente pesos ou referências. O XTTS demonstra por que é necessário separá-los. Este levantamento não substitui conferir as licenças das dependências distribuídas junto da aplicação.

O catálogo de vozes do Kokoro confirma explicitamente o recorte brasileiro. A cadeia atual sintetiza uma referência com Kokoro e depois a clona com Chatterbox; avaliar Kokoro diretamente pode ajudar a localizar em qual etapa aparece a entonação reprovada. Essa é uma inferência diagnóstica, não uma indicação de melhor produto. [Catálogo oficial de vozes](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

| Caminho | Hardware e execução offline | Memória/limite de evidência |
|---|---|---|
| Chatterbox atual | `from_local` carrega pesos locais; o projeto tem ensaios separados CUDA e MPS. MPS é PyTorch/Metal, não MLX. | Usar medições locais já registradas; não transportar pico CUDA para memória unificada. O timeout da VPS não é medida isolada da CPU. |
| Qwen oficial PyTorch | Exemplos dos autores usam CUDA/bfloat16 e FlashAttention 2. Aceitam diretório local previamente obtido. | Não foi confirmado um mínimo oficial de VRAM para a nossa fala/configuração. Não deduzir requisito total apenas dos parâmetros. [Quickstart oficial](https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md#environment-setup). |
| Qwen no MLX | Port voltado a Apple Silicon. Loader aceita caminho local; o snapshot precisa incluir tokenizer de texto e `speech_tokenizer/`, além dos pesos principais. | Snapshot 1.7B bf16 consultado: **4.544.212.739 bytes** no total; pesos principais 3.857.414.009 e codec 682.293.092 bytes. Isso é armazenamento, não pico de RAM. [Árvore da revisão](https://huggingface.co/api/models/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16/tree/a6eb4f68e4b056f1215157bb696209bc82a6db48?recursive=true). |
| CosyVoice3 | Exemplos carregam `model_dir` local; código desliga opções CUDA quando ela falta. Não foi confirmado um caminho MPS/MLX oficial nesta leitura. | Não há medição nossa nem suporte oficial pt-BR confirmado; não gastar esta rodada qualificando hardware para idioma ausente. [Loader](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/cosyvoice/cli/cosyvoice.py). |
| Kokoro direto | Biblioteca do autor com presets locais e frontend espeak; já existe ferramenta CPU offline no projeto. | 82M parâmetros não equivalem a um pico medido de RAM. Verificar frontend e pesos em cache antes de negar rede. [Implementação do autor](https://github.com/hexgrad/kokoro), [ferramenta local](../../apps/worker/runtimes/voices/voice_references.py). |

“Offline” significa carregar os artefatos completos em disco e executar sem rede. Um identificador do Hub pode disparar download; variáveis `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` são auxiliares, sem substituir um bloqueio de rede verificado. O card MLX registra conversão feita com `mlx-audio` 0.3.0; isso não determina a versão atual do runtime. [Card do convertido](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16).

## Opção executável 1 — ablação de referência no Chatterbox

**Hipótese:** parte do “Olá” exagerado e do ritmo de locução é transmitida pela referência sintética atual. Isso pode refutar a afirmação forte “o modelo, sozinho, é o culpado”. Não refuta todas as limitações do modelo.

Proposta de execução em área privada, sem editar receita ou referências de produção:

1. Preservar texto de saída completo, incluindo “Olá”, checkpoint pt-BR, D001/policy v3, device, seed e controles comuns. Usar uma configuração fixa, sem mudar CFG/temperatura/expressividade junto da referência.
2. Comparar a referência original com um recorte que comece depois do cumprimento, em limite de palavra e sem cortar fonema. Ouvir primeiro os dois inputs. Salvar os tempos exatos de corte e hash novo; nunca sobrescrever `pf_dora.wav` nem declarar seu hash antigo para o recorte.
3. Registrar que o recorte também muda duração e conteúdo do condicionamento. Se a hipótese ganhar apoio, confirmar depois com janelas de mesma duração com/sem cumprimento, antes de atribuir o efeito especificamente à palavra inicial.
4. Gerar somente os WAVs curtos. Comparar em ordem oculta o começo, a transição entre frases, as pausas e a sensação de locução. Preservar saída reprovada. Uma seed é uma primeira observação; confirmação exige repetir o par com outra seed comum.

**Resultado que enfraquece a hipótese:** o “Olá” e o ritmo reprovados permanecem semelhantes após mudar a referência. **Resultado que a sustenta:** o usuário prefere repetidamente a saída com referência recortada, mantendo a fala correta. Isso desloca a investigação para escolha/preparo da referência; não autoriza freeze automático. Se for necessária outra voz, uma referência humana autorizada e com estilo aprovado seria um teste posterior, distinto do recorte atual.

Não propor alongamento artificial, troca de pitch ou compressão para disfarçar a causa. Segmentar frase por frase também é uma variável nova: pode alterar contexto e criar emendas. Deve ser ensaio separado, mantendo o texto, em vez de um tratamento silencioso da fala literal.

## Opção executável 2 — Qwen3-TTS 1.7B Base bf16 no MLX

O coordenador selecionou o snapshot **`mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16`**, revisão **`a6eb4f68e4b056f1215157bb696209bc82a6db48`**, com `mlx-audio==0.5.9` em ambiente temporário. Usar bf16 evita misturar a troca de modelo com quantização de pesos. Esses dados descrevem o experimento planejado; esta pesquisa não executou nem aprovou sua qualidade. [Revisão consultada](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16/tree/a6eb4f68e4b056f1215157bb696209bc82a6db48), [release PyPI 0.5.9](https://pypi.org/project/mlx-audio/0.5.9/).

A API foi conferida no tag `v0.5.9`, não apenas no README de `main`: `load_model(Path(snapshot))` e `model.generate(text=..., lang_code="portuguese", ref_audio=..., ref_text=..., stream=False, ...)`. O `ref_text` precisa transcrever **a referência**, não a fala alvo. Conferir a assinatura da instalação antes da execução. [Loader do tag](https://github.com/Blaizzy/mlx-audio/blob/0fe0b9cd21d3a528892a4e2e2e98d8cd2b9b2d08/mlx_audio/tts/utils.py), [gerador do tag](https://github.com/Blaizzy/mlx-audio/blob/0fe0b9cd21d3a528892a4e2e2e98d8cd2b9b2d08/mlx_audio/tts/models/qwen3_tts/qwen3_tts.py).

Há diferenças de runtime que precisam ser explícitas: Base não oferece os presets nem o controle `instruct` das outras variantes; `speed` é documentado como não suportado diretamente. O caminho ICL com áudio/transcrição/encoder força **`repetition_penalty = max(valor, 1.5)`**. Não registrar 1,2 como penalidade efetiva nesse caminho, nem chamar um teste entre engines de comparação de um único slider. O codec local precisa ter encoder para ativar ICL. Esses detalhes vêm do código do port 0.5.9, não são parâmetros do Chatterbox.

O ensaio proposto usa o mesmo texto da Ana e o `pf_dora.wav` original; informa seed, sampler, teto de tokens, duração e memória medidos. Negar rede após preparar o snapshot completo. Verificar WAV e conclusão, ouvir antes de renderizar e manter o stress numérico como regressão separada. A guarda D001 do Chatterbox não se transfere automaticamente para a arquitetura Qwen: o wrapper precisa registrar como detecta término e recusar saída truncada pelo teto.

Para avaliar a troca de engine, comparar Qwen à saída Chatterbox com **a mesma referência original**, sem usar a melhor referência recortada apenas em um deles. Mesmo assim, arquitetura, codec, sampler e controles diferem; a conclusão é preferência pela configuração completa testada. Se ambos reproduzirem o mesmo tom robótico, isso dá mais motivo para testar referência/estilo antes de trocar outro modelo.

## Revisões e limites do levantamento

| Fonte | Versão/revisão consultada |
|---|---|
| Chatterbox usado pelo projeto | 0.1.7; código `59bc590b3cad826e5d5987745bf6844627a21ad5`; pt-BR do manifesto `b3952f18bc2eaa72b9bd7c17d2c4653bcad4770d`; D001/policy v3 locais preservados |
| Documentação atual Chatterbox | `5de7a54aa4e5e2baadb0182dde554908b48b85c2`, consultada em 15/10/2026; não aplicada ao runtime |
| Qwen3-TTS oficial | Código `022e286b98fbec7e1e916cb940cdf532cd9f488e`; Base 1.7B original `fd4b254389122332181a7c3db7f27e918eec64e3`; paper v1 |
| MLX-Audio | Tag v0.5.9 `0fe0b9cd21d3a528892a4e2e2e98d8cd2b9b2d08`; release de 13/10/2026; também lido `main` `dad2087f790dfe96b07d5aac1405db4b578b411f` |
| Qwen MLX escolhido | Base 1.7B bf16 `a6eb4f68e4b056f1215157bb696209bc82a6db48` |
| Opções MLX menores verificadas, sem seleção de qualidade | Base 0.6B bf16 `1eccf1cb2519b5a4e8a95b5f0544f3303568164f`; Base 1.7B 4bit `37e955a1deb861c088ae5f3a67043185f3d1a60c` |
| CosyVoice | Código `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`; pesos Fun-CosyVoice3-0.5B-2512 `29e01c4e8d000f4bcd70751be16fa94bf3d85a18` |
| Kokoro | Card v1.0, catálogo brasileiro e licença consultados em 15/10/2026; usar a revisão já fixada no manifesto local ao executar |

As revisões foram conferidas nas APIs públicas dos próprios repositórios/modelos. Links para metadados: [tag MLX](https://api.github.com/repos/Blaizzy/mlx-audio/git/ref/tags/v0.5.9), [PyPI 0.5.9](https://pypi.org/pypi/mlx-audio/0.5.9/json), [snapshot Qwen MLX](https://huggingface.co/api/models/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16/revision/a6eb4f68e4b056f1215157bb696209bc82a6db48), [CosyVoice3](https://huggingface.co/api/models/FunAudioLLM/Fun-CosyVoice3-0.5B-2512/revision/29e01c4e8d000f4bcd70751be16fa94bf3d85a18).

Não foi realizado teste auditivo novo, benchmark próprio ou confirmação de pt-BR nativo no Qwen. Não foi demonstrada equivalência entre o port MLX e PyTorch/CUDA. Não há ranking de naturalidade, garantia de leitura de números ou estimativa de pico de memória baseada somente no tamanho dos pesos. Os dois ensaios acima produzem evidência revisável para a próxima decisão; resultados devem ser registrados separadamente antes de qualquer alteração de produção.
