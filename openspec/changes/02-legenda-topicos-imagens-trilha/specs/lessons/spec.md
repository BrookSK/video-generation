# Spec Delta

## ADDED Requirements

### Requirement: Legenda literal sincronizada
Toda cena SHALL ter legenda com o texto daquela cena, dividido em trechos de até duas linhas. A legenda MUST mostrar o texto palavra por palavra, sem trocar, cortar ou acrescentar palavras, e cada trecho MUST aparecer enquanto é falado, com o tempo tirado do áudio gerado da cena.

#### Scenario: Legenda confere com o texto
- **WHEN** uma aula fica pronta
- **THEN** a junção dos trechos da legenda de cada cena é idêntica ao texto informado para a cena

#### Scenario: Trecho dentro da frase falada
- **WHEN** a cena tem três frases separadas por pausas no áudio
- **THEN** cada trecho da legenda começa e termina dentro do intervalo de fala da sua frase

#### Scenario: Pausas que não casam com as frases
- **WHEN** o número de intervalos de fala detectados difere do número de frases
- **THEN** o tempo da cena é dividido pelos caracteres dos trechos e o texto exibido continua literal

### Requirement: Tópicos na tela
Cada cena SHALL aceitar até 5 tópicos com até 80 caracteres cada. Os tópicos MUST aparecer escritos na tela durante toda a cena, com o texto exatamente como foi informado, à direita no 16:9 e acima da legenda no 9:16, nas cores da identidade.

#### Scenario: Cena com tópicos
- **WHEN** uma cena tem os tópicos "Isolar a área" e "Usar EPI"
- **THEN** os dois tópicos aparecem durante a cena com esse texto

#### Scenario: Tópicos acima do limite
- **WHEN** a pessoa informa 6 tópicos numa cena ou um tópico com mais de 80 caracteres
- **THEN** a geração é recusada indicando a cena e nada é gravado

### Requirement: Imagem durante a explicação
Cada cena SHALL aceitar uma imagem opcional em JPEG, PNG ou WebP. Durante uma cena com imagem, a imagem MUST ocupar a área principal sem distorção e o apresentador MUST aparecer num quadro menor no canto, com fala e legenda mantidas. Cenas sem imagem MUST mostrar o apresentador em tela cheia.

#### Scenario: Cena com captura de tela
- **WHEN** uma cena tem uma captura de tela do sistema
- **THEN** a captura aparece na área principal durante a cena, sem distorção, e o apresentador aparece no canto

#### Scenario: Cena sem imagem
- **WHEN** a cena seguinte não tem imagem
- **THEN** o apresentador volta à tela cheia e nenhuma imagem aparece

### Requirement: Trilha de fundo com ducking
Quando a trilha estiver ligada na aula, a trilha da identidade SHALL tocar durante a aula em volume baixo, repetida ou cortada até a duração da aula, com saída suave no encerramento. A trilha MUST ficar mais baixa nos trechos com fala do que nos trechos sem fala, sem encobrir a voz. A aula MUST poder ser gerada sem trilha.

#### Scenario: Volume sob a fala
- **WHEN** uma aula com trilha fica pronta
- **THEN** o nível da trilha medido no arquivo final é menor durante a fala do que nas pausas

#### Scenario: Aula sem trilha
- **WHEN** a pessoa desliga a trilha na aula
- **THEN** o arquivo final tem só a voz

#### Scenario: Trilha ilegível
- **WHEN** a trilha congelada na aula não pode ser lida na montagem
- **THEN** a aula fica em falha com motivo em português
