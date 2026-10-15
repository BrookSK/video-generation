# P06 — revisão de qualidade e próxima rodada

Registro de 15/10/2026. **P06/T06 continua incompleta.** O pacote de calibração
prepara comparações; não comprova melhora de voz, movimento ou cenário sem novas
inferências e avaliação das saídas. A receita de produção permanece `draft`.

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
É preciso construir/publicar uma nova imagem identificada para usar essa opção
na GPU. A imagem do preview anterior não contém as novas flags.

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
Nesta retomada, o console abriu deslogado e não foi possível consultar billing
atual. O alias SSH antigo não serve como confirmação de instância atual.
Nenhum novo recurso pago foi criado e nenhuma recarga foi feita.

A consulta anônima/com as credenciais locais disponíveis ao manifesto do digest
anterior no registro retornou `no such manifest`. Isso não diferencia imagem
privada/inacessível de referência removida. Não há imagem local do worker para
reutilizar. A próxima janela também precisa restabelecer acesso ao registro e
publicar/conferir a imagem do código atual; não reutilizar o digest antigo como se
incluísse as novas flags.

Com o desempenho medido e os preços históricos, oito execuções de 30 s custariam
cerca de US$ 6,83; incluindo uma de 60 s, cerca de US$ 8,54. Essa projeção não
inclui 720p, preparação, espera por clonagem, repetições ou a matriz final. A
reserva de armazenamento vem além disso. Preço, capacidade e saldo devem ser
conferidos antes de contratar a próxima janela.

Mensagem para o cliente:

> Precisamos repor os créditos da Verda para continuar os testes de qualidade dos
> vídeos. O saldo registrado na última rodada já não cobria uma nova geração.
> Pode adicionar saldo e avisar quando estiver disponível? Vamos validar primeiro
> as falas e depois os movimentos e cenários, para usar melhor os créditos.

## Verificação desta alteração

- Suíte local do worker: **282 testes passaram; um teste GPU não selecionado**.
- Ruff do worker e do preparador: sem erros. Formatação dos três arquivos Python
  alterados/novos: sem diferenças pendentes.
- Nova bateria de 15 casos verifica reuso dos bytes, ausência de ressíntese,
  rejeições no preflight e preservação do fluxo antigo. A reprodução anterior à
  implementação falhou como esperado. Revisão independente: nenhum finding aberto.
- Pacote privado preparado: três receitas e quinze filas válidas, hashes
  conferidos e stress numérico anterior preservado byte a byte.
- Não houve nova síntese Chatterbox, inferência InfiniteTalk, build/publicação de
  imagem ou aprovação de qualidade nesta rodada. As novas falas e os novos
  parâmetros ainda precisam passar pelos testes reais.
