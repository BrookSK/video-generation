# Uso do painel de vídeos

O painel atende a uma equipe única. Todos os usuários autenticados podem gerar vídeos, consultar o histórico da equipe, cadastrar assets e administrar pessoas/chaves. Não há perfis diferentes neste ciclo.

## Entrar e preparar o catálogo

Entre com o e-mail e a senha cadastrados pela equipe. Na primeira instalação, o operador cria o primeiro usuário conforme o guia de instalação. Sair encerra a sessão. Sem sessão válida, o painel pede login novamente.

Em **Avatares**, cadastre uma foto autorizada e escolha voz feminina ou masculina. Aguarde o recorte: um avatar em preparação não pode gerar vídeo. Falha de preparação precisa ser resolvida antes do uso. Não use foto sem autorização. Em **Cenários**, crie o fundo por imagem ou cor e salve o enquadramento para os dois formatos.

Arquivar retira o asset das escolhas de novos vídeos; não apaga os vídeos existentes. Avatares/cenários arquivados não podem ser usados em um novo pedido, inclusive ao refazer um vídeo antigo.

## Novo vídeo

1. **Texto da fala:** escreva exatamente o que será dito. Pontuação, espaços e quebras de linha são preservados. Não coloque comandos como “sorria”, “mude de cenário” ou instruções ao modelo: o sistema não interpreta roteiros.
2. **Avatar:** selecione um ativo. A voz aparece junto ao nome e vem do cadastro.
3. **Cenário:** selecione um ativo. A prévia usa a imagem preparada do avatar, o fundo e o enquadramento salvo no cenário.
4. **Formato:** 9:16 é vertical; 16:9 é horizontal. A prévia acompanha a escolha. Ela é estática: não demonstra fala nem qualidade de animação.

O contador usa o limite da receita vigente. A duração mostrada antes de gerar é apenas uma estimativa, quando a receita fornece taxa de caracteres; não é a duração medida do vídeo. O áudio real também precisa caber no limite. Sem receita vigente, o botão fica indisponível; o operador precisa concluir a calibração antes de liberar a geração.

Clique **Gerar vídeo**. O botão fica desabilitado durante o envio, e uma resposta perdida permite repetir a mesma intenção sem criar outro job. Depois da confirmação, o pedido já está salvo no servidor. Fechar a aba não cancela a fila. Alterar os dados e enviar de novo é uma nova intenção.

## Histórico e estados

**Histórico** mostra vídeos do painel e da API, com quem solicitou, origem, formato, avatar, cenário e data. Use o filtro de estado. A consulta é atualizada a cada 3 s, sem pedidos sobrepostos.

| Estado | Significado | Ação |
|---|---|---|
| Na fila | Pedido persistido, aguardando gerador; posição é na fila de vídeos. | Aguardar ou voltar depois. |
| Processando | Worker mantém a tentativa na GPU. Etapas: compor, voz, animar, finalizar, salvar. | Acompanhar etapa/tempo decorrido; não há porcentagem nem prazo garantido. |
| Pronto | Geração concluída. O resultado verifica se o arquivo ainda existe. | Abrir o vídeo e baixar o MP4. |
| Falha | Geração terminou com erro legível e código. | Conferir o motivo; corrigir dados ou pedir ao operador que verifique o gerador. |

**Gerador sem resposta** significa nenhum heartbeat observado ou último sinal há mais de 2 min. API/painel acessíveis não significam GPU operante. A fila permanece salva. Um erro de consulta aparece como estado desconhecido/último dado recebido, e não como diagnóstico de GPU desligada.

Recarregar a página busca novamente o job do servidor. Se faltar rede, o painel mantém o último estado recebido e identifica a falha de atualização.

## Resultado, falha e download

O resultado pronto usa o player nativo do navegador, com som/pausa/tela cheia. Duração e tamanho só aparecem quando medidos/persistidos; não são estimativas inventadas. **Baixar MP4** usa a sessão autenticada. Copiar esse link não concede acesso a alguém sem sessão. O arquivo é H.264/AAC, 25 FPS, 1080×1920 ou 1920×1080, com faststart.

Antes de pronto, o download fica indisponível. Um resultado concluído cujo arquivo sumiu mostra **Arquivo indisponível**: o operador verifica o volume de armazenamento. Erro do player não vira um vídeo de substituição; tente o download ou recarregue.

Em falha, informe ao operador o código exibido. `OUT_OF_MEMORY` significa memória insuficiente; `WORKER_LOST`, perda de comunicação/lease; `INPUT_INVALID` pode indicar fala maior que o limite de áudio; `RENDER_FAILED` e `OUTPUT_INVALID` precisam de diagnóstico do worker. Não reenvie indefinidamente.

**Refazer com os mesmos dados** copia fala, avatar, cenário e formato para Novo vídeo. Não envia sozinho. Confira tudo, substitua assets arquivados e clique Gerar vídeo quando estiver pronto.

Baixe e publique manualmente no Instagram ou em outra plataforma. Não existe publicação automática, acesso à conta do Instagram ou garantia de aceitação pela plataforma.

## Aulas

