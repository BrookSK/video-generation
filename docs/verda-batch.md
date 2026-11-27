# EstudioIA com Verda Batch Jobs

A VPS mantém o PostgreSQL, a fila e os MP4. O controlador envia somente os
identificadores do vídeo e do lote para o endpoint de Batch Jobs. A réplica
reivindica esse vídeo pela API privada, reutiliza o render, entrega os arquivos
e encerra o processo. O PostgreSQL continua sendo a autoridade sobre publicação.
O cache padrão do deployment fica em `/data`, sem restaurar o disco de VM.

## Instalação em DEV

- Construa `infra/docker/verda-batch.Dockerfile` passando `WORKER_IMAGE`
  com o digest do worker CUDA compatível com a GPU. Publique o digest derivado
  em um registry alcançável pela Verda.
- Crie um deployment Batch Job para DEV com zero réplicas ociosas, uma réplica
  concorrente, porta 8000 e health check `/health`. Configure o cache padrão
  com escrita para o usuário da imagem. Defina a duração máxima da execução e
  o tempo máximo em fila. Configure a autenticação do endpoint de Batch Job.
- A réplica precisa de `WORKER_TOKEN`, `WORKER_ID` exclusivo de DEV e
  `API_URL` para o serviço privado da VPS. Quando o acesso for por túnel,
  monte a configuração da identidade SSH dedicada e host keys verificadas
  e defina `VERDA_BATCH_SSH_CONFIG`. O alias `avatar-api` deve incluir um
  `LocalForward` para a API. Restrinja a chave ao encaminhamento necessário.
  O endpoint público do painel continua bloqueando `/internal/v1`.
- Na VPS, inclua `docker-compose.verda-batch.yml` no Compose do ambiente.
  Informe o mesmo ID em `VERDA_WORKER_ID`. No arquivo privado apontado por
  `VERDA_ENV_FILE`, configure `VERDA_BATCH_DEPLOYMENT`, `VERDA_BATCH_TOKEN`
  e `VERDA_BATCH_HORIZON_SECONDS` com, no mínimo, o tempo máximo em fila mais
  a duração máxima da réplica, incluindo margem para a resposta do provedor.
- O disco é conferido contra o manifesto do worker. Uma cópia já preparada
  pode ser importada no mesmo layout antes do primeiro vídeo. O worker busca
  das fontes fixadas no manifesto os pesos públicos que faltarem. Receitas
  com insumos privados ou derivados exigem esses arquivos no cache.
- Para aceitar, use um vídeo pequeno com receita ativa. Confira o MP4 pela
  VPS, a saída da réplica e a contagem de zero réplicas no deployment. Um teste
  com provedor simulado cobre contratos locais, mas não mede tempo ou cobrança.

A parada segura aguarda os lotes enviados chegarem ao fim antes de desligar o
controlador. A migração 0007 cria somente a tabela de despachos. Para voltar a
uma imagem anterior, use a imagem nova para executar `alembic downgrade 0006`
depois de drenar o ambiente.
