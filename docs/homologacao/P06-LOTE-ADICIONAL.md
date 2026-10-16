# P06 — três novos pares de avatar e voz

Em 16/10/2026, o usuário informou que o cliente aprovou o vídeo masculino anterior e combinou mais um avatar masculino e dois femininos, com uma nova voz masculina e duas novas vozes femininas. Esta rodada prepara esses **três novos pares**, preservando os arquivos anteriores. O relato não identifica um SHA específico entre as variantes do homem anterior; não foi atribuída aprovação automática a todas elas.

O aceite dos novos pares e a conclusão integral do projeto ainda estão pendentes. A receita parte das lições documentadas na [voz D](P06-VOZ-APROVADA.md) e no [ensaio de gestos e zoom](P06-DINAMICA.md).

## Entrega local preparada

Pacote privado fora do Git: `video-generation-amostras/p06-novos-avatares-20261016/`. Página conjunta `revisao.html`: três retratos, três áudios e a voz D para comparação. Há links para baixar os MP3s e as imagens. Os 14 alvos locais foram conferidos. Não foi realizado playback do HTML pelo agente.

Os nomes Rafael, Ana e Marina são nomes de demonstração para as novas combinações. O texto mantém a mensagem aprovada e troca a apresentação: “Olá, eu sou o Rafael/a Ana/a Marina. Uma boa mensagem aproxima pessoas. Vamos apresentar sua ideia com calma, clareza e um jeito natural de conversar.” Os requests de voz contêm cada versão exata, com artigo e nome correspondentes.

| Par | Retrato PNG, SHA-256 | WAV de escuta para o avatar, SHA-256 | Duração / quadros previstos a 25 fps |
|---|---|---|---|
| Rafael — `homem-02` | `9b49e658e8d7cc32396598308cdd66f21d245656cb722c98720a0f23459ed4f8` | `4f138bd55e7489b0c64e2494cfb62fadbb6739c351f94861a6fd1882f1ddbd50` | 9,92 s / 248 |
| Ana — `mulher-01` | `d08173a22656ef15bd39266fa37caa89d0d34fede965c9e2631e7d9a7da25d13` | `dda666229207cd5dd10ea23358f58e0a7651e24ff42c0e001b2244f4bbe6ed7a` | 10,00 s / 250 |
| Marina — `mulher-02` | `373a474d4e0590d1634e84dc2dbd441f148bbdb2dfea1bcd773eeb1068a6a541` | `2b8951530af23b4dda766233e6f235d940c024b21b2191dc8e5c238511d2fff0` | 9,76 s / 244 |

As contagens são previsões para o gerador, não medições de vídeos novos. Nenhum MP4 novo deste lote foi gerado até este registro.

## Imagens e preparo

Três novas identidades adultas virtuais foram geradas pela ferramenta integrada `image_gen`. Os PNGs finais têm 941×1672 pixels, RGB. Escritório claro, plano até as coxas, mãos separadas abaixo do rosto, ambos os punhos, cotovelos e antebraços completos. A coordenação inspecionou os três originais e a grade das entradas preparadas. A inspeção estática não comprova anatomia ou estabilidade temporal na animação.

Rafael e Marina têm cerca de 9% de margem acima da cabeça; Ana tem cerca de 15%. A variante de Ana com mais margem foi escolhida para preservar espaço para movimento e zoom. As alternativas e prompts estão em `assets/`. Nenhuma imagem do homem aprovado foi sobrescrita.

O preparo local usa a mesma geometria do ensaio de gestos: `ImageOps.fit` central com Lanczos para 1092×2028, canvas final 1080×1920 e offset (6,54), bucket 448×832. A área retida supera 90%; mãos e cabeça continuam no quadro nas entradas vistas. Os inputs de cada par ficam em `renders/<id>/in/`, com SHA256SUMS e proteção contra escrita. Os WAVs foram copiados byte a byte das candidatas de escuta. O script `execution/prepare-pairs.py` não acessa rede nem lança inferência.

## Vozes e verificações

Foi preservada a receita aceita em D: Qwen3-TTS Base 1.7B MLX bf16, revisão `a6eb4f68e4b056f1215157bb696209bc82a6db48`, MLX-Audio 0.5.9, seed 20261015, temperatura 0,9, top-p 1, top-k 50, repetition penalty 1,5 e limite de 512 tokens. O ambiente foi reconstruído com Python 3.12.13 e freeze idêntico, somente por cache offline. Treze arquivos do modelo foram conferidos por SHA. Inferências e ASRs rodaram localmente, em sequência e com rede bloqueada, sem Verda ou outra API paga de voz.

