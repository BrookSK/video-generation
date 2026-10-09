# Instalação no servidor GPU do cliente

Procedimento executado com o cliente, no servidor dele, a partir de um clone do repositório.
Todos os comandos rodam na raiz do clone. Nenhum token ou senha entra nos comandos abaixo.

Caminhos usados neste guia:

- `/srv/avatar/models`: pesos dos modelos (`MODELS_DIR`), montado em `/models` só leitura no piloto.
- `/srv/avatar/pilot`: entradas e saídas do piloto (`PILOT_DIR`), montado em `/pilot`.

## Pré-requisitos do servidor GPU

O servidor precisa de Ubuntu 24.04 x86_64, GPU NVIDIA e acesso `sudo`.

### Espaço em disco

- Pesos dos modelos: cerca de 123 GB em `/srv/avatar/models`.
- Durante o download, o maior arquivo ocupa até 20 GB extras como `.part`.
- Imagem `avatar-worker:pilot` e imagem CUDA base: reserve 40 GB no disco do Docker (`/var/lib/docker`).

Reserve pelo menos 200 GB livres. Confira com:

```bash
df -h /srv /var/lib/docker
```

### Driver NVIDIA

O CUDA 12.6 da imagem exige driver 560.28.03 ou mais novo.

```bash
sudo apt-get update
sudo ubuntu-drivers list --gpgpu
sudo ubuntu-drivers install --gpgpu nvidia:570-server
sudo reboot
```

Depois do reinício, `nvidia-smi` deve listar a GPU e a versão do driver.
Se a lista do `ubuntu-drivers` não trouxer a série 570, use a série mais nova que ela mostrar, desde que seja 560 ou maior.

### Docker Engine e Docker Compose

Instale pelo repositório oficial da Docker, não pelo pacote `docker.io` do Ubuntu:

```bash
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Para rodar `docker` sem `sudo`, adicione o operador ao grupo `docker` e abra uma nova sessão.
O grupo `docker` equivale a acesso de root no servidor. Se o cliente preferir, rode os comandos com `sudo`.

```bash
sudo usermod -aG docker "$USER"
```

### NVIDIA Container Toolkit

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Checagem do host

```bash
bash infra/scripts/gpu-host-check.sh
```

O script confere, nesta ordem: Ubuntu 24.04, driver 560.28.03 ou mais novo, Docker, Docker Compose, `nvidia-ctk`, runtime `nvidia` no Docker e `nvidia-smi` dentro de um contêiner com a imagem CUDA base do worker.
Ele para no primeiro item que falhar e explica o motivo.
No fim, mostra um resumo com o nome da GPU, a VRAM total e o driver vistos de dentro do contêiner.
Guarde essa saída como evidência da instalação.

### Ambiente GPU do provedor em contêiner (2026-10-08)

O acesso entregue pelo cliente é Ubuntu 24.04 em um contêiner Sysbox, com
NVIDIA L40S (46.068 MiB), driver 580.159.03, limite de 8 GB de RAM e quota
equivalente a 4 CPUs. Os 128 processadores visíveis não são a quota disponível.
O driver já vem do provedor: não reinstale o driver nem reinicie o host físico.

Docker 29.8.2, Compose 5.6.0 e NVIDIA Container Toolkit 1.20.1 foram instalados.
O runtime legado falhou ao configurar os dispositivos neste ambiente aninhado.
O modo CDI oficial resolveu a exposição da GPU, mantendo o `--gpus all` usado
pelo projeto:

```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
sudo nvidia-ctk config --in-place --set nvidia-container-runtime.mode=cdi
sudo nvidia-ctk runtime configure --runtime=docker --set-as-default
sudo systemctl restart docker
sudo bash infra/scripts/gpu-host-check.sh
```

O último comando passou no servidor. Regenere a especificação CDI quando o
provedor trocar a GPU ou o driver. Referência:
https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html .
Não há medição de RAM do pipeline nem aprovação de qualidade nesta checagem.

A primeira construção falhou em `uv python install` com `No file descriptors
available (os error 24)`: os contêineres tinham limite soft de 1024 arquivos.
O build completo passou depois de configurar `nofile` soft 65536 e hard 524288,
sem desativar a compilação de bytecode nem alterar versões ou lockfiles.
O servidor usa `/etc/systemd/system/docker.service.d/avatar-limits.conf`
com `[Service]` e `LimitNOFILE=65536:524288`. Em `/etc/docker/daemon.json`,
o objeto `default-ulimits` contém
`"nofile": {"Name": "nofile", "Hard": 524288, "Soft": 65536}`.
Preserve as demais chaves do daemon, incluindo as redes configuradas pelo
provedor e o runtime NVIDIA. Valide o JSON com `sudo dockerd --validate`,
rode `sudo systemctl daemon-reload` e reinicie somente o serviço Docker.

Os runtimes executaram multiplicação de matrizes na L40S, com resultado
conferido, usando `--network none`: TTS com PyTorch 2.6.0+cu126 e avatar com
PyTorch 2.4.1+cu121. No avatar, `flash_attn 2.7.4.post1` e
`xformers 0.0.28.post1` importaram sem recompilação. Isso comprova CUDA e as
extensões da imagem, não a qualidade, a duração ou a memória do piloto.

O disco raiz tem cerca de 89 GiB livres e não comporta os 123 GB de pesos.
O mount de `/var/lib/docker` expõe cerca de 659 GiB livres. Neste ambiente,
os modelos ficam em um volume Docker, usando o caminho real do volume nos
comandos e nas montagens já existentes:

```bash
sudo docker volume create avatar_models
export MODELS_DIR="$(sudo docker volume inspect --format '{{.Mountpoint}}' avatar_models)"
export PILOT_DIR=/srv/avatar/pilot
sudo env MODELS_DIR="$MODELS_DIR" PILOT_DIR="$PILOT_DIR" \
  docker compose -f infra/compose/docker-compose.pilot.yml build
