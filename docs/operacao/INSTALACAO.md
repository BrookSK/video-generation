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
