# P06 — investigação de sotaque brasileiro

Rodada de 15/10/2026, após o retorno humano da comparação anterior. A P06 continua incompleta. Naturalidade inclui pronúncia e sotaque percebidos como brasileiros; texto recuperado por ASR não atende sozinho a esse requisito.

## Evidência do usuário

A amostra 2 era Qwen Base/MLX com referência Kokoro sem os primeiros 0,53 s. Foi considerada próxima em naturalidade, mas o início soou como português de Portugal. A amostra 4 era Chatterbox com a mesma referência recortada; foi considerada razoável, ainda precisando melhorar. Nenhuma foi aprovada. O usuário também percebeu pt-PT nos outros áudios/vídeos ouvidos, sem identificar individualmente todos os arquivos. Não transformar essa frase em uma nota específica inventada para cada arquivo.

Os WAVs foram preservados. O retorno foi anexado ao mapa da comparação anterior e à nova pasta privada `p06-sotaque-20261015/feedback-anterior.json`. A preferência parcial não virou aprovação da voz nem dos vídeos.

## O que foi descartado na investigação

Não foi encontrada configuração explícita que tenha trocado o idioma local para pt-PT. O frontend do Kokoro mapeia `p` a `pt-br`; Misaki passa esse idioma ao eSpeak. Chatterbox carrega o fine-tune `t3_pt_br` já fixado no manifesto. O card atual desse modelo é a mesma revisão já usada, portanto apontar para ele novamente não constitui um upgrade de sotaque. Veja [o trace do código](P06-SOTAQUE-CODIGO.md).

Qwen usa um token `Portuguese` compartilhado. A ausência de um token separado não prova qual sotaque sairá. No Base utilizado, o caminho de clonagem em contexto recebe o áudio e sua transcrição; ele não recebe uma instrução livre de sotaque. Inserir `pt-BR` como código inventado ou um `instruct` ignorado não resolve essa limitação. [Implementação e fontes](P06-SOTAQUE-FONTES.md).

As comparações E/F/G/J compartilham uma referência sintética derivada de Kokoro. Ter dois modelos de saída não torna essas referências independentes. A rejeição em ambos sustenta investigar o insumo comum, mas ainda não prova que ele cause o sotaque. O controle direto Kokoro também não recebeu uma avaliação individual explicitamente identificada nesta resposta.

## Pesquisa de fonética e limites de classificação

