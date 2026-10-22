# Proposal

## Why

Para entregar a montagem ao cliente sem instalar no ambiente dele e sem gastar GPU, a prova precisa de uma aula real. Os renders de 21/10 da videoaula do Rafael (sete planos em médio e close, voz aprovada) já existem. A montagem nova sobre eles mostra ao cliente o resultado final, e os tempos medidos naqueles renders dão à equipe o custo de GPU por cena.

## What Changes

- Aula de exemplo montada pela montagem nova, localmente, sobre os renders reais de 21/10 da videoaula do Rafael: troca de plano, legenda literal, tópicos, uma imagem e trilha, com abertura e encerramento.
- Registro do tempo de GPU por cena medido nos renders de 21/10, para a equipe estimar o custo de uma aula.
- Pacote de entrega ao Felipe: aula de exemplo e a prova da change 03.

Decisão do Felipe em 22/10/2026: nada é instalado no ambiente do cliente neste ciclo. A instalação continua pendente do M001.

Fora de escopo: GPU nova, Verda, servidor do cliente, novos renders e narração contínua.

## Capabilities

### New Capabilities

- `lesson-example`: aula de exemplo montada sobre renders reais e o registro de GPU por cena.

### Modified Capabilities

Nenhuma.

## Impact

- Script de preparo da aula de exemplo no pacote privado de amostras, fora do repositório, com os renders, os WAVs e o roteiro da videoaula do Rafael.
- Registro em `docs/homologacao/M002-AULA-EXEMPLO.md` com hashes, perfil do arquivo, conferência da legenda e tempo de GPU por cena. Mídia e material do cliente ficam fora do git.
- Requisito do escopo M002 atendido: RSK-010.
