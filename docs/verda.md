# GPU sob demanda na Verda

A API e o PostgreSQL ficam na VPS EstudioIA. O controlador detecta vídeos
na fila, solicita uma instância Verda com um disco de boot já preparado e
espera o sinal do worker. O worker usa a API interna para baixar os insumos
e enviar o MP4. O fluxo existente verifica o arquivo e confirma o job no
PostgreSQL. Ao esvaziar a fila, o controlador aguarda o período de
ociosidade, exclui a instância e conserva o disco. A Verda pode continuar
cobrando pelo armazenamento do disco desconectado.

## Configuração de cada ambiente

1. Prepare um disco de boot Verda com o runtime NVIDIA, os modelos e a
   imagem de worker por digest já carregada. Configure o boot para iniciar
   o túnel privado e o worker. Os serviços em `infra/systemd/` usam
   `/opt/estudioia` para o checkout, `/etc/avatar/worker.env` para o ambiente
   e `/etc/avatar/tunnel/ssh_config` para o alias `avatar-api`. Esse alias
   deve definir a chave privada dedicada, o arquivo de host keys verificadas
   e o redirecionamento de porta local para a API privada da VPS. Instale as
   unidades e habilite `avatar-verda-worker.service`. O usuário local
   `avatar-tunnel` deve poder ler apenas sua configuração e chave.
   No caso de Spot, confirme que a política de remoção do disco é
   `keep_detached`.
2. Use disco, identidade de worker e token de API interna próprios de cada
   ambiente. Configure a VPS com a credencial da API Verda em um arquivo de
   acesso restrito. O banco identifica o controlador pela identidade do
   worker. Uma cópia da base de outro ambiente não adota suas instâncias.
3. Adicione `docker-compose.verda.yml` ao Compose da VPS. Na configuração de
   Compose, informe `VERDA_WORKER_ID` e o caminho `VERDA_ENV_FILE`. No disco
   de boot, use o mesmo valor em `WORKER_ID` e a porta local do túnel em
   `API_URL`. A VPS continua responsável por preparo de avatar e montagem.
4. No arquivo secreto, defina `VERDA_CLIENT_ID`, `VERDA_CLIENT_SECRET`,
   `VERDA_BOOT_VOLUME_ID`, `VERDA_SSH_KEY_ID`, `VERDA_LOCATION`,
   `VERDA_INSTANCE_TYPE` e `VERDA_MAX_RUNTIME_SECONDS`. Use `VERDA_SPOT=true`
   com um disco preparado para Spot. O tempo de boot padrão é 900 segundos
   (`VERDA_BOOT_TIMEOUT_SECONDS`), com 60 segundos de ociosidade
   (`VERDA_IDLE_SECONDS`) e uma criação por hora
   (`VERDA_MAX_LAUNCHES_PER_HOUR`). O limite de tempo pode interromper um
   vídeo em andamento. Nesse caso o lease expira e a fila reprocessa o job.
5. Para validar DEV, envie um vídeo de uma receita ativa, confira seu
   download pela VPS e confirme que a instância desapareceu da Verda
   enquanto o disco ficou disponível. Repita em HOMOLOG antes de ativar
   a configuração em PROD.

## Recuperação

O controlador guarda a intenção antes de solicitar a criação. Se a resposta
sumir, ele procura o hostname persistido na Verda e só reconhece a instância
com o disco de boot esperado. Se o controlador indicar criação incerta,
consulte o pedido e o disco no console antes de liberar uma nova tentativa.
Se houver erro na exclusão, mantenha o controlador e a credencial ativos.
Ele volta a consultar a mesma instância e repete a exclusão enquanto ela
existir. Antes de desligar o serviço controlador, confirme que a instância
foi excluída.

## Reversão

Antes de ativar o controlador em outro ambiente, preserve o backup do
PostgreSQL e valide o retorno à versão anterior em DEV. Para reverter,
primeiro pare a admissão de novos vídeos e aguarde a exclusão confirmada da
instância na Verda. A imagem anterior da API conhece o Alembic até a
revisão `0005`. Antes de voltar a imagem, use a imagem que contém a revisão
`0006` para executar `alembic downgrade 0005`. O downgrade remove somente a
tabela de controle de GPU. Preserve os arquivos de vídeo e o disco de boot.