Uma aula junta várias cenas curtas num único MP4, com abertura e encerramento na identidade visual do cliente. Cada cena é um vídeo do avatar gerado como um vídeo avulso; a montagem acontece depois, no servidor, sem GPU.

### Identidade e trilha

Em **Identidade**, envie o logo (PNG ou JPEG, de preferência com fundo transparente) e escolha a cor de fundo e a cor de destaque no formato #RRGGBB. Clique **Salvar identidade**. Sem logo e cores, a aula não pode ser gerada. A prévia mostra a abertura e o encerramento de 3 s; o logo nunca é ampliado.

A trilha de fundo é opcional. Depois de salvar a identidade, escolha a trilha (MP3, WAV, M4A ou OGG, até 20 MB). Ela é salva na hora e pode ser ouvida no player da tela. **Remover trilha** faz as próximas aulas saírem sem trilha. O sistema não fornece trilha: use só material que o cliente tem direito de usar.

Trocar logo, cores ou trilha vale só para as aulas criadas depois. Aulas já criadas guardam a identidade da criação.

### Criar a aula

Em **Nova aula**, escolha o avatar, o cenário e o formato (9:16 ou 16:9). Depois monte as cenas, na ordem em que vão aparecer:

1. **Texto da cena:** escreva exatamente o que será falado. A legenda mostra esse mesmo texto, palavra por palavra. O limite de caracteres por cena é o da receita vigente.
2. **Plano:** **Plano médio** mostra o apresentador com o enquadramento do cenário; **Close** aproxima no rosto. Alternar os planos entre cenas deixa a aula menos monótona.
3. **Tópicos:** opcionais, um por linha, até 5 por cena e até 80 caracteres cada. Aparecem durante toda a cena, à direita no 16:9 e acima da legenda no 9:16, com o texto exatamente como foi escrito.
4. **Imagem:** opcional, uma por cena (JPEG, PNG ou WebP, até 20 MB), por exemplo uma captura de tela do sistema. Durante essa cena, a imagem ocupa a área principal sem distorção e o apresentador vai para um quadro menor no canto. A cena seguinte sem imagem volta ao apresentador em tela cheia.

Use **Adicionar cena**, **Subir**, **Descer** e **Remover** para organizar de 2 a 12 cenas. Marque **Tocar a trilha de fundo** para usar a trilha da identidade; a opção fica bloqueada quando a identidade não tem trilha. A trilha toca baixa, abaixa mais enquanto o apresentador fala e sai suave no encerramento.

Clique **Gerar aula**. Como no vídeo avulso, o botão trava durante o envio e uma resposta perdida não cria outra aula. Erros aparecem no campo da cena que precisa de ajuste.

### Acompanhar e baixar

**Aulas** lista as aulas da equipe com o estado e quantas cenas já estão prontas. A tela da aula é atualizada sozinha:

| Estado | Significado | Ação |
|---|---|---|
| Gerando cenas | As cenas estão na fila de vídeos ou em geração na GPU, uma de cada vez. | Aguardar; fechar a aba não cancela. |
| Montando | Todas as cenas ficaram prontas e o servidor está juntando abertura, cenas e encerramento. | Aguardar alguns instantes. |
| Pronta | O MP4 final está salvo. | Assistir no player e usar **Baixar MP4**. |
| Falha | Uma cena ou a montagem falhou. | Ler o motivo e o código mostrados. |

O MP4 da aula segue o mesmo perfil do vídeo avulso: H.264/AAC, 25 FPS, 1080×1920 ou 1920×1080, com faststart. A duração é a soma das cenas mais 3 s de abertura e 3 s de encerramento.

### Quando uma cena falha

Se uma cena falhar, a aula fica em **Falha** com a mensagem "A cena N falhou" e o motivo da cena. As outras cenas não são aproveitadas automaticamente. Corrija o que o motivo indicar (por exemplo, encurtar uma fala maior que o limite de áudio) e crie a aula de novo. Os códigos das cenas são os mesmos do vídeo avulso; `OUT_OF_MEMORY`, `WORKER_LOST`, `RENDER_FAILED` e `OUTPUT_INVALID` pedem verificação do operador. Uma falha da montagem com `INPUT_INVALID` indica imagem ou trilha que não pôde ser lida: troque o arquivo e gere de novo.

## Integração e responsabilidades de operação

Em **Usuários e chaves**, crie uma chave para cada integração; guarde o segredo mostrado uma única vez e revogue quando não for mais usado. Ao remover uma pessoa, revogue explicitamente as chaves emitidas por ela: remover acesso ao painel só encerra suas sessões. Uma chave não lê jobs criados por outra chave. Siga [o guia da API](../api/GUIA.md) para listar assets, criar/pollar e baixar com Bearer. Não compartilhe senha do painel com integrações.

Instalação, modelos, rede privada entre API/GPU, HTTPS, backup e recuperação são responsabilidade do procedimento em [INSTALACAO.md](INSTALACAO.md). Seeds, servidor E2E e mídia sintética servem apenas a testes locais isolados: nunca rode esses controles na instalação do cliente. A entrega final exige piloto na GPU, receita congelada com medições reais e aprovação das amostras pelo cliente; testes locais não substituem esse aceite.