sudo env MODELS_DIR="$MODELS_DIR" bash infra/scripts/models-pull.sh
```

Não remova o volume nem execute `docker volume prune`. O espaço exibido pertence
ao filesystem do provedor; quota, persistência após destruir a instância e backup
externo precisam ser confirmados com ele. O limite de 8 GB de RAM permanece:
a geração só será considerada viável após o piloto real na P06, sem reduzir qualidade
ou congelar a receita para contornar falta de memória.

### Estado da retomada e ajuste autorizado (2026-10-09, observação UTC)

A preparação do host (P02/T12) foi comprovada e concluída. A imagem do worker
foi construída e seus dois runtimes executaram cálculos CUDA. Seu digest está
registrado em `RECIPE-v1.json`, que permanece em `draft`.
Digest da imagem identifica o build já observado; sua presença não transforma
o rascunho em receita aprovada. `recipe validate --frozen` continua recusando
a receita sem medições e avaliação do piloto. A suíte valida essas ausências
em fixtures isoladas, sem exigir que o JSON real omita um digest já comprovado.

A validação exige buckets de ambos os formatos, inclusive quando a seção estiver
vazia. A receita frozen exige medições `tts`, `render` e `finalize` por formato:
o estágio `avatar` do relatório do piloto corresponde a `render` na receita.
Não copiar apenas a finalização nem preencher tempos/VRAM não observados.
O adaptador aceita caminhos relativos ao diretório do processo chamador e os
resolve antes de entrar no diretório isolado do gerador (`save_audio/` permanece lá).

O download dos modelos foi interrompido com
`Error waiting for container: Canceled: grpc: the client connection is closing:
context canceled`. Depois, o acesso SSH fornecido pelo cliente recusou conexão;
a mesma recusa foi observada em checagem TCP, tanto da origem local quanto do servidor CPU. Não foi possível
inspecionar o servidor depois da interrupção. A causa, os arquivos ainda
persistidos e a disponibilidade da imagem após restabelecer a instância são
desconhecidos. Não há evidência para atribuir a interrupção à RAM.

O download completo, a segunda execução sem downloads e a geração de vídeos
não foram comprovados: P02/T13 continua pendente, assim como as provas de
piloto/congelamento de T14/T15. Suas obrigações serão replanejadas na P06 após
reaprovação do pacote; o ajuste não as declara executadas. Quando o cliente
restabelecer o acesso GPU, confira o volume e a imagem, depois reexecute
`models-pull.sh` com o `MODELS_DIR` do volume. O comando revalida os hashes dos
arquivos existentes e baixa novamente os ausentes ou inválidos; não dispense
essa conferência.

Para as provas de piloto/congelamento na P06 falta uma imagem de pessoa, com
ombros visíveis, e o registro de autorização de uso. A foto pública usada na
P03 era uma fixture, não um avatar autorizado do cliente. O avaliador precisa
examinar as amostras antes de congelar a receita. Não invente sua aprovação.

O usuário selecionou **“Autorizar o ajuste do Astra”**, ciente do risco de
retrabalho. A decisão autoriza desenvolvimento real local da P04/P05 antes da
calibração GPU, não aprova amostras nem gastos. A P02 fornece `render_runtime`
(código, schemas, adaptadores, composição, finalização e ferramentas de download
e piloto); a P04 o consome e a P05 segue a P04. Fixtures ficam restritas aos
testes, sem vídeo artificial apresentado como produto. `RECIPE-v1.json`
permanece `draft`; o carregamento pela API continua exigindo `frozen`, e a
ausência de receita vigente deve retornar erro explícito, sem receita fictícia.
Os contratos concluídos da P01/P03 e as definições e provas da P02/T01–T12
permanecem preservados pela reaprovação/rebind, sem edição manual de status.

Na retomada, o acesso ao servidor CPU e o login/logout do painel foram
verificados; a stack CPU foi parada em seguida. Esse acesso não restabeleceu
o endpoint GPU e não comprova geração de vídeo, piloto ou memória disponível
para o pipeline completo.

A P06 consome `render_runtime`, calibra e congela `render_recipe` e entrega
`installed_release`. Nessa fase final permanecem obrigatórios: pesos completos
com hashes e segunda execução sem downloads; piloto 9:16 e 16:9 com materiais
autorizados, medições de VRAM e tempos frio/quente, qualidade, sincronia e
movimento além da boca; piloto isolado sem rede externa, interfaces só `lo`;
pacote inicial autorizado de 2 avatares e 4 cenários; testes dos consumidores
reais da P04/P05 no servidor, incluindo perfil de exportação, falhas,
recuperação e ausência de conexões externas além da API interna.

A entrega final também exige instalação reproduzível em diretório limpo,
veredito do cliente na matriz de 2 avatares, 4 cenários e 2 formatos, amostras de
30 s e no limite aprovado, uma pessoa para publicar manualmente no Instagram
e uma pessoa da equipe para provar autonomia. HTTPS e a revogação dos acessos
temporários, seguida de novo job `ready`, pertencem à instalação final,
não à checagem do host. Antecipar o desenvolvimento local não reduz nenhum
aceite; ajustes dos consumidores após a calibração continuam sendo um risco.

Na topologia de duas VPS, API, PostgreSQL e `/data` permanecem na VPS CPU/API;
o worker GPU e `/models` ficam na VPS GPU. A P06 verifica o acesso autorizado
e a conexão entre ambas: o supervisor usa HTTP interno `/internal/v1` com token
próprio, por túnel SSH ou rede privada autenticada, para claim, heartbeat e
upload. Não exponha `/internal/v1` pelo Caddy nem o banco; o worker não recebe
credencial de banco nem acesso direto aos volumes da API. `network_mode: none`
e interfaces só `lo` continuam obrigatórios no piloto isolado, não no supervisor
que precisa dessa comunicação interna. Nenhuma conexão de controle autoriza
uso de SaaS de inferência ou gastos.

## Pesos dos modelos

### Imagem do worker

O download roda dentro da imagem `avatar-worker:pilot`. Construa a imagem antes:

```bash
export MODELS_DIR=/srv/avatar/models
export PILOT_DIR=/srv/avatar/pilot
docker compose -f infra/compose/docker-compose.pilot.yml build
```

O Compose exige `MODELS_DIR` e `PILOT_DIR` definidos, mesmo no `build`.
Em vez de `export`, os dois podem ficar em `infra/compose/.env` (modelo em `infra/compose/.env.example`).
O `models-pull.sh` não lê esse arquivo, então exporte `MODELS_DIR` no shell antes de rodá-lo.

### Download verificado

`MODELS_DIR` precisa ser caminho absoluto, existir e ser gravável pelo usuário que roda o script.
O contêiner roda com o uid e o gid desse usuário.

```bash
sudo mkdir -p /srv/avatar/models
sudo chown "$(id -u):$(id -g)" /srv/avatar/models
MODELS_DIR=/srv/avatar/models bash infra/scripts/models-pull.sh
```

O script:

- confere `docs/models/MODEL_MANIFEST.json` contra a política de licenças e hashes antes de baixar qualquer coisa;
- baixa cada arquivo dos componentes `model` para `/srv/avatar/models/<id do componente>/<path>`;
- grava primeiro em `<arquivo>.part` e só renomeia quando o SHA-256 e o tamanho batem com o manifesto;
- com hash ou tamanho divergente, apaga o `.part`, nomeia o arquivo e sai com código 1.

O manifesto é montado só leitura dentro do contêiner. Nenhum token é usado: os repositórios são públicos.

### Reexecução

Rodar `models-pull.sh` de novo é seguro. Arquivo já presente com hash correto aparece como `já conferido` e não é baixado.
Arquivo ausente, incompleto ou divergente é baixado de novo.
A segunda execução completa termina com `0 baixado(s)` e código 0.
Ela ainda relê todos os arquivos para calcular o SHA-256, então leva alguns minutos.

## Piloto

O piloto e o congelamento da receita são obrigações finais da P06; as
ferramentas implementadas na P02 não equivalem a essa execução ou ao aceite.

O piloto roda com `network_mode: none`, a GPU reservada e `/models` só leitura.
A receita e o manifesto usados são os de `/app/docs/models`, copiados para a imagem no `build`.
Depois de alterar `docs/models`, construa a imagem de novo.

### Diretório do piloto

O contêiner roda como o usuário `app` (uid 10001). `PILOT_DIR` precisa ser gravável por esse uid.

```bash
sudo mkdir -p /srv/avatar/pilot/in /srv/avatar/pilot/out
sudo cp avatar.png fala-30s.txt /srv/avatar/pilot/in/
sudo chown -R 10001:10001 /srv/avatar/pilot
```

`avatar.png` é a imagem autorizada pelo cliente. `fala-30s.txt` é a fala em UTF-8.

### Execução

Passe o digest da imagem em `WORKER_IMAGE_DIGEST` para que o relatório do piloto o registre:

```bash
export MODELS_DIR=/srv/avatar/models
export PILOT_DIR=/srv/avatar/pilot
docker compose -f infra/compose/docker-compose.pilot.yml run --rm \
  -e WORKER_IMAGE_DIGEST="$(docker image inspect --format '{{.Id}}' avatar-worker:pilot)" \
  pilot \
  --recipe /app/docs/models/RECIPE-v1.json \
  --manifest /app/docs/models/MODEL_MANIFEST.json \
  --models /models \
  --image /pilot/in/avatar.png \
  --background '#1f2937' \
  --composition '{"9:16": {"scale": 0.8, "x": 0.5, "y": 1.0}, "16:9": {"scale": 0.9, "x": 0.5, "y": 1.0}}' \
  --text-file /pilot/in/fala-30s.txt \
  --voice feminina \
  --runs 2 \
  --out /pilot/out/fala-30s
```

Sem `--formats`, o piloto gera 9:16 e 16:9. Com `--runs 2`, a primeira execução é fria e a segunda quente.
Os vídeos e o `report.json` ficam em `/srv/avatar/pilot/out/fala-30s`.
O relatório traz tempo e pico de VRAM por etapa e as interfaces de rede vistas no contêiner, que devem ser só `lo`.
