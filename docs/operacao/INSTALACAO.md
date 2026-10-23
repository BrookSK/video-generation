# Instalação nas VPS API e GPU do cliente

Procedimento executado com o cliente, no servidor dele, a partir de um clone do repositório.
Todos os comandos rodam na raiz do clone. Nenhum token ou senha entra nos comandos abaixo.

Caminhos usados neste guia:

- `/srv/avatar/models`: pesos dos modelos (`MODELS_DIR`), montado em `/models` só leitura no piloto.
- `/srv/avatar/pilot`: entradas e saídas do piloto (`PILOT_DIR`), montado em `/pilot`.

## Pré-requisitos do servidor GPU

O servidor precisa de Ubuntu 24.04 x86_64, GPU NVIDIA e acesso `sudo`.

### Espaço em disco

- Pesos dos modelos: cerca de 124 GB em `/srv/avatar/models`.
- Durante o download, o maior arquivo ocupa até 20 GB extras como `.part`.
- Imagem `avatar-worker:pilot` e imagem CUDA base: reserve 40 GB no disco do Docker (`/var/lib/docker`).

`models/` é excluído do contexto de build por `.dockerignore`; pesos e WAVs são
fornecidos separadamente pelo volume `/models`, não embutidos na imagem.

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
foi construída e seus dois runtimes executaram cálculos CUDA. O digest desse
build chegou a ser registrado em `RECIPE-v1.json`; na P07, `worker_image.digest`
voltou a `null`, porque aquele build não contém as correções da P07. A P06
publica a imagem do commit entregue na P07 e registra o novo digest. A receita
permanece em `draft`, e um digest não transforma o rascunho em receita
aprovada. Após a T05, o draft aponta para o digest efetivamente verificado.
`recipe validate --frozen` continua recusando seu status draft e a ausência de
medições/avaliação do piloto.

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
não foram comprovados. As obrigações originalmente P02/T13–T15 foram
transferidas à P06 pelo pacote reaprovado; P02 local concluída não as declara
executadas. Quando o cliente
restabelecer o acesso GPU, confira o volume e a imagem, depois reexecute
`models-pull.sh` com o `MODELS_DIR` do volume. O comando revalida os hashes dos
arquivos existentes e baixa novamente os ausentes ou inválidos; não dispense
essa conferência.

Na retomada P06 de 2026-10-14, DEC-005 autoriza reutilizar os dois avatares e
quatro cenários sintéticos existentes em
`~/Developer/video-generation-amostras/materiais-sinteticos/`, com prompts e
hashes registrados. Essa decisão supera a restrição de insumos da DEC-003;
não faltam novas fotos nem nova autorização desses materiais para o piloto.
A foto pública da P03 continua sendo fixture. O avaliador precisa examinar as
novas amostras antes de congelar a receita; autorização de uso não é aprovação
de qualidade, tempos ou assinatura humana.

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

## GPU Verda (A100 80 GB)

A partir da P07, a calibração usa uma instância da Verda (antiga DataCrunch)
com NVIDIA A100 80 GB. O teste técnico de 2026-10-14 rodou numa A100-SXM4-80GB
da localização FIN-01, com materiais sintéticos aceitos só para teste, e não
aprova qualidade, tempos nem receita. O pico de VRAM do avatar nesse teste,
de 48.776 a 50.776 MiB, passa dos 46.068 MiB da L40S descrita acima.

Publicar a imagem do commit entregue na P07, medir na GPU, rodar o piloto e
obter o aceite ficam na P06. Este guia não traz automação de nuvem: criar,
desligar ou excluir instância e volume são ações manuais no console da Verda e
dependem de autorização do cliente; exclusão e retomada estão descritas abaixo.
Na instância, rode `bash infra/scripts/gpu-host-check.sh` e instale, pelos
passos acima, só o que ele apontar como ausente.

### Candidato P06 publicado e verificado (2026-10-15)

O worker foi construído em Linux amd64 a partir de
`50fc974ceadff502694522e77a5704e2cbed4c8d` (correção D001 do TTS) e publicado
no registro do cliente. Use a identidade verificada, sem trocar pelo Image ID
ou por uma reconstrução:

```bash
WORKER_IMAGE=vccr.io/5e20534f-f96c-42fb-8a52-deb4f7e28efc/avatar-worker@sha256:f2814d283009ef7ebcb941367b531631e5008623ef2667cc92eadd8d1c4f06ff
docker pull "$WORKER_IMAGE"
docker tag "$WORKER_IMAGE" avatar-worker:pilot
```

O candidato D001 foi puxado por digest na A100 80 GB e executou o TTS real sem
rede. Uma geração sem EOS foi recusada antes de decodificar/publicar; a mesma
reprodução publicava áudio incompleto no candidato anterior. O manifesto registra
a política v3 aplicada ao Chatterbox 0.1.7, com hashes do patch e do aplicador.
Isso não prova literalidade, qualidade humana nem capacidade de fala de 60 s:
o orçamento de 1000 tokens permanece e uma amostra masculina real foi recusada
por esgotá-lo sem EOS. Não aumentar o orçamento silenciosamente.

A prova T05 de 2026-10-14 pertence ao candidato anterior `ec4fad2d…`, fonte
`d031c876…`: CUDA dos dois runtimes, 40 arquivos conferidos sem downloads,
referências de voz e claim/presença/upload em preflight privado isolado.
Não atribuir essa prova histórica à imagem nova.

Preview real D001 em 2026-10-15: feminina/escritório/9:16, uma execução fria,
25,96 s (não 30 s), 649 frames, H.264 1080×1920/25 fps e AAC 48 kHz.
O avatar levou 2304,575 s, pico 49328 MiB; total computado 2363,666 s
(91,05 s de computação por segundo de vídeo). Rede somente `lo`, Perth detectado.
MP4 copiado e SHA-256 conferido, FFprobe e grade visual observados. Isso não
aprova sincronia/fala literal nem o desempenho; repetição, outras vozes/formatos,
60 s, 720p e avaliação C1–C7 seguem pendentes. A GPU e o clone temporários foram
excluídos após a cópia; o volume original permaneceu detached.

