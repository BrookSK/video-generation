# Spec Delta

## Purpose

Mostra ao cliente a montagem nova sobre uma aula real e informa à equipe o custo de GPU por cena, sem instalar no ambiente do cliente e sem GPU nova.

## ADDED Requirements

### Requirement: Aula de exemplo sobre renders reais
A entrega SHALL incluir uma aula de exemplo gerada pela montagem da plataforma, rodando local, com as cenas reais da videoaula do Rafael de 21/10. A aula MUST ter troca de plano, legenda literal, tópicos, uma imagem e trilha, com abertura e encerramento, e MUST ser gerada sem uso de GPU.

#### Scenario: Aula de exemplo pronta
- **WHEN** a aula de exemplo é montada pela stack local
- **THEN** o arquivo passa na validação de saída e a legenda confere palavra por palavra com o roteiro

#### Scenario: Sincronia das cenas reais
- **WHEN** as cenas reais são finalizadas para a aula
- **THEN** a sincronia de cada cena medida pelo SyncNet é de 0 quadros

### Requirement: Tempo de GPU por cena
A entrega SHALL registrar, para cada cena da aula de exemplo, o tempo de GPU medido no render de 21/10, a duração do áudio da cena e o total da aula, com a GPU e a receita usadas.

#### Scenario: Registro para a equipe
- **WHEN** a equipe abre o registro da aula de exemplo
- **THEN** encontra o tempo de GPU de cada cena, a relação com a duração do vídeo e o total, com a máquina informada