Rafael usa referência humana Faber/OHF `pt_BR`, CC0. Ana e Marina usam dois clipes humanos distintos de [FLEURS, configuração `pt_br`](https://huggingface.co/datasets/google/fleurs), com gênero `FEMALE` e transcrição primária. A licença declarada é CC-BY-4.0; atribuição, revisão, IDs, transcrições e alterações estão em `voices/CREDITOS.md`. FLEURS não expõe `speaker_id` nesses clipes: não foi afirmado que são duas pessoas reais distintas.

As três sínteses terminaram com EOS real. WAVs PCM16 mono/24 kHz, sem clipping. As cópias de escuta receberam apenas ganho constante para −23,5 LUFS: Rafael +0,33 dB; Ana −0,33 dB; Marina +18,42 dB. Não houve corte, denoise, limiter, alteração de pitch ou tempo. Os MP3s de WhatsApp decodificam com as durações esperadas, sem clipping. Os quatro WAVs do pacote D aprovado continuam com os hashes anteriores.

O ganho maior de Marina não prova distorção: o pico final é −4,65 dBTP. Pode tornar fundo e respirações mais perceptíveis; essa candidata merece prioridade de escuta. Whisper large-v3-turbo corresponde à mensagem completa nas três. Small-q4 corresponde Rafael, mas diverge em “aproxima pessoas” nas duas femininas. A divergência pede audição e não foi tratada como prova de erro de fala ou justificativa de ressíntese automática.

Similaridades descritivas do speaker encoder Qwen não têm threshold calibrado e não certificam identidade, diferença perceptual de timbre, sotaque ou naturalidade. A avaliação direta deve comparar Rafael/D e Ana/Marina, desde a saudação até o fim. **As vozes novas ainda não têm aceite humano.** Não houve audição pelo agente.

Os limites anteriores continuam: watermark Perth nulo, sem alegar C7 satisfeito, integração CUDA de produção ou homologação integral do Qwen no worker. O TTS experimental local e a preparação dos três pares não alteram o worker de produção.

## Próximos renders e bloqueio real

Perfil preparado: mesmo digest `cad3a59ea8afb4197179a02ce6702a48bb9bf8f3f79acb586645291b53c632b4`, InfiniteTalk bf16 A100, quatro passos, seed 42, text CFG 1/audio CFG 2. Prompt de gesto moderado, mãos abaixo do rosto e câmera fixa, adequado ao gênero visual do avatar. Zoom será uma variante de finalização. Cada render precisa de nova medição de sincronia, crop facial geométrico revisto antes dos scores e controles de ±200 ms. Não copiar +80 ms ou +120 ms das amostras anteriores.

O antigo IP `95.133.252.19` apresentou chave SSH diferente em 16/10 às 19:35 UTC. A checagem estrita recusou a conexão. Nenhum comando de trabalho chegou ao host, e o pin original não foi substituído. Após o usuário concluir o login, o console autenticado confirmou que não há instâncias nem volumes ativos. O audit log da instância anterior registra exclusão em **16/10/2026 às 03:50:08 UTC**, com `discontinue_reason: due_to_zero_balance`. Essa evidência confirma encerramento por saldo zerado; não foi usado o IP antigo para retomar trabalho.

O console foi acessado pela extensão do **Google Chrome normal**, sem expor credenciais. **O usuário concluiu o MFA e o login está resolvido.** O projeto correto mostra **US$ 0,27**, uso atual **US$ 0,00/h** e cinco volumes na lixeira. O bloqueio atual é saldo insuficiente. A tela de recarga exige **US$ 20 ou mais**; a aba ficou aberta para o usuário, sem submissão de pagamento ou alteração da recarga automática.

O volume original `OS-fHuXBon4` e o disco `p06-avatar-d-fresh-20261015`, que contém o último ambiente de render, estavam recuperáveis por cerca de **79 horas** na consulta de 16/10. A UI exibiu **US$ 1,10 por recuperação**, além de US$ 0,06849/h por volume ativo de 250 GiB. O original fica em FIN-01 e o disco do último render em FIN-03. Os prazos e valores variam com o tempo e precisam ser revistos antes de restaurar. Nenhum volume foi restaurado, movido ou excluído nesta retomada. Não esvaziar a lixeira. Os artefatos locais continuam disponíveis e foram verificados.

O seletor de deploy mostrou **1× A100 80 GB SXM4, `1A100.22V`, FIN-01, US$ 2,016/h**, On-Demand/Pay As You Go. Disponibilidade é uma observação, não uma reserva. O ensaio anterior de 1.195,291 s projeta cerca de US$ 0,67 de inferência por vídeo, ou US$ 2,01 para três. Três limites de 2.400 s equivalem a **US$ 4,032 apenas de inferência**. Inicialização, download, verificações, recuperação e storage são adicionais; esses números não são teto de cobrança da VM. A recarga mínima de US$ 20 é crédito na conta, não estimativa de preço dos três vídeos.

Nenhuma VM nova, render pago ou recarga foi iniciado nesta rodada. O rascunho `execution/cost-plan.draft.json` foi atualizado com saldo, preço e bloqueio atuais. O plano efetivo e a previsão de consumo precisam ser persistidos antes de provisionar, revalidando capacidade e recuperação. Usar uma GPU para os três renders em sequência, baixar e conferir as saídas e encerrar a instância para interromper compute ao terminar. Não deixar GPU aguardando revisão humana. Não há reserva artificial de US$ 1.

O Astra revisou a proposta e os artefatos, no modelo `gpt-6-astra`, esforço `medium`. Pareceres privados em `reviews/PROTOCOLO-ASTRA.md` e `CANDIDATAS-ASTRA.md`. Os retratos foram considerados adequados ao ensaio; a revisão não substitui escuta nem aceite do cliente. Nos vídeos, conferir principalmente textura da camisa de Rafael, cabelo sobre a blusa de Ana, cachos e contatos das mãos de Marina, além de boca, corpo, fundo e junções dos chunks.

O preparo do QC CPU foi reconstruído por cache offline com Torch 2.6 e limite de duas threads. Compilação, interfaces CLI e planejamento passaram. Os scripts e contratos deste lote usam os hashes, durações e contagens próprias de cada voz, com crop e offset temporal ainda não definidos. **Nenhum vídeo foi processado por esse preparo.** Os ambientes temporários de voz e QC foram removidos. Bootstrap, contratos, fontes e resultados do preparo ficam preservados em `qc/` para retomada após a recarga.
