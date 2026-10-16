# P06 — dinâmica, gestos e câmera

Pesquisa e ensaio iniciados em 15/10/2026, com verificações em 16/10 UTC. O cliente gostou da demonstração anterior e pediu mais dinâmica: braços, mãos e zoom. A voz masculina D continua aprovada e preservada. Este documento complementa [o ensaio D](../homologacao/P06-AVATAR-D.md); não encerra a P06.

## Referência observada

Fonte enviada pelo usuário: [Reel DefeTmphQan](https://www.instagram.com/reel/DefeTmphQan/). Foram recuperadas as faixas públicas completas, com 313 quadros, 1916×1078, 24 fps e 13,041667 s de vídeo. A análise visual usa 27 quadros, espaçados a cada 0,5 s. Não houve audição ou playback audiovisual contínuo pelo agente. Não foi identificada a ferramenta usada pelos criadores.

| Trecho aproximado | Ação visível nos quadros |
|---|---|
| 0–1,5 s | Entrada lateral e reposicionamento do corpo |
| 2–2,5 s | Gesto curto com mão perto do rosto |
| 3,5–4,5 s | Objeto se aproxima e cobre a lente |
| 5–7 s | Revelação do carro; corpo e olhar viram; polegar aponta para ele |
| 8,5–9 s | Mão ao lado da boca |
| 11,5–12,5 s | Duas mãos na cabeça, reação ampla |
| 13 s | Saída lateral |

A escala do fundo parece relativamente estável na amostragem. Não há evidência suficiente para atribuir a dinâmica a grandes zooms repetidos. O detector de mudança visual encontrou um candidato em 4,5 s, no trecho de oclusão; isso não prova um corte. A adaptação proposta é um gesto moderado com retorno ao repouso e aproximação editorial discreta. Identidade, objetos e vídeo do Reel não são entradas do gerador.

## O que os implementadores publicam

| Fonte primária | Evidência e consequência prática |
|---|---|
| [Autores do InfiniteTalk — paper](https://arxiv.org/html/2508.14033v1) | Usam quadros esparsos da atuação em V2V para preservar movimento com liberdade de adaptação ao áudio. O controle não equivale a copiar cada gesto no instante exato. |
| [InfiniteTalk — implementação](https://github.com/MeiGen-AI/InfiniteTalk) e [demonstrações](https://meigen-ai.github.io/InfiniteTalk/) | Publicam I2V e V2V. As demos V2V humanas já incluem atuação e braços na fonte. Isso sustenta ensaiar referência temporal quando uma foto não entrega o gesto desejado. |
| [Kijai — workflow V2V](https://github.com/kijai/ComfyUI-WanVideoWrapper/blob/main/example_workflows/wanvideo_2_1_14B_V2V_InfiniteTalk_example_02.json) | Há um fluxo reproduzível com entrada de vídeo, redimensionamento e geração. É evidência de implementação independente; não valida automaticamente a qualidade ou o custo do nosso runtime. |
| [Discussão técnica entre Kijai e os autores](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/1069) | Explicam a integração e a seleção de referências/motion frames. Também há relatos de limitações em movimentos rápidos e mudanças de fundo. Relatos não são benchmark controlado. |
| [FFmpeg — zoompan](https://ffmpeg.org/ffmpeg-filters.html#zoompan) | Zoom pode ser feito na finalização, sem síntese neural. Duração por quadro, FPS, resolução e posição precisam ser explícitos para preservar a cadência e o enquadramento. |

O JSON V2V de Kijai foi baixado como dado bruto, sem executar o workflow: 57.087 bytes, SHA-256 `a0951c61b13ec6755772adfc5c13afe133284363e02053574a9fcbfd4c43817e`. Contém `VHS_LoadVideo`, `WanVideoImageToVideoMultiTalk`, `WanVideoSampler` e saída a 25 fps. Snapshot e manifesto ficam em `research-sources/` no pacote privado. Não foi transplantado para o nosso runtime.

A convergência útil está no material de entrada e no condicionamento temporal. Popularidade e demonstrações selecionadas não comprovam naturalidade no nosso caso. Por isso o teste preserva a voz aprovada e verifica o arquivo realmente produzido.

O Astra revisou a proposta no modelo `gpt-6-astra`, esforço `medium`. Recomendou avaliar o enquadramento e a atuação antes de trocar o gerador. Parecer completo no pacote privado `astra/PARECER.md`.

## Hipóteses e intervenções desta rodada

A imagem anterior foi criada como busto, sem braços completos. Seu prompt de geração incluía `hands` no negativo. O prompt do avatar dizia para manter as mãos abaixo da borda inferior. Esses fatores concretos restringiam o movimento pedido pelo cliente. Não demonstram que uma única causa explique todo o resultado.

Foram preparados dois ensaios:

1. **Zoom isolado:** partir do vídeo nativo anterior e manter a compensação visual de três quadros de B, o WAV D inteiro, 246 quadros e 25 fps. Aproximação cossenoidal de 1,00× a 1,06×, âncora (0,5; 0,36), supersampling espacial 2× e um quadro de saída por entrada. A faixa de 6% é uma proposta editorial para comparação. Não reproduz uma lente identificada no Reel nem cria detalhe ausente na geração 448×832.
2. **Gestos com meio corpo:** editar a imagem do personagem virtual existente para mostrar cotovelos, antebraços e mãos separados; inspecionar antes da inferência. Pedir um único gesto explicativo de palma aberta, moderado, abaixo do rosto, seguido de repouso. Câmera fixa. Manter WAV D, seed 42, modelo, quatro passos, text CFG 1 e audio CFG 2. Uma inferência de 9,84 s na A100 já existente.

O segundo ensaio altera **imagem e prompt juntos**. É um protótipo comparativo, não uma ablação que isola a contribuição de cada fator. O deslocamento temporal de B não deve ser transferido a ele sem nova medição.

## Critérios de avaliação

- Integridade: hashes, decodificação completa, 246 quadros, 9,84 s, PTS monotônicos e áudio D integral, sem clipping ou deslocamento introduzido na finalização.
- Corpo: gesto reconhecível; mãos, punhos e cotovelos presentes; sem dedos extras evidentes, fusões, desaparecimento ou saltos nas junções de 3,24/6,12/9,00 s.
- Imagem: rosto e roupa consistentes; fundo estável; espaço para o gesto. Um rosto menor na resolução nativa pode perder definição labial.
- Sincronia: crop facial definido pela geometria e pelos quadros antes do score; janelas e controles temporais de SyncNet. O instrumento mede compatibilidade temporal, não naturalidade ou anatomia.
- Avaliação humana: comparar o vídeo anterior, zoom e gestos com a mesma voz. A preferência e a naturalidade audiovisual dependem de reprodução com som e do julgamento do usuário/cliente.

Se o corpo continuar parado ou a mão falhar, conferir primeiro as entradas efetivamente consumidas. O próximo ensaio recomendado é V2V com atuação própria ou autorizada, gesto simples e retorno ao repouso, pela CLI existente. Antes disso, verificar FPS, duração, canvas e seleção dos quadros. Trocar por Wan Animate ou LongCat exigiria validar outro runtime, hardware, licenças e sincronia; não há prova de que essa troca isolada resolva o pedido.

## Evidências privadas

Pacote fora do Git: `video-generation-amostras/p06-dinamica-20261015/`. `reference/analysis/` contém quadros e observações da referência; `gestos-image/` registra a edição; `gestos-run/` contém entradas, custo planejado e execução; `zoom/` registra o filtro e a saída; `qc/` contém as verificações; `astra/` contém a revisão independente. URLs temporárias de CDN, credenciais e mídia da referência não são incluídas no repositório.

O [resultado técnico e o estado dos recursos temporários](../homologacao/P06-DINAMICA.md) registram a coleta e o QC. O painel da Verda solicita um código de seis dígitos enviado ao e-mail da conta. O teste em andamento usa SSH existente; o painel ainda depende desse código para consultar saldo e encerrar os recursos.
