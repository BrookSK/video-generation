# P08: qualidade por cena e custo (24/10)

Teste de 24/10/2026 da change 08 (`openspec/changes/08-qualidade-por-cena`). O cliente pediu
qualidade alta de GPU só onde o avatar aparece grande (abertura e encerramento), o modo atual nas
cenas do meio, com o avatar no quadro menor ao lado do checklist, e uma passagem menos seca entre
as cenas. Sem cobrança de desenvolvimento; a GPU saiu da recarga de US$ 25 do cliente na Verda.

Insumos: foto, WAV aprovado e prompt da videoaula do Rafael ([roteiro](P06-ROTEIRO-RAFAEL.md)),
seed 42. Checklists, logo, cores e trilha são sintéticos, como na
[aula de exemplo](M002-AULA-EXEMPLO.md).

## GPU

| Campo | Valor |
|---|---|
| Instância | 1x H100 SXM5 80 GB, FIN-02, US$ 4,56/h (a H200 aprovada acabou antes do deploy; troca confirmada pelo Felipe) |
| Disco | `p06-novos-cache-fin02-20261016` restaurado da lixeira (US$ 5,01), imagem `cad3a59e`, modelos em `/srv/avatar/models` |
| Janela | 19:22Z a 21:57Z (2 h 35 min). A fila terminou às 21:21Z; a sessão do console expirou e a exclusão esperou o login do Felipe |
| Custo | saldo de US$ 25,41 para US$ 8,05: US$ 17,36 no total, abaixo do teto de US$ 20 |
| Fim | instância excluída e disco na lixeira (restaurável por 96 h); nada ativo no console |

Os renders passam por `batch.py`, que carrega o modelo uma vez por LoRA. O 480p roda sem offload.
O 720p sem offload estourou os 80 GB (78 GiB em uso no erro) e voltou na mesma VM com offload
(pico de 74 GiB). Todos os SHA-256 copiados conferem com os da VM.

## Resultado

SyncNet oficial em CPU sobre o render nativo, mesmo recorte de rosto proporcional, controles de
áudio deslocado em -200, 0 e +200 ms recuperados em todos. Confiança maior = boca mais presa à fala.

| Perfil | Cena | Render | GPU (s) | s de GPU por s de vídeo | Pico VRAM (GiB) | SyncNet (offset, confiança) |
|---|---|---|---|---|---|---|
| A (receita atual), 21/10 na A100 | 1 / 3 / 6 | 896x448 | | 107 com a carga | | -3 3,22 / -2 4,24 / -3 3,96 |
| A sem offload | 1 | 896x448 | 273 | 32,6 | 59 | -3 3,23 |
| E (áudio CFG 1) | 3 | 896x448 | 187 | 19,7 | 59 | -2 1,93 |
| H1 (720p, LoRA T2V rank32, 4 passos, shift 11) | 1 / 6 | 1408x640 | 1.372 / 1.807 | 177,4 | 74 | -4 7,04 / -1 7,21 |
| H2 (720p, LoRA I2V rank64, 6 passos, shift 11) | 1 | 1408x640 | 1.986 | 237,6 | 74 | -3 7,86 |
| B6 (480p, LoRA I2V rank64, 6 passos, shift 11) | 1 | 896x448 | 461 | 55,1 | 58 | -3 3,18 |

Carga do modelo: 191 a 247 s por lote. H2 no encerramento foi pulado pelo prazo da VM.

- **A sem offload sai igual ao aprovado** (PSNR 38,8 dB contra o render de 21/10, mesma
  sincronia) e custa menos de um terço do tempo de hoje. É ganho sem mudança visível.
- **720p é o que melhora o rosto e a boca.** H1 e H2 dobram a confiança do SyncNet e o rosto fica
  visivelmente mais nítido. B6, que troca LoRA e passos mas fica em 480p, não melhora nada: o
  ganho vem da resolução.
- **H2 fica muito perto do H1** (7,86 contra 7,04 na abertura, sem diferença clara no quadro) e
  custa 34% a mais.
- **E (áudio CFG 1) piora a sincronia** (1,93 contra 4,24 na mesma cena). Sai do quadro menor.

## Custo por aula

Aula de exemplo: 56,72 s de fala, abertura e encerramento 17,92 s, meio 38,80 s. Custo = (carga
única + taxa medida x duração) x preço da H100. "Hoje" usa a medição de 21/10 na A100.

| Modo | Segundos de GPU | Custo por aula | Por minuto de aula |
|---|---|---|---|
| Hoje (A, offload, carga por cena, A100) | 6.069 | US$ 3,62 | US$ 3,83 |
| A sem offload, carga única (H100) | 2.099 | US$ 2,66 | US$ 2,81 |
| Híbrido: H1 em abertura e encerramento, A no meio | 4.693 | US$ 5,94 | US$ 6,29 |
| Híbrido: H2 em abertura e encerramento, A no meio | 5.771 | US$ 7,31 | US$ 7,73 |
| Tudo em H1 | 10.309 | US$ 13,06 | US$ 13,81 |
| Tudo em H2 | 13.722 | US$ 17,38 | US$ 18,39 |

O 720p rodou com offload por falta de memória na H100. Numa GPU de 141 GB (H200) ele pode rodar
sem offload e ficar mais rápido; isso não foi medido.

## Montagem

A dissolução de 0,4 s entre cenas (commit `ed96ba2`) foi conferida nos quadros da passagem da
abertura para a cena 2: o quadro do meio mistura as duas cenas e o seguinte é limpo. Áudio e
duração não mudam (62,72 s nas duas aulas).

## Arquivos

Ficam só no pacote privado, fora do repositório:
`~/Developer/video-generation-amostras/p06-qualidade-por-cena-20261024/`

| Arquivo | SHA-256 |
|---|---|
| `aulas/aula-A.mp4`: tudo em A, checklists, dissolução | `2a51ee9dc305bad2fb257f15cb17e8b9d7af8850e6680ae53a2eab6cda9f5c64` |
| `aulas/aula-H1.mp4`: híbrido H1 | `980fa545a42102ed7fcfd1034f741ce9be36750055bfdf0b55e3990d5da1f9bd` |
| `aulas/comparacao-abertura.mp4`: A, H1, H2 e B6 em grade | `33388cdc147bf17f7a54b1c90f2a545029e9decefe33c7ee45e9909325421411` |

As duas aulas: H.264 1920x1080, AAC, 62,72 s, decodificam sem erro (`ffmpeg -xerror`). Ao lado:
`renders/` (nativos), `cenas/` (finalizadas, com registro), `qc/` (SyncNet), `tempos/` e `logs/`
(fila da VM), `gpu/` (lotes, `batch.py`, `patch_cfg1.py`, `run.sh`, `bootstrap.sh`) e `pos/`
(`finalizar.py`, `montar.py`, `comparar.py`, `custos.py`).

## Próximo passo

A decisão é do cliente: aprovar o híbrido H1 (cerca de US$ 6 por aula de 1 minuto) e, depois
disso, levar o perfil por cena para a receita, a API e o painel. A troca para sem offload com carga
única vale para qualquer escolha e não depende do cliente.
