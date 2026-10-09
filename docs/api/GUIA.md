# API de vídeos — guia de integração

A API recebe **texto literal**, avatar e cenário cadastrados; devolve um job persistido, não o vídeo imediatamente. Não interpreta instruções de cena nem escreve roteiros. O worker gera voz e animação na GPU. O download é MP4; a postagem no Instagram é manual.

A API e o painel podem estar disponíveis enquanto a GPU está parada. Testes locais com mídia sintética não comprovam inferência, qualidade ou homologação do cliente. A receita de produção depende do piloto e da aprovação na GPU.

## Endereço e autenticação

Use a origem HTTPS da instalação, sem `/panel`, como `API_URL`. Crie uma chave em **Usuários e chaves** e guarde-a em um cofre: aparece uma única vez. Envie `Authorization: Bearer <chave>` em todas as chamadas `/api/v1`, inclusive prévias e download. Não envie chave na URL, query string, HTML, logs ou repositório. Cookie/CSRF são exclusivos do painel e não substituem Bearer.

Jobs da API pertencem à chave que os criou. Outra chave recebe 404 mesmo sendo da mesma equipe. Revogar a chave ou remover o acesso de quem a criou interrompe o consumo com ela. Ausência, chave inválida e revogada retornam o mesmo 401.

```bash
# Configure API_URL e API_KEY no ambiente por um mecanismo seguro.
curl --fail-with-body "$API_URL/api/v1/avatars" -H "Authorization: Bearer $API_KEY"
curl --fail-with-body "$API_URL/api/v1/scenes" -H "Authorization: Bearer $API_KEY"
```

## 1. Listar os assets disponíveis

`GET /api/v1/avatars` e `GET /api/v1/scenes` retornam `items`. Só assets ativos aparecem. `voice` vem do avatar, não do pedido. Cadastro/preparação/arquivamento são feitos no painel. `preview_url` pode ser `null` se não houver prévia preparada; isso não é ausência do asset.

Os UUIDs abaixo são **exemplos**, não IDs da instalação. Use os IDs recebidos por HTTP.

<!-- example: response GET /api/v1/avatars 200 -->
```json
{"items":[{"id":"aaaaaaaa-0000-4000-8000-000000000001","name":"Avatar autorizado","voice":"feminina","preview_url":null,"created_at":"2026-10-09T12:00:00Z"}]}
```

<!-- example: response GET /api/v1/scenes 200 -->
```json
{"items":[{"id":"bbbbbbbb-0000-4000-8000-000000000001","name":"Fundo claro","preview_url":"/api/v1/scenes/bbbbbbbb-0000-4000-8000-000000000001/preview","created_at":"2026-10-09T12:00:00Z"}]}
```

Prévia: `GET /api/v1/avatars/{avatar_id}/preview?aspect_ratio=9:16` ou `/scenes/{scene_id}/preview?aspect_ratio=16:9`, sempre com Bearer. Sucesso é PNG binário. Formatos aceitos: `9:16` e `16:9`. Prévia ausente/asset indisponível retorna 404; formato inválido, 422.

## 2. Criar o job e conservar a intenção

`POST /api/v1/jobs`, JSON UTF-8. `script_text` não pode ser vazio e precisa caber no limite da receita vigente. Preserve pontuação, espaços e quebras de linha: o texto é falado literalmente. O limite exato é calibrado pela receita; não copie um número de teste local para a integração. Texto acima do limite: 422 `SCRIPT_TOO_LONG`. Sem receita vigente: 503 `RECIPE_UNAVAILABLE`.

`aspect_ratio` opcional; omitido usa `9:16`. Para horizontal, envie `16:9`. Não há parâmetro de voz, FPS, resolução ou publicação. O cenário guarda um enquadramento para cada formato.

<!-- example: request POST /api/v1/jobs -->
```json
{"script_text":"Olá! Este texto será falado literalmente.","avatar_id":"aaaaaaaa-0000-4000-8000-000000000001","scene_id":"bbbbbbbb-0000-4000-8000-000000000001","aspect_ratio":"9:16"}
```

<!-- example: request POST /api/v1/jobs -->
```json
{"script_text":"Uma fala para o vídeo horizontal.","avatar_id":"aaaaaaaa-0000-4000-8000-000000000001","scene_id":"bbbbbbbb-0000-4000-8000-000000000001","aspect_ratio":"16:9"}
```

<!-- example: request POST /api/v1/jobs -->
```json
{"script_text":"Formato vertical por omissão.","avatar_id":"aaaaaaaa-0000-4000-8000-000000000001","scene_id":"bbbbbbbb-0000-4000-8000-000000000001"}
```