`RECIPE-v1.json` segue `draft`, sem aprovação humana ou congelamento.
DEC-005 autoriza os seis materiais existentes; domínio HTTPS público, túnel
definitivo restrito e aceite permanecem requisitos das etapas seguintes.

### Perfil da receita draft

`docs/models/RECIPE-v1.json` continua `draft`, com o perfil
`480p-bf16-a100-lightx2v4`:

- bf16 sem quantização: `quant: null` e `num_persistent_param_in_dit: null`;
- LoRA lightx2v (componente `lightx2v-lora`, arquivo
  `Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors`) com escala 1.0;
- 4 passos (`sample_steps`), guia de texto 1.0 e guia de áudio 2.0;
- sem prompt negativo (`negative_prompt: null`): o `generate_infinitetalk.py`
  fixado não tem esse argumento.

O estágio de avatar repassa esses valores explicitamente ao gerador, sem
depender dos defaults dele. A validação da receita e o próprio estágio recusam
perfil quantizado (fp8 ou int8) antes de iniciar o gerador: o optimum-quanto
compilaria uma extensão CUDA na primeira inferência, e a imagem não tem `nvcc`.
Não instale toolchain, não amplie permissões e não troque de perfil para
contornar a recusa. GPU com menos de 80 GB pede outro perfil, aprovado numa
receita nova.

No teste de 2026-10-14, só com execuções frias, a geração com lightx2v levou de
99,7 a 111,9 s de computação por segundo de vídeo, quase tudo no avatar (cerca
de 50 min de GPU para um vídeo de 30 s), com pico de 48.776 a 50.776 MiB no
avatar. Sem a LoRA, com 40 passos, cada passo levou cerca de 71 s. Use esses
números só para estimar custo: não são garantia, e a P06 mede de novo, frio e
quente.

### Pesos novos

O manifesto ganhou `lightx2v-lora` (316.822.496 bytes) e `kokoro-82m` (cerca de
330 MB, fontes das referências de voz). O código que baixa e confere os pesos
roda dentro da imagem `avatar-worker:pilot`, e uma imagem anterior à P07 recusa
o manifesto novo. Construa e publique a imagem do HEAD entregue na P07 sob a
conta do cliente, conforme *Construir e registrar imagens reais*, antes do
download e do piloto. Puxe o digest registrado e aponte `avatar-worker:pilot`
para ele; `models-pull.sh` roda essa imagem. Arquivos já conferidos são pulados
e só os novos são baixados. A segunda execução precisa terminar com
`0 baixado(s)`. Preserve também os pesos fp8 do manifesto completo, embora o
draft bf16 não os use.

### Custo: desligar não para a cobrança

