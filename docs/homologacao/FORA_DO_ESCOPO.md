# Pedidos fora do escopo

Dois pedidos novos registrados, abaixo. Este documento não transforma defeitos do combinado em cobrança extra nem registra aceite em nome do cliente.

## Correções incluídas

Falhas da instalação/pipeline/painel/API/documentação acordados, formato/exportação incorreto, perda de literalidade, sincronização/naturalidade reprovada nos critérios aprovados, problemas de enquadramento e falhas de recuperação previstas são defeitos a corrigir e reamostrar na P06. A reprovação permanece registrada; o cliente não precisa aceitar amostra defeituosa para concluir o sistema.

## Solicitações novas

Geração de roteiro por IA a partir de briefing, auto-post/agendamento/integração Meta, automação de ligar/desligar GPU, produção pelo desenvolvedor de assets além dos 2 avatares/4 cenários iniciais acordados e funcionalidades não presentes no escopo selado exigem avaliação/proposta separada. A equipe pode cadastrar novos assets pelo painel; isso já faz parte da autonomia acordada.

Se o cliente solicitar algo novo, acrescente registro com data, solicitante, descrição concreta, diferença em relação ao combinado, impacto e decisão real do cliente. Não implemente nem declare aprovado sem autorização. Custos de servidor/disco/domínio/registro de imagens permanecem com o cliente; este registro não autoriza contratação nem gasto.

Vereditos de qualidade e aceite ficam em [MATRIZ.md](MATRIZ.md). Dúvida sobre a fala literal não é um novo comando ao modelo: a interface recebe o texto que será falado, não um prompt para gerar roteiro.

## Registro

### 22/10/2026: montagem institucional das aulas

- Solicitante: Lucas Narciso (ON Solutions), por áudios de 21/10 e 22/10 e mensagem escrita de 22/10.
- Pedido: aulas institucionais e de treinamento no padrão de curso, montadas dentro da plataforma pela própria equipe: legenda tirada do texto da fala, tópicos na tela por cena, trilha de fundo que abaixa sob a fala, abertura e encerramento fixos com logo e cores do cliente, troca de plano médio e close entre cenas e imagem ou tela do sistema durante a explicação.
- Diferença em relação ao combinado: o escopo selado do M001 gera um vídeo por texto, sem cenas, legenda, trilha, telas nem montagem. A videoaula de demolição foi montada fora da plataforma.
- Impacto: novo ciclo M002-montagem-institucional no Bianchini Method, com aula, cenas, identidade visual e montagem em CPU. Sem GPU nova e sem mudança na receita de inferência.
- Fora do pedido: narração contínua refeita em GPU, produção da série de aulas pelo desenvolvedor e trabalho contínuo.
- Decisão real do cliente: aprovou em 22/10/2026 o valor de R$ 650 ("vamos seguir com aquele valor menor"). O cliente pagou por Pix em 22/10 a metade do total combinado com o Help Desk (R$ 2.750); o restante vem na entrega. Início previsto para 26/10/2026, entrega na mesma semana.

### 13/11/2026: avatares pela API

- Solicitante: Lucas Narciso (ON Solutions), por mensagens e áudios de 13/11.
- Pedido: o sistema dele (My Academy) passar a fazer pela API o que hoje é feito no painel: separação por escola, avatares, cenários, identidade visual, trilhas, aulas, revisões e aviso por webhook.
- Diferença em relação ao combinado: o escopo selado do M001 prevê a API só para criar job, consultar status, listar assets e baixar o vídeo. Cadastro de avatar e de cenário é feito pelo painel.
- Impacto: a API `/api/v1` ganha cadastro, consulta e arquivamento de avatar por chave de API, com o nome de quem autorizou o uso da imagem e a data da autorização. O fluxo de vídeo, o painel e o worker não mudam. Uso descrito em [GUIA.md](../api/GUIA.md).
- Fora do pedido atendido: separação por escola na plataforma, cenários, identidade visual, trilhas, aulas, revisões e webhook pela API. Ficam para proposta separada. A separação por escola fica no sistema do cliente, que guarda a qual escola pertence cada avatar.
- Decisão: em 13/11/2026 o Felipe decidiu fazer sem custo o cadastro, a consulta e o arquivamento de avatares pela API. Os demais itens não foram aprovados nem orçados.
