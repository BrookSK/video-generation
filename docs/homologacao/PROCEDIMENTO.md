# Procedimento de homologação e entrega

## Fronteira da aceitação

P06 é a verificação no ambiente final do cliente. Código compilado, testes locais, mídia FFmpeg e catálogo sintético não aprovam GPU, qualidade, domínio, Instagram ou autonomia. Não homologue árvore fonte no lugar do release candidate identificado. Ao completar a fase e construir o RC, repita a regressão integrada e os gates de release conforme o método; não chame preparação local de release aprovado.

O cliente autoriza os materiais, a conexão entre as VPS, o domínio/registro de imagens e os avaliadores. O operador registra logs/metadados sem segredos; o avaliador humano fornece os vereditos. Custos continuam com o cliente, sem autorização implícita para contratar serviços ou automatizar ligar/desligar GPU.

Ordem: acesso/host/pesos → piloto e avaliação → receita congelada → imagens/instalação → catálogo e jornadas reais → matriz/Instagram → autonomia/revogação. Qualquer pré-requisito ausente bloqueia o passo dependente, não autoriza material substituto.

## SCN-001 — host, modelos e conexão privada (MH-07)

1. Restabelecer SSH GPU autorizado e seguir [INSTALACAO.md](../operacao/INSTALACAO.md). No ambiente Sysbox do provedor, preservar driver/host físico e usar o runtime CDI já comprovado, revalidando o host real.
2. Guardar saída de `gpu-host-check.sh`: Ubuntu 24.04, driver ≥560.28.03, Docker/Compose/toolkit, nome da GPU e VRAM vistos no container.
3. Construir imagem no servidor/conta do cliente e registrar referência publicada com digest real, não `.Id`. Dentro dela, CUDA disponível nos runtimes TTS/avatar e imports `flash_attn`/`xformers`; política comercial do manifesto aprovada.
4. Completar `models-pull.sh`: todos os arquivos/tamanhos/SHA-256 do manifesto, sem arquivo parcial tratado como peso válido. Reexecutar: exit 0 e zero downloads. Não reduzir o manifesto para caber no disco.
5. Com autorização e host key verificada, estabelecer túnel SSH ou rede privada autenticada CPU↔GPU. Supervisor autentica token em `/internal/v1`; banco não tem porta pública nem credenciais no worker. Pelo domínio público, `/internal/v1/claim` deve responder 404; ausência de credencial interna pública não basta para provar isolamento.

Evidência: observação, logs de host/modelos/runtime e controles de rede, referências/digests e versão do manifesto. Não guardar senha/token/SSH privado.

## SCN-002 — piloto real e C1–C7 (MH-04 e MH-08)

Use imagem autorizada com ombros visíveis e texto pt-BR com números, valores, telefone, nomes e negativas. Siga o script de piloto publicado, com inferência estritamente only-lo; nenhuma chamada de SaaS nem download durante a inferência. O supervisor precisa de HTTP interno, mas os subprocessos/piloto não recebem rede externa.

- Fala medida de 30 s, 9:16 e 16:9, execução fria e quente (`--runs 2`), mesma imagem e referência de voz autorizada ou padrão aprovado.
- Teste de 60 s em 9:16 antes de elevar limite, observando streaming/max_frame_num e deriva de cor.
- Se a GPU tiver **pelo menos 48 GB**, testar 720p sem quantização. A L40S anteriormente observada tinha 46.068 MiB disponíveis; registre capacidade nominal e memória disponível separadamente. Não descarte o teste só por converter GB para GiB ou descontar memória reservada; em dúvida, execute e registre o resultado real. A condição não é uma aprovação antecipada de 720p.
- Por etapa: tempo e pico de VRAM; perfil nativo/final, segundos de computação por segundo de vídeo, taxa de caracteres medida, texto/hash, versões/digests e interfaces de rede. FFprobe confere perfil e duração real.

| Critério | Avaliação exigida |
|---|---|
| C1 | Fala literal correta em pt-BR, incluindo números, valores, telefone, nomes e negativas. |
| C2 | Sincronia labial adequada, sem atraso perceptível ou troca de fonemas. |
| C3 | Movimento natural de cabeça e ombros além da boca. |
| C4 | Expressão variável; não aceitar rosto estático com boca apenas. |
| C5 | Rosto/corpo sem esticar nem cortar; pad só da cor do cenário. |
| C6 | Sem color shift/deriva temporal, inclusive amostra longa. |
| C7 | `watermark_detected` verdadeiro; watermark Perth do Chatterbox preservado. |

Cliente/avaliador registra cada veredito em `docs/models/PILOTO-v1.md`, incluindo autorização, GPU/perfil, medições e referência privada das amostras. Reprovação mantém receita não congelada, exige ajuste/reamostragem ou replanejamento para fallback documentado (EchoMimicV3 ou LongCat-Video-Avatar-1.5), sem trocar o combinado funcional. Somente aprovação real permite congelar `RECIPE-v1.json`, registrar limites medidos e carregar a receita na API. Nenhum arquivo de piloto aprovado existe ainda.

