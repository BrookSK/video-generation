# Spec Delta

## Purpose

Guarda a identidade visual do cliente (logo e cores) usada na abertura e no encerramento fixos de todas as aulas.

## ADDED Requirements

### Requirement: Cadastro da identidade visual
O painel SHALL permitir cadastrar e trocar um logo (PNG ou JPEG), uma cor de fundo e uma cor de destaque no formato `#RRGGBB`. O sistema MUST manter uma única identidade vigente e registrar autor e data da última mudança.

#### Scenario: Cadastrar logo e cores
- **WHEN** a pessoa envia um logo PNG, a cor de fundo `#0B2545` e a cor de destaque `#F2A541` na tela Identidade
- **THEN** a identidade fica gravada e a tela reaberta mostra o logo e as duas cores

#### Scenario: Logo em formato não aceito
- **WHEN** a pessoa envia um logo WebP ou SVG
- **THEN** o envio é recusado com mensagem no campo do logo e a identidade anterior continua valendo

#### Scenario: Cor inválida
- **WHEN** a pessoa informa a cor `azul`
- **THEN** o envio é recusado com mensagem no campo da cor

### Requirement: Troca de identidade vale para aulas novas
Trocar o logo ou as cores SHALL valer para as aulas criadas depois da troca. Uma aula já criada MUST continuar usando o logo e as cores vigentes na sua criação, inclusive em nova tentativa de montagem.

#### Scenario: Aula criada antes da troca
- **WHEN** uma aula é criada, a identidade é trocada e a montagem dessa aula roda em seguida
- **THEN** a abertura e o encerramento usam o logo e as cores anteriores à troca

#### Scenario: Aula criada depois da troca
- **WHEN** uma aula é criada depois da troca de logo
- **THEN** a abertura e o encerramento usam o logo novo