Na Verda, instância em **shutdown continua cobrando** o preço da GPU. O
shutdown serve para manutenção e para anexar ou desanexar volumes, não para
economizar ([Shutdown and Delete](https://docs.verda.com/cpu-and-gpu-instances/shutdown-hibernate-and-delete/)).
O saldo é pré-pago e descontado em blocos de 10 minutos. Com saldo zerado, a
Verda descontinua as instâncias e apaga os volumes, que podem ser restaurados
por até 96 horas ([Pricing and Billing](https://docs.verda.com/welcome-to-verda/pricing-and-billing/)).
GPU e storage são custos do cliente.

O único jeito de parar o custo de compute é excluir a instância. Isso exige
autorização pontual do cliente para aquela exclusão, registrada com quem
autorizou, data e hora; autorização anterior ou genérica não vale. Sem ela,
não exclua nada e avise o cliente de que a instância segue cobrando.

Com a autorização:

1. Espere o piloto terminar e pare o worker, se estiver rodando, com o mesmo
   comando Compose usado para subi-lo, trocando `up -d` por `stop`.
2. Na instância, rode `sync` para gravar no disco o que estiver em buffer.
3. Registre o nome do volume, a localização e o fingerprint da host key da
   instância (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`).
4. No console da Verda, use **Delete instance** e não marque nenhum volume na
   lista de storage (o padrão é nenhum marcado). Exclua só a instância.
5. Confira no console que o volume ficou desanexado (detached). Ele guarda o
   que foi gravado no disco da instância, como pesos, referências de voz,
   imagens Docker e saídas do piloto, e **o storage continua cobrado**
   enquanto o volume existir, mesmo sem instância.

No teste de 2026-10-14, a instância foi excluída depois do `sync` e o volume
`OS-fHuXBon4` ficou desanexado em FIN-01. Mantenha saldo para o storage enquanto
o volume existir: com saldo zerado ele é apagado. Excluir o volume é outra
decisão do cliente e não faz parte deste procedimento.

### Retomada com o volume preservado

DEC-005 já autoriza criar a GPU e usar os seis materiais existentes; não repetir
esses pedidos. Após recusa de capacidade em FIN-01, a DEC-006 autoriza esta
janela em A100 80 GB **spot FIN-03**, com o clone `P06-piloto-FIN03` (250 GiB)
do volume original `OS-fHuXBon4`, que deve permanecer preservado em FIN-01.
Usar apenas o saldo existente, sem recarga, mantendo reserva de **US$1**.
Salvar as amostras/evidências e executar `sync` antes de excluir somente a nova
instância `avatar-p06-pilot-ec4fad2` e o clone temporário. Não excluir o original
nem publicar externamente. Confirmar estado, preço, IP e host key no console;
aliases/IPs anteriores não provam acesso atual.

1. Para esta janela, usar o clone desanexado `P06-piloto-FIN03` como volume OS
   da A100 spot em FIN-03, com **No deletion / Keep all storage** em caso de
   interrupção. A instância criada tem ID `bde3697c-2d12-499a-95cd-77c435c2fc78`;
   o clone, `e5f8c4cb-b83a-4bce-83d6-9e77b6b6f028`. Não anexar/excluir o
   original para substituir essa execução.
2. **IP e host key:** anote o IP novo e atualize o SSH config do operador. No
   primeiro acesso, compare o fingerprint oferecido com o registrado. Se mudou,
   confirme-o por um canal confiável antes de aceitar; nunca desative a
   verificação de host key. Depois, remova a entrada do IP antigo com
   `ssh-keygen -R <ip antigo>`.
3. **Disco:** confira que o volume é o disco da instância e o espaço livre:

   ```bash
   lsblk
   df -h /srv/avatar /var/lib/docker
   ```

4. **Host e GPU:** `bash infra/scripts/gpu-host-check.sh`.
5. **Imagem atual por digest:** se só existir uma imagem anterior à P07,
   construa/publique o HEAD entregue na P07 com autorização operacional e
   registre o digest real antes de baixar pesos ou rodar o piloto. A referência
   publicada precisa aparecer em

   ```bash
   docker image inspect --format '{{json .RepoDigests}}' avatar-worker:pilot
   ```

   Se não aparecer, puxe a imagem pela referência registrada e marque-a como
   `avatar-worker:pilot`, com `WORKER_IMAGE` igual a essa referência:
   `docker pull "$WORKER_IMAGE"` e `docker tag "$WORKER_IMAGE" avatar-worker:pilot`.
   Não reconstrua a imagem para substituí-la.

6. **Pesos:** `MODELS_DIR=/srv/avatar/models bash infra/scripts/models-pull.sh`.
   Com os componentes novos, a primeira execução pode baixar arquivos; depois,
   repita e exija `0 baixado(s)`.
7. **Referências de voz:** copie os dois WAVs registrados e rode a conferência
   de *Referências de voz* com `REFS_MODELS=/srv/avatar/models`.

## Supervisor e API em duas VPS

Configuração disponível no código; instalação e conectividade reais serão
comprovadas na P06. Em ambas, use o mesmo release e crie `infra/compose/.env`
com permissão `0600`. O token interno deve ser igual nos dois servidores.
Só a VPS API recebe `POSTGRES_PASSWORD`; não copie essa senha para a GPU.

Na VPS API:

```bash
docker compose -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.cpu.yml \
  -f infra/compose/docker-compose.api.yml up -d --build --wait
```

API e PostgreSQL usam os volumes existentes. O bind de API é somente
`127.0.0.1:8000`; o painel usa `127.0.0.1:8088` até a publicação HTTPS final.
O worker CPU fica no perfil opcional `cpu-assets`, desativado por padrão:
o worker GPU prepara avatares e gera vídeos. Não ative um consumidor CPU
sem conferir seus pesos e a preparação real. O Caddy continua bloqueando
`/internal/v1`; não publique a porta 8000 em `0.0.0.0`.

Na VPS GPU Linux, configure uma identidade SSH autorizada para o servidor API,
com host key verificada. Restrinja o encaminhamento dessa identidade a
`127.0.0.1:8000` (`PermitOpen`); não desative a verificação de host key.
O alias `avatar-api` abaixo pertence ao SSH config do operador:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -L 127.0.0.1:18000:127.0.0.1:8000 avatar-api
```

Mantenha o túnel sob supervisão do sistema com essa identidade, antes de iniciar
o worker. Reinicie-o se cair. Em outro terminal da GPU:

```bash
docker compose -f infra/compose/docker-compose.worker.yml up -d --build
docker compose -f infra/compose/docker-compose.worker.yml logs --follow worker
```

`network_mode: host` é Linux e permite alcançar o túnel local em
`http://127.0.0.1:18000` (`API_URL`). Não monta `/data` nem acessa PostgreSQL.
`MODELS_DIR` é o caminho absoluto no host, montado em `/models` somente leitura;
o processo usa os runtimes copiados para a imagem. O CMD inicia
`python -m avatar_worker.supervisor`, uma tarefa por vez. Não use a variante
CPU para gerar vídeo. O piloto isolado continua usando rede `none`.

Cheque `/readyz` diretamente na API interna: espera JSON com banco e storage
ok, não HTML do painel. Com uma chave pública, `GET /api/v1/worker-status`
devolve `last_heartbeat_at` ou `null`. Claim de vídeo atualiza esse registro
inclusive com fila vazia; polling somente `asset_prepare` não o atualiza.
Timestamp antigo não é garantia de worker disponível. O aviso de ausência
superior a dois minutos pertence ao painel da P05.

### Geração, arquivos e recuperação

Carregue somente uma receita realmente congelada após o piloto da P06.
Sem receita vigente a API recusa criação; draft ou frozen incompleta não
executam inferência no worker. O claim transporta a receita vinculada ao job,
voz, arquivos, cor e enquadramento: mudar a receita vigente não muda esse job.

Etapas: `compose`, `tts`, `render`, `finalize`, `upload`. O TTS encerra antes
de iniciar o avatar. O WAV real precisa respeitar o limite; o final é H.264,
yuv420p, 25 fps e AAC 48 kHz, 1080×1920 ou 1920×1080, com faststart.
Cada tentativa guarda `manifest.json`, `audio.wav`, `render.mp4` e `final.mp4`
no storage da API. O manifesto contém receita, SHA-256 do texto (não seu
conteúdo), hashes da mídia, tempos medidos e VRAM quando observada; desconhecida
permanece `null`. Consultas públicas não expõem caminhos internos.

Heartbeat perdido/obsoleto cancela o grupo de subprocessos antes de publicar.
O varredor reencaminha leases vencidos até três tentativas; a tentativa antiga
recebe `409 STALE_ATTEMPT`. Upload reabre o arquivo em cada retry e complete
confere tamanho e SHA-256 antes de marcar `ready`. Não altere arquivos de
tentativa manualmente. Falhas permanentes, incluindo OOM ou saída inválida,
ficam `failed`; diagnósticos de inferência não são enviados como erro público.
Consulte job e logs pelo identificador, sem registrar token ou texto da fala.

### Limite das provas locais

SCN-009 exercita HTTP, PostgreSQL migrado, supervisor, arquivos e FFmpeg reais,
nos dois formatos, com doubles apenas nas fronteiras TTS/avatar e receita
isolada de teste. Não comprova inferência GPU, qualidade, tempo, memória,
conexão entre as VPS nem aprovação do cliente. Esses gates permanecem P06;
nunca carregue fixtures como receita de produção.


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
- com hash ou tamanho divergente, apaga o `.part`, nomeia o arquivo e sai com código 1;
- não baixa componentes `derived`, como as referências de voz (veja *Referências de voz*).

O manifesto é montado só leitura dentro do contêiner. Nenhum token é usado: os repositórios são públicos.

### Reexecução

Rodar `models-pull.sh` de novo é seguro. Arquivo já presente com hash correto aparece como `já conferido` e não é baixado.
Arquivo ausente, incompleto ou divergente é baixado de novo.
A segunda execução completa termina com `0 baixado(s)` e código 0.
Ela ainda relê todos os arquivos para calcular o SHA-256, então leva alguns minutos.

## Referências de voz

As vozes `feminina` e `masculina` usam referências sintéticas distintas,
geradas offline em CPU pelo Kokoro-82M pt-BR (`lang_code='p'`) com os presets
`pf_dora` e `pm_alex`. Ninguém é gravado ou clonado. Código, pesos e presets
são Apache-2.0, com revisões fixadas no manifesto (`kokoro-code` e
`kokoro-82m`). O TTS de produção continua o Chatterbox; o Kokoro só prepara as
referências.

Os WAVs ficam fora do Git. O componente `kokoro-voice-references` (kind
`derived`) do manifesto registra SHA-256, tamanho e proveniência de cada
arquivo, e `tts.voices` da receita aponta `feminina` para `pf_dora.wav` e
`masculina` para `pm_alex.wav`. O TTS confere o SHA-256 a cada uso e recusa
referência ausente ou divergente.

Os bytes registrados foram gerados em macOS arm64 (`parameters.platform` da
proveniência). Gerar de novo na mesma plataforma, com o mesmo `uv.lock`,
reproduz os mesmos bytes. Em outra plataforma os bytes podem mudar e a
conferência falha: use a cópia registrada. Registrar WAVs novos exige atualizar
manifesto e receita enquanto ela for `draft`; receita congelada nunca muda.

### Runtime isolado

A ferramenta `apps/worker/runtimes/voices/voice_references.py` roda num runtime
próprio, com `pyproject.toml` e `uv.lock` separados do worker e dos runtimes de
TTS e avatar: Python 3.12, torch 2.6.0 só para CPU e kokoro no commit do
manifesto. O runtime instala em macOS arm64 e Linux x86_64. O espeak-ng, usado
na fonetização, vem embutido na wheel `espeakng-loader` 0.2.4 fixada no lock;
não instale pacote de sistema. O espeak-ng é GPL-3.0 e só roda nesta ferramenta
offline: não entra na imagem do worker, no pipeline de produção nem no
manifesto.

Na máquina do operador, na raiz do clone, prepare o runtime e as fontes (estes
dois comandos usam a rede):

```bash
uv sync --frozen --directory apps/worker/runtimes/voices
uv run --frozen --project apps/worker python -m avatar_worker.manifest pull \
  --policy docs/models/MODEL_MANIFEST.json --dest models --component kokoro-82m
```

O segundo comando baixa as fontes para `models/kokoro-82m/`, conferindo
tamanho e SHA-256 de cada arquivo. O diretório `models/` fica fora do Git.

### Gerar offline em CPU

No macOS, a geração roda com a rede negada pelo sistema:

```bash
sandbox-exec -p '(version 1)(allow default)(deny network*)' \
  uv run --frozen --offline --project apps/worker/runtimes/voices \
  python apps/worker/runtimes/voices/voice_references.py \
  --manifest docs/models/MODEL_MANIFEST.json --models models
```

`--offline` impede o uv de baixar pacotes. A ferramenta também força o Hugging
Face offline e recusa qualquer conexão de socket. Antes de carregar o modelo,
ela confere tamanho e SHA-256 das fontes; fonte ausente ou divergente sai com
código 1 sem gravar nada. Em Linux x86_64, rode o mesmo comando sem a linha do
`sandbox-exec`.

No sucesso, a ferramenta grava `pf_dora.wav` e `pm_alex.wav` (PCM 16 bits,
mono, 24 kHz) em `models/kokoro-voice-references/`, avisa
`referências gravadas em models/kokoro-voice-references` e imprime no stdout o
componente `derived`, com hashes e proveniência. Ela sobrescreve os WAVs dessa
pasta: se a cópia registrada estiver ali, guarde-a antes de gerar em outra
plataforma.

### Conferir e copiar para `/models`

A conferência compara cada voz da receita com o manifesto e com o arquivo. Na
máquina do operador, use `REFS_MODELS=models`; no servidor GPU, o diretório dos
pesos (`REFS_MODELS=/srv/avatar/models`). Rode na raiz do clone:

```bash
REFS_MODELS=models
python3 - "$REFS_MODELS" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

models = Path(sys.argv[1])
manifest = json.loads(Path("docs/models/MODEL_MANIFEST.json").read_text(encoding="utf-8"))
recipe = json.loads(Path("docs/models/RECIPE-v1.json").read_text(encoding="utf-8"))
registered = {
    f"{component['id']}/{entry['path']}": entry
    for component in manifest["components"]
    if component["kind"] == "derived"
    for entry in component["files"]
}
failed = False
for name, voice in recipe["tts"]["voices"].items():
    entry = registered.get(voice["path"])
    path = models / voice["path"]
    data = path.read_bytes() if path.is_file() else b""
    ok = (
        entry is not None
        and entry["sha256"] == voice["sha256"]
        and len(data) == entry["size"]
        and hashlib.sha256(data).hexdigest() == voice["sha256"]
    )
    print(f"{name}: {path} {'ok' if ok else 'AUSENTE OU DIVERGENTE'}")
    failed = failed or not ok
sys.exit(1 if failed else 0)
PY
```

A saída esperada é `feminina: models/kokoro-voice-references/pf_dora.wav ok` e
`masculina: models/kokoro-voice-references/pm_alex.wav ok`, com código 0.

Copie os dois arquivos conferidos para o servidor GPU. O alias `avatar-gpu`
pertence ao SSH config do operador, com host key conferida:

```bash
ssh avatar-gpu 'mkdir -p /srv/avatar/models/kokoro-voice-references'
scp models/kokoro-voice-references/pf_dora.wav models/kokoro-voice-references/pm_alex.wav \
  avatar-gpu:/srv/avatar/models/kokoro-voice-references/
```

No servidor, na raiz do clone, repita a conferência com
`REFS_MODELS=/srv/avatar/models`. O piloto e o worker montam esse diretório em
`/models` só leitura.

### Referência humana da engine Qwen

A receita com `tts.engine` `qwen3-tts-base` usa o Qwen3-TTS Base 1.7B
(`qwen3-tts-12hz-1.7b-base`, revisão fixada no manifesto, Apache-2.0). O Qwen
clona a voz de uma referência humana com transcrição. A voz `masculina` é a
gravação `faber` do OHF Voice Datasets (CC0-1.0, componente `ohf-voice-pt-br`).

O `faber.wav` do componente `qwen-voice-references` (kind `derived`) é o MP3 de
origem convertido para PCM 16 bits, mono, 24 kHz pelo FFmpeg, como descreve a
proveniência no manifesto. A transcrição fica em `provenance.text` e a receita
repete o mesmo texto em `tts.voices.<voz>.transcript`. O WAV não é gerado de
novo na instalação: outra versão do FFmpeg pode mudar os bytes aprovados. Copie
o arquivo do pacote privado das amostras para
`/srv/avatar/models/qwen-voice-references/faber.wav` e confira o SHA-256 com o
manifesto:

```bash
python3 - /srv/avatar/models <<'PY'
import hashlib
import json
import sys
from pathlib import Path

models = Path(sys.argv[1])
manifest = json.loads(Path("docs/models/MODEL_MANIFEST.json").read_text(encoding="utf-8"))
(component,) = [c for c in manifest["components"] if c["id"] == "qwen-voice-references"]
for entry in component["files"]:
    path = models / component["id"] / entry["path"]
    ok = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    print(f"{path} {'ok' if ok else 'AUSENTE OU DIVERGENTE'}")
PY
```

Os pesos do Qwen e o MP3 de origem vêm pelo `models-pull.sh`, como os demais
componentes `model`. Na imagem do worker, o Qwen roda em `runtimes/qwen-tts`,
com Python e `transformers` próprios; o Python do runtime pode ser trocado pela
variável `QWEN_TTS_PYTHON`, como `TTS_PYTHON` no Chatterbox.

## Piloto

O piloto e o congelamento da receita são obrigações finais da P06; as
ferramentas implementadas na P02 e na P07 não equivalem a essa execução ou ao
aceite.

O piloto roda com `network_mode: none`, a GPU reservada e `/models` só leitura.
A receita corrente e o manifesto são dados externos em `/pilot/in:ro`, com
hashes registrados por execução. Atualizar esses dados durante a calibração
não exige reconstruir a imagem. Preserve o digest candidato medido e nunca
monte código para alterar seu runtime; as instruções de build inicial não
substituem este caminho de retomada.

O piloto recebe uma fila de amostras de calibração em JSON. Cada amostra combina
avatar, fundo, fala, voz e formato; uma amostra sozinha é uma fila de um item.
A receita `draft` é aceita: o piloto mede e grava relatórios, não avalia
qualidade nem congela a receita.

### Diretório do piloto

O contêiner roda como o usuário `app` (uid 10001). `PILOT_DIR` precisa ser gravável por esse uid.

```bash
sudo mkdir -p /srv/avatar/pilot/in /srv/avatar/pilot/out
sudo cp fila.json avatar-a.png avatar-b.png cenario.png fala-30s.txt /srv/avatar/pilot/in/
sudo chown -R 10001:10001 /srv/avatar/pilot
```

As imagens precisam ser autorizadas pelo cliente. DEC-005 autoriza nesta P06
os dois avatares e quatro cenários sintéticos existentes, com proveniência,
prompts e hashes, superando a restrição de insumos DEC-003. Isso não fornece
veredito humano de qualidade ou desempenho. Avatar sem transparência passa
pelo recorte BiRefNet antes da composição. As falas ficam em arquivos UTF-8;
nomes como `aprox30s` não substituem a duração medida do WAV real por voz.

### Fila de calibração

Exemplo de `/srv/avatar/pilot/in/fila.json`:

```json
{
  "samples": [
    {
      "id": "a-9x16",
      "image": "avatar-a.png",
      "background": "#1f2937",
      "text_file": "fala-30s.txt",
      "voice": "feminina",
      "format": "9:16"
    },
    {
      "id": "a-16x9",
      "image": "avatar-a.png",
      "background": "cenario.png",
      "text_file": "fala-30s.txt",
      "voice": "feminina",
      "format": "16:9"
    },
    {
      "id": "b-16x9-fechado",
      "image": "avatar-b.png",
      "background": "#1f2937",
      "text": "Olá! Ligue para 0800 721 4400 até 15 de março de 2027.",
      "voice": "masculina",
      "format": "16:9",
      "composition": {"scale": 1.1, "x": 0.5, "y": 1.2}
    }
  ]
}
```

Campos de cada amostra:

- `id`: único na fila, com letras, dígitos, `-` e `_`, começando por letra ou
  dígito; vira a pasta da amostra;
- `image`: imagem do avatar; `background`: cor `#RRGGBB` ou imagem do cenário;
- `text` (fala no próprio JSON) ou `text_file` (arquivo UTF-8), só um dos dois.
  A fala é literal: nada é removido nem normalizado, nem a quebra de linha
  final do arquivo;
- `voice`: `feminina` ou `masculina`; `format`: `9:16` ou `16:9`;
- `composition` (opcional): `{scale, x, y}` nas mesmas faixas dos cenários
  (`scale` de 0,3 a 1,2, `x` de 0 a 1, `y` de 0,5 a 1,2). Sem ela, vale o
  enquadramento de `calibration.composition` da receita para o formato.

Caminhos relativos partem da pasta do `fila.json`. O piloto confere a fila
inteira antes de executar: com qualquer problema, lista todos e sai com código 2
sem rodar nenhuma amostra.

Execute o candidato publicado por digest, sem rebuild nem montagem de código.
A receita corrente e o manifesto são dados externos em `/pilot/in:ro`;
os snapshots anteriores de calibração não identificam o candidato D001.
Copie a pasta privada `p06-piloto-atual/in/` preparada para
`/srv/avatar/pilot/p06-current/in/`. O comando abaixo descreve o lote completo:
quatro amostras × duas execuções não cabem na janela de saldo da DEC-006 pelos
tempos históricos. Não iniciar esse lote autonomamente: o coordenador limita
as amostras à reserva, salva resultados e encerra os recursos temporários.
Os gates não executados permanecem pendentes. O comando não cria instância,
não baixa modelos e não contém credenciais.

```bash
export WORKER_IMAGE=vccr.io/5e20534f-f96c-42fb-8a52-deb4f7e28efc/avatar-worker@sha256:f2814d283009ef7ebcb941367b531631e5008623ef2667cc92eadd8d1c4f06ff
export MODELS_DIR=/srv/avatar/models
export PILOT_DIR=/srv/avatar/pilot/p06-current
docker run --rm --pull=never --gpus device=0 --network none --user 10001:10001 \
  -e WORKER_IMAGE_DIGEST="$WORKER_IMAGE" \
  --mount type=bind,src="$MODELS_DIR",dst=/models,readonly \
  --mount type=bind,src="$PILOT_DIR/in",dst=/pilot/in,readonly \
  --mount type=bind,src="$PILOT_DIR/out",dst=/pilot/out \
  --entrypoint python "$WORKER_IMAGE" -m avatar_worker.pilot \
  --recipe /pilot/in/RECIPE-d001.json \
  --manifest /pilot/in/MODEL_MANIFEST-d001.json \
  --models /models \
  --queue /pilot/in/fila-aprox30s-4amostras.json \
  --runs 2 \
  --out /pilot/out/calibracao-30s-01
```

O contêiner não tem rede (`--network none`); os relatórios precisam registrar
somente `lo`. `--out` precisa ser pasta nova ou vazia; pasta usada é recusada
com código 2. `--runs 2` rotula a primeira execução de cada amostra como fria
e a segunda como quente, mas ambos os estágios iniciam subprocessos novos e
recarregam modelos em cada execução. Não há modelos residentes nem controle
de cache frio do host: interpretar como repetição sequencial com recarga,
não prova de ganho por inferência quente residente. O recorte é feito uma vez
por amostra, fora dos runs. Pelos números históricos (~100 s de GPU por segundo
de fala), uma execução de 30 s poderia ocupar cerca de 50 min; não é medição
do candidato atual nem garantia. Some as execuções antes de rodar.

Para o ensaio longo separado, use `RECIPE-calibracao-60s-d001.json`,
`fila-aprox60s-vertical.json` e saída `/pilot/out/calibracao-60s-01`, mantendo
`--runs 2`. O draft de calibração permite até 60 s/1500 frames; isso não eleva o
limite de produção nem prova 60 s de fala. Se o WAV exceder o limite, registre
a falha e ajuste o texto com novo hash antes de reamostrar. Na A100 80 GB,
o teste 720p se aplica: use `RECIPE-calibracao-720p-d001.json`, a fila de quatro
amostras e saída `/pilot/out/calibracao-720p-01`, sem quantização, `--runs 2`.
Os buckets são 704×1280 e 1280×704; a exportação permanece Full HD. A variante
mantém os pesos Wan 480p existentes conforme o adaptador, não inventa um
checkpoint 720p. Capacidade e qualidade só são demonstradas pela execução.

As amostras rodam na ordem da fila. Em `$PILOT_DIR/out/calibracao-30s-01`
(`/srv/avatar/pilot/p06-current/out/calibracao-30s-01` nesta janela):

- `index.json`: a fila na ordem declarada, com o status de cada amostra (`ok`
  ou `failed`), o SHA-256 da fila e da receita e os comandos de TTS, avatar e
  VRAM usados;
- `<id>/report.json`: o relatório da amostra, com tempo e pico de VRAM por
  etapa, a composição usada e sua origem (`sample` ou `recipe`), SHA-256 e
  número de caracteres da fala (não o texto) e as interfaces de rede vistas
  no contêiner, que devem ser só `lo`;
- `<id>/run-N/final.mp4`: o vídeo de cada execução.

Se uma etapa falha, o erro fica em `error` no relatório da amostra, sem
`final.mp4`; a fila segue para a próxima amostra e o comando sai com código 1.
Os relatórios não avaliam qualidade nem congelam a receita.

## Ensaio local sem GPU

Antes de usar a GPU, o operador pode exercitar na própria máquina, em CPU, as
referências de voz (seção *Referências de voz*), a fila de calibração e o guard
de release. A fila do ensaio usa dublês identificados no lugar do TTS, do
render e da leitura de VRAM: eles não geram voz nem animação e não medem GPU,
então o ensaio não vale como piloto. Composição, FFmpeg e ffprobe são reais.
Nunca rode o ensaio no servidor do cliente.

Requer `uv`, `python3`, `ffmpeg`, `ffprobe` e Docker Compose na máquina. Rode na
raiz do clone.

### Fila com dublês

Entradas do ensaio, com um avatar de fundo transparente, um cenário e uma
imagem quebrada de propósito:

```bash
ENSAIO="$(mktemp -d)"
mkdir -p "$ENSAIO/in"
uv run --frozen --project apps/worker python - "$ENSAIO/in" <<'PY'
import sys
from pathlib import Path

from PIL import Image

inputs = Path(sys.argv[1])
avatar = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
avatar.paste((200, 150, 120, 255), (100, 100, 300, 800))
avatar.save(inputs / "avatar.png")
Image.new("RGB", (640, 360), (40, 90, 120)).save(inputs / "cenario.png")
(inputs / "avatar-quebrado.png").write_text("não é imagem\n", encoding="utf-8")
(inputs / "fala.txt").write_text("Terceira amostra do ensaio, lida do arquivo.\n", encoding="utf-8")
PY
cat > "$ENSAIO/in/fila.json" <<'JSON'
{
  "samples": [
    {"id": "retrato", "image": "avatar.png", "background": "#1f2937",
     "text": "Primeira amostra do ensaio local.", "voice": "feminina", "format": "9:16",
     "composition": {"scale": 0.6, "x": 0.4, "y": 0.9}},
    {"id": "quebrada", "image": "avatar-quebrado.png", "background": "#1f2937",
     "text": "Esta amostra falha no recorte.", "voice": "feminina", "format": "9:16"},
    {"id": "paisagem", "image": "avatar.png", "background": "cenario.png",
     "text_file": "fala.txt", "voice": "masculina", "format": "16:9"}
  ]
}
JSON
```

Dublês, só para o ensaio. O de TTS grava 2 s de silêncio e o de render repete a
imagem recebida no tamanho do bucket; nenhum dos dois informa VRAM nem marca
d'água:

```bash
cat > "$ENSAIO/duble-tts" <<'PY'
#!/usr/bin/env python3
# DUBLÊ DE ENSAIO: não sintetiza voz; grava 2 s de silêncio a 24 kHz.
import json, sys, wave
request = json.load(open(sys.argv[2], encoding="utf-8"))
with wave.open(request["out_wav"], "wb") as out:
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(24000)
    out.writeframes(b"\0\0" * 48000)
result = {"audio_path": request["out_wav"], "duration_s": 2.0, "sample_rate": 24000,
          "peak_vram_mb": None, "watermark_detected": None}
json.dump(result, open(sys.argv[3], "w"))
PY
cat > "$ENSAIO/duble-render" <<'PY'
#!/usr/bin/env python3
# DUBLÊ DE ENSAIO: não anima; repete a imagem recebida no tamanho do bucket.
import json, subprocess, sys, wave
request = json.load(open(sys.argv[2], encoding="utf-8"))
with wave.open(request["audio"]) as audio:
    seconds = audio.getnframes() / audio.getframerate()
width, height = {"9:16": (448, 832), "16:9": (896, 448)}[request["format"]]
video = request["out_dir"] + "/render.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", request["image"],
                "-vf", f"scale={width}:{height}", "-t", str(seconds), "-r", "25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", video], check=True)
result = {"video_path": video, "native_width": width, "native_height": height,
          "frames": round(seconds * 25)}
json.dump(result, open(sys.argv[3], "w"))
PY
chmod +x "$ENSAIO/duble-tts" "$ENSAIO/duble-render"
```

Rode a fila com o CLI real do piloto. `--vram-command true` não lê VRAM, então
os picos ficam `null`:

```bash
uv run --frozen --project apps/worker python -m avatar_worker.pilot \
  --recipe docs/models/RECIPE-v1.json \
  --manifest docs/models/MODEL_MANIFEST.json \
  --models "$ENSAIO/models" \
  --queue "$ENSAIO/in/fila.json" \
  --out "$ENSAIO/out" \
  --tts-python "$ENSAIO/duble-tts" \
  --avatar-python "$ENSAIO/duble-render" \
  --vram-command true
echo "código $?"
```

O comando termina com `código 1`, porque a amostra `quebrada` falha no
recorte, e as outras duas seguem. Confira:

```bash
python3 -m json.tool "$ENSAIO/out/index.json"
python3 -m json.tool "$ENSAIO/out/quebrada/report.json"
for video in "$ENSAIO"/out/*/run-1/final.mp4; do
  echo "$video"
  ffprobe -v error -show_entries stream=codec_name,width,height,sample_rate -of compact "$video"
done
```

- `index.json` lista `retrato` (`ok`), `quebrada` (`failed`) e `paisagem` (`ok`),
  nessa ordem, e `commands` mostra os dublês e o `true` no lugar do TTS, do
  render e da VRAM;
- `quebrada/report.json` traz `error.stage` `cutout` e a mensagem do erro, e
  não há `final.mp4` dessa amostra;
- os dois `final.mp4` são H.264 1080×1920 (`retrato`) e 1920×1080 (`paisagem`),
  com AAC 48 kHz.

Ao terminar, apague a pasta do ensaio com `rm -rf "$ENSAIO"`.

### Guard de release com ambiente de teste

O guard roda com um ambiente temporário de valores fictícios, identificados como
teste. Nunca use esses valores numa instalação:

```bash
TESTE="$(mktemp -d)"
FAKE="sha256:$(printf '%064d' 0)"
cat > "$TESTE/release.env" <<EOF
# Ambiente de TESTE do ensaio local: valores fictícios, nunca use em release.
POSTGRES_PASSWORD=ensaio-local-postgres-password-0123456789
WORKER_TOKEN=ensaio-local-worker-token-0123456789abcdef
APP_ENV=production
SITE_ADDRESS=ensaio.example.test
API_IMAGE=fixture-api@$FAKE
PANEL_IMAGE=fixture-panel@$FAKE
WORKER_IMAGE=fixture-worker@$FAKE
MODELS_DIR=/srv/avatar/models
EOF
chmod 600 "$TESTE/release.env"
bash infra/scripts/check-release.sh --env-file "$TESTE/release.env"
echo "código $?"
rm -rf "$TESTE"
```

O guard imprime `Release api: ...` e `Release worker: ...` com "Compose e
referências imutáveis válidos", avisa que é só validação de configuração e
termina com `código 0`. Ele não baixa nem executa as imagens fictícias.

## Release imutável e instalação por papel

Os comandos anteriores de build/piloto não são o aceite final. `install.sh` instala imagens já construídas e identificadas por digest; nunca faz build implícito, apaga volumes ou congela receita. Requer Python 3.11 ou superior e Docker Compose com `!reset`/`!override` (2.24.4 ou superior). Na GPU do provedor não reinstale o driver nem reinicie o host físico.

### Preparar segredos sem imprimi-los

Na VPS CPU, crie o ambiente uma única vez. Se já existe instalação, preserve os segredos e volumes; não gere senha nova para um PostgreSQL existente. O código abaixo recusa sobrescrever `.env`:

```bash
python3 - <<'PY'
import os, secrets
from pathlib import Path
p = Path('infra/compose/.env')
text = Path('infra/compose/.env.example').read_text()
text = text.replace('POSTGRES_PASSWORD=\n', 'POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
text = text.replace('WORKER_TOKEN=\n', 'WORKER_TOKEN=' + secrets.token_urlsafe(32) + '\n')
text = text.replace('APP_ENV=\n', 'APP_ENV=production\n')
with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
    output.write(text)
print('Ambiente privado criado; preencha domínio e imagens sem compartilhar o arquivo.')
PY
```

Edite o arquivo privado para preencher `SITE_ADDRESS` com o domínio real apontando à VPS CPU, `API_IMAGE` e `PANEL_IMAGE`. Na VPS GPU, seu ambiente privado usa o **mesmo** `WORKER_TOKEN`, `WORKER_IMAGE`, `MODELS_DIR` e `API_URL=http://127.0.0.1:18000` para o túnel documentado. Transfira o token por cofre/canal privado autorizado, não por chat, shell history ou repositório. Mantenha ambos `.env` com `chmod 600`.

### Construir e registrar imagens reais

Código e imagens devem permanecer sob controle do cliente. Use seu repositório e um registro de imagens sob sua conta; endpoint, permissões e custos desse registro precisam estar resolvidos antes da publicação. Não crie conta/registro nem pague serviço em nome do cliente. `REGISTRY` e `RELEASE` abaixo são valores definidos pelo operador, não um registro público escolhido pelo projeto.

No servidor CPU do cliente, com o commit escolhido:

```bash
docker build -f infra/docker/api.Dockerfile -t "$REGISTRY/avatar-api:$RELEASE" .
docker build -f infra/docker/web.Dockerfile -t "$REGISTRY/avatar-panel:$RELEASE" .
docker push "$REGISTRY/avatar-api:$RELEASE"
docker push "$REGISTRY/avatar-panel:$RELEASE"
docker image inspect "$REGISTRY/avatar-api:$RELEASE" --format '{{json .RepoDigests}}'
docker image inspect "$REGISTRY/avatar-panel:$RELEASE" --format '{{json .RepoDigests}}'
```

Na GPU, construa e publique a imagem do worker a partir do commit entregue na P07, **antes** do piloto: o piloto roda essa imagem pelo digest e a receita congelada registra o mesmo digest. Reconstruir depois gera outro digest, que não é o medido no piloto.

```bash
docker build -f infra/docker/worker.Dockerfile -t "$REGISTRY/avatar-worker:$RELEASE" .
docker push "$REGISTRY/avatar-worker:$RELEASE"
docker image inspect "$REGISTRY/avatar-worker:$RELEASE" --format '{{json .RepoDigests}}'
```

Use as referências completas `nome@sha256:...` retornadas realmente pelo registro, em `API_IMAGE`, `PANEL_IMAGE`, `WORKER_IMAGE`. `latest` é recusada mesmo acompanhada de digest. Image ID (`.Id`) não é digest de publicação; não o use no relatório do piloto nem na receita. Se o build local não oferece `RepoDigests`, publique/puxe no registro autorizado e confira a identidade antes do piloto. O nome/tag local `avatar-worker:pilot` precisa apontar à mesma imagem identificada no relatório.

### Instalar CPU/API e GPU

No papel API, somente PostgreSQL, API e Caddy iniciam. O release substitui o bind temporário do painel por portas públicas 80/443, guarda estado/certificados do Caddy em volumes e mantém a porta interna da API em loopback. O domínio precisa apontar à VPS e o firewall permitir apenas HTTPS/HTTP necessário e SSH autorizado; PostgreSQL e `/internal/v1` não são públicos.

```bash
bash infra/scripts/check-release.sh --role api
bash infra/scripts/install.sh --role api
```

O instalador espera a saúde da API e consulta `/readyz`; migrações rodam no entrypoint. Crie o primeiro usuário uma vez, com senha interativa (não em argumento):

```bash
CPU=(docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.cpu.yml -f infra/compose/docker-compose.api.yml -f infra/compose/docker-compose.release.yml)
"${CPU[@]}" exec api avatar-api users create --username equipe@dominio-do-cliente
```

Depois do piloto **real e aprovado**, carregue a receita frozen pelo stdin; o comando recusa receita não congelada:

```bash
"${CPU[@]}" exec -T api avatar-api recipes load < docs/models/RECIPE-v1.json
```

Na GPU, complete previamente `gpu-host-check.sh`, pesos conferidos e segunda execução de `models-pull.sh` com zero downloads. Runtimes CUDA/imports/licenças e piloto only-lo precisam da prova real descrita neste guia. Estabeleça o túnel privado com host key conferida antes de iniciar o supervisor:

```bash
bash infra/scripts/check-release.sh --role worker
bash infra/scripts/install.sh --role worker
```

O supervisor não usa `network_mode: none`: precisa alcançar a API interna. Only-lo é exigência dos subprocessos de inferência e do piloto isolado. Processo worker iniciado não comprova pesos, VRAM, qualidade ou geração; confirme heartbeat e um job real. Não entregue receita sintética para liberar o formulário.

O guard sem `--role` verifica os dois papéis e toda documentação. Ele valida configuração/digests, não disponibilidade ou conteúdo da imagem no registro nem aceite do cliente. `--no-pull` só é permitido quando as imagens imutáveis já foram puxadas/verificadas no cache; se faltar alguma, o instalador para sem download/build implícito.

### Reprodutibilidade e aceite

Repita a instalação no cliente a partir de clone/diretório limpo do mesmo commit, ambiente privado e digests registrados, sem substituir volumes ativos. Reinstalar sobre o mesmo projeto preserva banco e arquivos; não execute seed nem `down --volumes`. Para exercício isolado use projeto novo, overrides de portas em loopback e volumes próprios; jamais teste restauração sobre a instalação ativa.

Confirme DNS/certificado HTTPS externamente, login/logout, catálogo real autorizado, `/internal/v1` inacessível pelo domínio, banco sem porta publicada e comunicação GPU→API pelo túnel. Instalação local não comprova esses controles remotos. Siga [OPERACAO.md](OPERACAO.md) para backup/restore e [o procedimento de homologação](../homologacao/PROCEDIMENTO.md) para os cenários e aceite humano.
