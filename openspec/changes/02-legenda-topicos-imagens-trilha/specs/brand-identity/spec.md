# Spec Delta

## ADDED Requirements

### Requirement: Trilha de fundo na identidade
A identidade SHALL aceitar uma trilha de fundo opcional em MP3, WAV, M4A ou OGG de até 20 MB, enviada pela equipe. Trocar a trilha MUST valer só para as aulas criadas depois, e o sistema MUST não fornecer trilha própria.

#### Scenario: Enviar trilha
- **WHEN** a pessoa envia um MP3 de 5 MB na tela Identidade
- **THEN** a trilha fica gravada e pode ser ouvida na tela

#### Scenario: Trilha fora do formato ou do tamanho
- **WHEN** a pessoa envia um arquivo FLAC ou um MP3 de 25 MB
- **THEN** o envio é recusado com mensagem no campo da trilha

#### Scenario: Ligar trilha sem trilha cadastrada
- **WHEN** a pessoa tenta gerar uma aula com trilha ligada e a identidade não tem trilha
- **THEN** a geração é recusada com aviso que leva à tela Identidade
