# Spec Delta

## Purpose

Permite à equipe do cliente gerar no painel uma aula com várias cenas em plano médio ou close e baixar um único vídeo com abertura, cenas em ordem e encerramento, montado sem GPU.

## ADDED Requirements

### Requirement: Aula com várias cenas
O painel SHALL permitir criar uma aula com 2 a 12 cenas ordenadas, cada uma com o texto que o apresentador fala, além de avatar, cenário e formato. O formato MUST ser 9:16 quando não informado. O texto de cada cena MUST ser usado literalmente na voz, dentro do limite de fala vigente por vídeo.

#### Scenario: Aula de três cenas
- **WHEN** a pessoa cria uma aula de três cenas com textos distintos
- **THEN** o vídeo final mostra as três cenas na ordem informada e o apresentador fala em cada cena exatamente o texto dela

#### Scenario: Número de cenas fora do limite
- **WHEN** a pessoa tenta gerar uma aula com 1 ou com 13 cenas
- **THEN** a geração é recusada com mensagem e nenhuma aula ou vídeo é criado

#### Scenario: Cena acima do limite de fala
- **WHEN** uma cena tem texto acima do limite de fala vigente
- **THEN** a geração é recusada indicando a posição da cena e nada é gravado

#### Scenario: Avatar ou cenário arquivado
- **WHEN** a aula usa um avatar ou um cenário arquivado
- **THEN** a geração é recusada e nada é gravado

### Requirement: Identidade obrigatória para gerar aula
O painel MUST bloquear a geração de aula enquanto não houver logo e cores cadastrados, com aviso que leva à tela Identidade.

#### Scenario: Sem identidade cadastrada
- **WHEN** a pessoa abre Nova aula sem identidade cadastrada
- **THEN** o botão Gerar fica bloqueado e o aviso aponta para a tela Identidade

### Requirement: Plano médio ou close por cena
Cada cena SHALL ter plano médio ou close. O cenário MUST guardar, para cada formato, um enquadramento médio e um close, ajustáveis no editor com prévia. O close MUST vir de um render com enquadramento fechado, nunca de ampliação do vídeo do plano médio. Cenário sem close salvo MUST usar um close derivado do médio, com o apresentador maior e o topo da cabeça na mesma altura.

#### Scenario: Troca de plano entre cenas
- **WHEN** uma aula alterna cenas em plano médio e close
- **THEN** cada cena aparece no plano escolhido e a passagem entre elas é um corte seco

#### Scenario: Cenário antigo sem close
- **WHEN** uma cena em close usa um cenário cadastrado antes desta mudança
- **THEN** a cena sai com o close derivado do médio, sem erro

#### Scenario: Vídeo avulso
- **WHEN** um vídeo avulso é gerado pelo painel ou pela API
- **THEN** ele sai no plano médio, igual ao comportamento anterior

### Requirement: Abertura e encerramento fixos
Toda aula SHALL começar com uma abertura e terminar com um encerramento de 3 s cada, com o fundo na cor de fundo, o logo centralizado e a cor de destaque da identidade congelada na aula.

#### Scenario: Aula pronta
- **WHEN** uma aula fica pronta
- **THEN** o arquivo começa e termina com 3 s na cor de fundo cadastrada, com o logo visível

### Requirement: Montagem sem GPU
A montagem da aula MUST rodar só no supervisor CPU. O worker GPU MUST nunca receber a montagem, e o supervisor MUST recusar iniciar com geração de vídeo e montagem de aula juntas.

#### Scenario: Supervisor com configuração mista
- **WHEN** o supervisor é iniciado com `WORKER_KINDS=video,lesson_assemble`
- **THEN** ele recusa iniciar com código de saída 2

#### Scenario: Claim de outros tipos
- **WHEN** um worker pede tarefas de vídeo ou de preparo de asset
- **THEN** nunca recebe uma tarefa de montagem de aula

### Requirement: Estado da aula e falhas
A aula SHALL ficar na fila enquanto houver cena pendente, passar a montagem quando todas as cenas estiverem prontas e ficar pronta só com o arquivo final íntegro publicado. A falha definitiva de qualquer cena ou da montagem MUST levar a aula ao estado de falha com motivo legível, sem entregar aula parcial como pronta. A última cena pronta MUST gerar uma única montagem, mesmo com conclusões simultâneas.

#### Scenario: Cena falha
- **WHEN** uma cena falha em definitivo
- **THEN** a aula fica em falha com a posição da cena no motivo e nenhuma montagem é criada

#### Scenario: Últimas cenas concluídas juntas
- **WHEN** as duas últimas cenas de uma aula concluem ao mesmo tempo
- **THEN** existe exatamente uma montagem para a aula

#### Scenario: Tentativa obsoleta
- **WHEN** uma tentativa de montagem que perdeu o lease tenta concluir
- **THEN** a conclusão é recusada e a aula não muda de estado

### Requirement: Arquivo final da aula
O arquivo final SHALL ser H.264 `yuv420p`, AAC 48 kHz, 25 fps, com `+faststart`, em 1080x1920 ou 1920x1080 conforme o formato. A duração MUST ser 3 s de abertura mais a soma das cenas mais 3 s de encerramento, com tolerância de um quadro por junção. Arquivo fora desse perfil MUST falhar a montagem com mensagem em português.

#### Scenario: Perfil e duração
- **WHEN** uma aula 16:9 de três cenas fica pronta
- **THEN** o arquivo é 1920x1080, H.264 e AAC 48 kHz, e dura 6 s mais a soma das cenas

#### Scenario: Cena com resolução diferente
- **WHEN** uma cena chega com resolução diferente da do formato da aula
- **THEN** a montagem falha com `OUTPUT_INVALID` e a cena não é ampliada nem reduzida

### Requirement: Acompanhar e baixar a aula
O painel SHALL mostrar a lista de aulas e, em cada aula, o estado de cada cena e da montagem, com o motivo de falha quando houver. Com a aula pronta, o painel MUST mostrar o player e o download do arquivo final. O histórico de vídeos avulsos MUST não listar as cenas de aulas, e a API pública MUST continuar igual.

#### Scenario: Aula pronta
- **WHEN** a aula fica pronta
- **THEN** a tela da aula mostra o player e o botão Baixar MP4

#### Scenario: Download antes de pronta
- **WHEN** alguém pede o download de uma aula que ainda não está pronta
- **THEN** o pedido é recusado

#### Scenario: Histórico avulso
- **WHEN** a pessoa abre o histórico de vídeos avulsos
- **THEN** as cenas de aulas não aparecem nele