Um preprint de pesquisadores da UFRJ/Unicamp estudou inconsistências de realização fonética em vozes sintéticas brasileiras, incluindo Qwen e Kokoro. O trabalho combina reconhecedores de fonemas, formantes e medidas espectrais, agregadas em várias frases por locutor. A tarefa avaliada é detecção de fala sintética, não um classificador validado de Brasil versus Portugal para nossas duas palavras iniciais. Isso ajuda a rejeitar a ideia de usar apenas pitch ou ASR como certificado de sotaque. Não foi executado esse pipeline aqui. [Artigo, versão 1 de 20/09/2026](https://arxiv.org/html/2609.23807v1).

A queixa humana é a evidência perceptiva vigente. F0 parecido ou duas transcrições corretas não a contradizem. Tampouco existe um sotaque brasileiro único: o objetivo inicial é uma realização consistente e reconhecida pelo cliente como brasileira, sem impor uma região específica não solicitada.

## Novo controle: voz descrita, sem clonar Kokoro

A variante VoiceDesign do Qwen aceita uma descrição de voz. Foi escolhida para testar a orientação explícita de sotaque sem reutilizar a referência atual. É um ensaio local, sem integração ao worker, sem treinamento, sem voz de uma pessoa real e sem custo de GPU Verda. Não é declaração de que essa variante atende pt-BR.

O par mantém checkpoint bf16, runtime MLX-Audio 0.5.9, texto, idioma, seed e parâmetros iguais. Usa os defaults de amostragem do checkpoint: temperatura 0,9, top-p 1, top-k 50 e repetition penalty 1,05. O piso 1,5 do ICL Base não foi transportado automaticamente para VoiceDesign. O limite explícito é 384 tokens, com observação do EOS real antes de salvar WAV.

- L: descrição de mulher adulta, voz clara, ritmo de conversa, saudação suave e finais de frase contínuos.
- M: a mesma descrição, acrescida de uma cláusula pedindo uma falante nativa de português brasileiro, com sotaque brasileiro também nas primeiras palavras.

Somente a cláusula de sotaque muda no condicionamento do par. Os rótulos e caminhos de saída identificam os arquivos. A instrução pode alterar timbre e estilo além da pronúncia; não há identidade vocal fixada por um speaker embedding nesse experimento. A mudança Base → VoiceDesign também impede atribuir qualquer melhora sobre J exclusivamente à remoção do Kokoro. Uma realização por condição serve à triagem, não estima efeito médio ou robustez.

As duas sínteses concluíram offline com saída zero, EOS 2150 observado e sem clipping antes da gravação. L tem 9,04 s; M tem 9,52 s. Os picos MLX registrados foram 8.155.313.049 e 7.793.414.839 bytes, respectivamente. Não são medições CUDA ou promessa de desempenho do worker. O snapshot MLX foi conferido por tamanho e hash antes da inferência; o tokenizer idêntico ao Base foi reaproveitado por hardlink, sem alterar o original.

| Condição | SHA-256 do WAV bruto | Diagnóstico de conteúdo |
|---|---|---|
| L | `bb674689776827dea826bc7d5e362252818cd81b96a95ca349e10d65b25fb4e9` | Large sugere “ganha a voz”; small-q4 sugere “eu sou Ana”. Divergências de artigos a conferir na escuta. |
| M | `1434777d3bdce25247a6b356579b326a695e25b472378a7730d631287855ebe6` | Large recupera a sequência esperada; small-q4 sugere “eu sou Ana”. Não há literalidade humana certificada. |

Os quatro ASRs terminaram sem usar o texto esperado como prompt. As variantes Whisper têm erros correlacionados e não classificam sotaque. Os resultados completos ficam em `asr/ANALISE.md` na pasta privada desta rodada. O episódio anterior já demonstra que acertar palavras não resolve a rejeição perceptiva de pt-BR.

A página privada `p06-sotaque-20261015/revisao.html` apresenta Nova A/Nova B em ordem fixa embaralhada, com rótulos neutros; a correspondência técnica fica recolhida. Não é um estudo duplo-cego. As cópias PCM16 recebem somente ganho constante para volume comum de −23,5 LUFS, sem mudança de velocidade, duração, sample rate ou corte. Os raws foram preservados; os bytes ouvidos e comandos estão em `mapa-escuta.json`. As antigas 2/4 e a referência sintética usada nelas também estão disponíveis como controles separados.

O usuário ouviu Nova A/Nova B e respondeu **“Ainda nenhuma atende”**. As duas saídas L/M estão reprovadas para a direção pretendida; não há notas separadas de sotaque/ritmo por arquivo. A instrução explícita não resolveu o objetivo nessa realização. Isso não prova incapacidade global do modelo ou causa única na referência. Não houve novo render de avatar nem integração de VoiceDesign ao worker. Os WAVs deste experimento não têm watermark Perth. A comparação só indica uma direção útil se o usuário perceber melhora na saída real.


## Revisão ampla solicitada ao Astra

O usuário pediu explicitamente um subagente Astra com raciocínio médio ou alto e uma perspectiva do sistema completo. Foi chamado Astra com reasoning medium. O [parecer e as fontes](P06-ASTRA-NATURALIDADE.md) questionam explicações únicas de modelo, referência, sotaque, texto, enquadramento, scheduler e resolução. A falha local não foi generalizada para todos os modelos abertos.

O parecer recomenda um único controle novo de referência, com H como baseline masculino, em vez de comparar diretamente com J feminino. A gravação humana brasileira Cadu/OHF tem publicação CC0 destinada a TTS. A identidade e a duração da referência mudam; o resultado testa esse pacote, não isola a variável abstrata “humano versus sintético”. A própria gravação entra na escuta, identificada como referência e com outro texto.

O par preserva o texto H (“Olá, eu sou o João...”), Qwen Base 1.7B bf16, runtime MLX-Audio 0.5.9, seed 20261015 e sampler. A troca fica restrita a referência, SHA e transcrição correspondente; o caminho de saída apenas identifica N. O decode/resampling de 48 para 24 kHz e PCM16 foi registrado, sem ganho/limiter. Dois ASRs concordam na transcrição candidata de Cadu; não existe transcrição oficial publicada ou audição do agente.

O controle N foi gerado uma única vez, com saída zero e EOS 2150 observado. Resultado: **9,84 s**, PCM16 mono/24 kHz, sem clipping na conversão; SHA-256 `bc7d8c5ab058770c0fb5bb5423a84e2325b35c0ba6d4746188bc5260c24b4ec8`. A execução offline com rede negada levou 56,28 s incluindo inicialização; o pico MLX registrado foi 8.791.730.325 bytes. Não é benchmark Linux/CUDA nem aprovação de fala.

O ASR large recuperou a sequência esperada de H. O small-q4 segmentou “aproxima pessoas” como “a próxima pessoas”, divergência também presente em H. O restante das palavras foi recuperado. Não foi confirmado erro da fala nem sotaque por esses dados. A transcrição da referência é candidata, concordante nos dois ASRs, sem uma transcrição oficial publicada.

A página privada `p06-sotaque-20261015/controle-referencia/revisao.html` contém a gravação humana identificada e o par H/N sob rótulos C/D em ordem fixa embaralhada. Os três players usam ganho constante para volume comum de aproximadamente −23,5 LUFS; a referência fornecida ao modelo é o PCM24k anterior a esse ajuste de escuta. Os hashes dos bytes ouvidos ficam em `mapa-escuta.json`. A voz feminina não foi resolvida por este ensaio masculino. A avaliação humana do alvo e da nova saída está pendente.

Não houve novo render, contratação ou consumo de compute Verda. O arquivo novo mantém watermark Perth nulo e continua fora do manifesto/worker de produção. O erro inicial do controlador foi somente a ausência da pasta de logs, antes de criar o subprocesso de síntese; foi corrigido e registrado sem repetir inferência. Os dados brutos e fontes foram preservados.


## Próxima decisão

A avaliação humana deve separar: sotaque no começo, sotaque ao longo da frase, naturalidade de ritmo/entonação e palavras pronunciadas. Conservar a opção de nenhuma atender e manter disponíveis as amostras anteriores já reprovadas. Se a direção funcionar, repetir em outras frases e seeds antes de integrar um novo motor ou renderizar vídeo longo.

O controle N é a única nova troca de referência desta rodada. Se a própria referência atender e N continuar reprovado, o próximo contraste deve separar implementação e modelo com entrada equivalente, conforme a matriz do Astra. Se o alvo humano não atender, o resultado não condena o motor. Não há evidência de que mais variações de temperatura, sozinhas, garantam corrigir o sotaque. Os [limites e caminhos de referência](P06-SOTAQUE-REFERENCIAS.md) ficam separados do resultado dos ensaios.

As análises e evidências brutas não aprovam C1–C7. Voz, sincronia e movimento continuam sujeitos à revisão das amostras reais.