## Release guard e instalação (MH-01 e início do MH-02)

1. Resolver domínio/HTTPS e registro de imagens sob controle do cliente. Construir/publicar imagens de API/painel/worker com o commit e receita aprovados; preencher ambiente privado com referências reais.
2. Executar `bash infra/scripts/check-release.sh`: ambas composições válidas, imagens sem build ativo/latest e com digest, todas variáveis no `.env.example`, documentos presentes e segredos privados seguros. Este guard valida configuração, não conteúdo da imagem nem aprovação humana.
3. Executar instalação por papel seguindo só INSTALACAO.md, repetir em clone/diretório limpo, registrar commit/digests e preservar volumes ativos. Confirmar HTTPS externo/certificado, login/logout e isolamento banco/internal. Na CPU só API/PostgreSQL/Caddy; na GPU somente worker, sem banco/storage direto.
4. Executar `backup.sh` no cliente e exercício de recuperação isolado conforme [OPERACAO.md](../operacao/OPERACAO.md). Evidência de dump/tar/manifest/COMPLETE e comparação de banco/mídia; não restaurar sobre instalação ativa.
5. Pelo painel, cadastrar 2 avatares e 4 cenários com materiais fornecidos/autorizados. Ambos avatares precisam ficar ativos e cenários enquadrados nos dois formatos. Fixtures E2E não são o pacote inicial.

## SCN-004 — pipeline remoto e recuperação (MH-05)

Usando chave Bearer própria e o guia publicado, criar 9:16 padrão e 16:9 explícito; confirmar resposta rápida 202, polling 3 s, tentativa/etapa e estado `ready`. Baixar por autenticação e registrar SHA-256 e FFprobe: 1080×1920/1920×1080, H.264/yuv420p, AAC 48 kHz, 25 FPS CFR e faststart, áudio/vídeo coerentes com receita.

Durante um job autorizado de teste, parar o worker, observar lease vencido/WORKER_LOST e requeue; restaurar worker/túnel e confirmar próxima tentativa completa com arquivo válido, sem publicar resultado parcial. Texto acima do limite retorna 422 sem job novo. Com GPU parada/presença antiga, histórico informa falta de heartbeat após 2 min, enquanto API/listagens/downloads existentes permanecem disponíveis. Conferir conexões da geração: supervisor apenas API interna; inferência só lo. Não provocar perda de dados de produção para testar falha.

## SCN-005 — painel e consumidor externo (MH-06)

Pessoa da equipe gera no painel um 9:16 e um 16:9 com avatares diferentes, acompanha fila/etapas/pronto, recarrega sem perder job e baixa os arquivos. Registrar screenshots e FFprobe dos arquivos reais; voz corresponde ao avatar e prévia ao enquadramento.

Em outra máquina, consumidor escrito somente com [GUIA.md](../api/GUIA.md) lista assets, cria intenção, faz polling e baixa MP4 por `/api/v1`. Não importar produto, acessar banco ou usar controlador E2E. Chave distinta não lê job de outra chave; download não pronto e credencial revogada são recusados. Registrar logs sem headers/Bearer.

## SCN-006 — matriz e Instagram manual (MH-02)

Gerar todas combinações e amostras de duração da [MATRIZ.md](MATRIZ.md). Metade das 16 combinações usa UI e metade API. Para cada amostra, registrar job/tentativa/receita/hash/digest/assets/formato/origem/duração/arquivo, avaliador/data, critérios e veredito real. `ready` não é veredito de qualidade.

Defeitos do combinado são corrigidos e reamostrados; reprovação não é excluída do histórico. Novos pedidos são registrados separadamente. Uma pessoa da equipe publica manualmente um MP4 9:16 na conta Instagram do cliente e registra aceitação; não introduzir integração Meta, automação ou credencial no sistema.

## SCN-007 — autonomia e revogação (MH-03)

Sem terminal/desenvolvedor, uma pessoa da equipe segue USO.md e cria terceiro avatar, quinto cenário e vídeo até download. Observe, não conduza os cliques no lugar dela; registre pessoa/data/jobs e dificuldades reais.

Depois o operador cliente revoga todos acessos temporários do desenvolvedor: SSH/túnel temporário, usuário do painel/sessões e **cada chave Bearer explicitamente**. Preserve identidade permanente do túnel/worker sob controle do cliente e chaves legítimas de integração. Remover usuário não revoga suas chaves automaticamente. Verificar recusa dos acessos temporários e concluir **um novo job pela API** até `ready` com credencial definitiva do cliente. Só então registrar continuidade/autonomia.

## Estado de bloqueio e fechamento

Atualmente, SSH GPU recusado, pesos/digest/piloto completos não verificados e material/domínio/equipe final ausentes impedem execução dos cenários remotos. Não preencher observações aprovadas nem congelar receita para contornar isso. Registre o pré-requisito exato e retome da primeira tarefa elegível quando houver acesso/material.

Concluir P06 exige MH-01–MH-08 reais, revisão independente atual e nenhum gap material. Depois construir/identificar RC e executar regressão integrada/homologação de release. Não declare sistema final entregue com apenas preparação local concluída.
