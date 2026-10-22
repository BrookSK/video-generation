# Tasks

## 1. Cenas reais

- [ ] 1.1 Gerar os MP4s de cena 1920x1080 a partir dos renders da receita A e dos WAVs aprovados, pela finalização da plataforma, com o atraso de vídeo por cena da v2; guardar no pacote privado de amostras; verificar com `ffprobe` (perfil de saída) e com `qc/scripts/sync.py` (offset de 0 quadros em todas as cenas)

## 2. Aula de exemplo

- [ ] 2.1 Criar pela stack local da change 03 a aula de exemplo com as cenas reais em ordem, a fala literal do roteiro, troca de médio e close, tópicos, uma captura de tela sintética e trilha, e montá-la pelo supervisor CPU sem GPU; verificar com `ffprobe` (perfil e duração esperada) e com a conferência da legenda palavra por palavra contra o roteiro
- [ ] 2.2 Assistir à aula de exemplo com som do começo ao fim e anotar defeitos de corte, legenda, tópicos, imagem ou trilha; corrigir o que for da montagem e repetir 2.1; verificar com a anotação final sem defeito aberto da montagem

## 3. Registro e entrega

- [ ] 3.1 Calcular o tempo de GPU por cena a partir de `renders/_remoto/status.json` e das durações dos áudios; verificar conferindo a soma com a duração total da fila registrada no `P06-ROTEIRO-RAFAEL.md`
- [ ] 3.2 Escrever `docs/homologacao/M002-AULA-EXEMPLO.md` com o caminho privado e o SHA-256 da aula, o perfil do arquivo, a conferência da legenda, a sincronia por cena, o tempo de GPU por cena e o total, e o aviso de que logo, cores e trilha são sintéticos; verificar relendo os números contra os arquivos
- [ ] 3.3 Entregar ao Felipe a aula de exemplo e o resumo da prova da change 03, sem enviar nada ao cliente; verificar com o arquivo aberto e reproduzido localmente