Envie `Idempotency-Key` (1 a 128 caracteres) com uma chave nova por **intenção**, por exemplo UUID. Se a resposta se perder, reenvie **a mesma chave e o mesmo JSON**, não crie outra chave. Um replay pode devolver o job já processando/pronto/falho. Mesma chave com pedido diferente: 409 `IDEMPOTENCY_CONFLICT`. Outra intenção usa outra chave. Sem esse cabeçalho, cada POST pode criar um job novo. Não há retry automático de job falho por este mecanismo.

```bash
curl --fail-with-body -X POST "$API_URL/api/v1/jobs" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Idempotency-Key: $INTENTION_ID" \
  -H 'Content-Type: application/json' --data-binary @pedido.json
```

202 significa que o pedido foi persistido. Use `id` e `status_url` recebidos:

<!-- example: response POST /api/v1/jobs 202 -->
```json
{"id":"cccccccc-0000-4000-8000-000000000001","status":"queued","status_url":"/api/v1/jobs/cccccccc-0000-4000-8000-000000000001","download_url":null}
```

## 3. Acompanhar até o estado final

`GET /api/v1/jobs/{job_id}`, a cada 3 s. Estados: `queued`, `processing`, `ready`, `failed`. `stage` só é preenchido em processamento: `compose`, `tts`, `render`, `finalize`, `upload`. São etapas, não porcentagem. Não existe duração garantida: depende da GPU, receita e fila. Fechar o cliente não cancela o job.

<!-- example: response GET /api/v1/jobs/{job_id} 200 -->
```json
{"id":"cccccccc-0000-4000-8000-000000000001","status":"processing","status_url":"/api/v1/jobs/cccccccc-0000-4000-8000-000000000001","download_url":null,"stage":"tts","aspect_ratio":"9:16","created_at":"2026-10-09T12:00:00Z","finished_at":null,"error":null}
```

<!-- example: response GET /api/v1/jobs/{job_id} 200 -->
```json
{"id":"cccccccc-0000-4000-8000-000000000001","status":"ready","status_url":"/api/v1/jobs/cccccccc-0000-4000-8000-000000000001","download_url":"/api/v1/jobs/cccccccc-0000-4000-8000-000000000001/download","stage":null,"aspect_ratio":"9:16","created_at":"2026-10-09T12:00:00Z","finished_at":"2026-10-09T12:05:00Z","error":null}
```

<!-- example: response GET /api/v1/jobs/{job_id} 200 -->
```json
{"id":"cccccccc-0000-4000-8000-000000000001","status":"failed","status_url":"/api/v1/jobs/cccccccc-0000-4000-8000-000000000001","download_url":null,"stage":null,"aspect_ratio":"9:16","created_at":"2026-10-09T12:00:00Z","finished_at":"2026-10-09T12:05:00Z","error":{"code":"OUT_OF_MEMORY","message":"A GPU não tem memória para esta geração."}}
```

Em `failed`, apresente `error.code` e `error.message`; não tente baixar nem crie outra intenção sem decisão do usuário. Códigos possíveis incluem `OUT_OF_MEMORY`, `WORKER_LOST`, `INPUT_INVALID`, `RENDER_FAILED` e `OUTPUT_INVALID`. O operador verifica o gerador; uma fala cujo áudio ultrapassa o limite deve ser encurtada (`INPUT_INVALID`). Não substitua falha por um arquivo fictício.

`GET /api/v1/worker-status` informa o último heartbeat persistido de um worker de vídeo. `null` = nenhum sinal observado; mais de 2 min = sem resposta recente. Não é uma sondagem instantânea nem prova de capacidade GPU. Falha de rede significa estado **desconhecido**, não offline.

<!-- example: response GET /api/v1/worker-status 200 -->
```json
{"last_heartbeat_at":null}
```

## 4. Baixar o MP4

`GET /api/v1/jobs/{job_id}/download`, ou o `download_url` retornado, com Bearer. Sucesso 200 `video/mp4`; `Range` é aceito e retorna 206. Não pronto: 409 `JOB_NOT_READY`; falho: 409 `JOB_FAILED`; arquivo ausente ou job desconhecido/de outra chave: 404. O estado `ready` não impede falha de armazenamento posterior: trate o HTTP do download.

```bash
curl --fail-with-body "$API_URL/api/v1/jobs/$JOB_ID/download" \
  -H "Authorization: Bearer $API_KEY" --output video.mp4
```

Perfil final: H.264/yuv420p, AAC, MP4 com faststart, 25 FPS; 1080×1920 em 9:16 ou 1920×1080 em 16:9. O worker valida a mídia antes de publicar. Duração é a do áudio gerado, não uma estimativa calculada no cliente. Guarde o arquivo e publique manualmente; não existe endpoint de Instagram.

## Erros HTTP

Os erros JSON usam um envelope único; `field` é opcional, `request_id` identifica a requisição (também `X-Request-ID`). Não são o array padrão `detail` do FastAPI. Download/Range também pode usar erro textual do servidor de arquivos (por exemplo 416).

<!-- example: response POST /api/v1/jobs 422 -->
```json
{"error":{"code":"SCRIPT_TOO_LONG","message":"Texto acima do limite da receita vigente.","field":"script_text","request_id":"exemplo-req-1"}}
```

<!-- example: response GET /api/v1/avatars 401 -->
```json
{"error":{"code":"UNAUTHORIZED","message":"Chave de API ausente ou inválida.","request_id":"exemplo-req-2"}}
```

Validação 422: corrigir o pedido. Conflito 409: verificar intenção/estado. 401: corrigir ou trocar a chave. 404: conferir ID e a chave que criou o job. 503: serviço ou receita indisponível; consultar o operador. 500: informar `request_id` ao operador. Não registre o cabeçalho Authorization nem o texto da fala em logs de diagnóstico.

## Consumidor independente (Python 3, biblioteca padrão)

Salve o código como `consumir.py`. Configure `API_URL`/`API_KEY` de forma segura; use `ASPECT_RATIO=16:9` para horizontal. Opcionalmente informe `AVATAR_ID`/`SCENE_ID`; sem eles, o exemplo escolhe o primeiro asset ativo. `FALA` é o texto literal. O script não usa banco, rotas do painel ou protocolo interno. Ele lista, cria, acompanha e baixa. Em falha, termina sem criar um novo pedido. Um timeout deixa o job persistido: conserve o ID/chave exibidos para acompanhar/repetir a mesma intenção.

```python
import json
import os
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = os.environ["API_URL"].rstrip("/")
key = os.environ["API_KEY"]
headers = {"Authorization": "Bearer " + key}

def call(method, path, body=None, intention=None):
    extra = {"Content-Type": "application/json"} if body is not None else {}
    if intention is not None:
        extra["Idempotency-Key"] = intention
    request = Request(base + path, method=method, headers={**headers, **extra},
                      data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise SystemExit(f"HTTP {error.code}: {error.read().decode()}") from None

avatars = call("GET", "/api/v1/avatars")["items"]
scenes = call("GET", "/api/v1/scenes")["items"]
if not avatars or not scenes:
    raise SystemExit("Cadastre e prepare um avatar e um cenário no painel.")
intention = os.environ.get("INTENTION_ID", str(uuid.uuid4()))
payload = {"script_text": os.environ.get("FALA", "Olá! Este é um vídeo de teste."),
           "avatar_id": os.environ.get("AVATAR_ID", avatars[0]["id"]),
           "scene_id": os.environ.get("SCENE_ID", scenes[0]["id"]),
           "aspect_ratio": os.environ.get("ASPECT_RATIO", "9:16")}
print("Intenção:", intention, flush=True)
job = call("POST", "/api/v1/jobs", payload, intention)
print("Job:", job["id"], flush=True)
deadline = time.monotonic() + 3600
while True:
    job = call("GET", job["status_url"])
    print(job["status"], job.get("stage"), flush=True)
    if job["status"] == "failed":
        raise SystemExit(json.dumps(job["error"], ensure_ascii=False))
    if job["status"] == "ready":
        break
    if time.monotonic() >= deadline:
        raise SystemExit("Timeout de acompanhamento. O job continua salvo; não crie outra intenção.")
    time.sleep(3)
request = Request(base + job["download_url"], headers=headers)
try:
    with urlopen(request, timeout=60) as response, Path("video.mp4").open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
except HTTPError as error:
    raise SystemExit(f"Download HTTP {error.code}: {error.read().decode()}") from None
print("Arquivo: video.mp4; publique manualmente.")
```

## Contrato e atualização

[`openapi.json`](openapi.json) é gerado da aplicação atual. Contém também schemas internos/painel para rastreabilidade; integrações usam apenas `/api/v1`. Nenhum endpoint de documentação fica publicado na instalação.

Da raiz do repositório, atualize o export após mudar o contrato:

```bash
uv run --directory apps/api python -c 'import json; from pathlib import Path; from avatar_api.main import create_app; Path("../../docs/api/openapi.json").write_text(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n")'
uv run --directory apps/api pytest tests/docs
```

Os exemplos JSON marcados neste documento são validados contra o OpenAPI; os testes também exercitam autenticação, limite, posse, estados e download reais. O catálogo/mídia do E2E são apenas fixtures isoladas. Não execute seeds nem o servidor de teste na VPS de produção.
