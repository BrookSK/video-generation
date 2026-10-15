# Procedimento de homologação e entrega

## Fronteira da aceitação

P06 é a verificação no ambiente final do cliente. Código compilado, testes locais, mídia FFmpeg e catálogo sintético não aprovam GPU, qualidade, domínio, Instagram ou autonomia. Não homologue árvore fonte no lugar do release candidate identificado. Ao completar a fase e construir o RC, repita a regressão integrada e os gates de release conforme o método; não chame preparação local de release aprovado.

O cliente autoriza os materiais, a conexão entre as VPS, o domínio/registro de imagens e os avaliadores. O operador registra logs/metadados sem segredos; o avaliador humano fornece os vereditos. Custos continuam com o cliente, sem autorização implícita para contratar serviços ou automatizar ligar/desligar GPU.

Ordem: acesso/host → imagem do HEAD entregue na P07 publicada por digest → pesos/referências e conexão privada → piloto e avaliação → receita congelada → instalação → catálogo e jornadas reais → matriz/Instagram → autonomia/revogação. Qualquer pré-requisito ausente bloqueia o passo dependente, não autoriza material substituto.

## SCN-001 — host, modelos e conexão privada (MH-07)

1. DEC-005 autoriza a GPU e os seis materiais existentes; não solicitar novamente. Após recusa FIN-01, DEC-006 autoriza A100 80 GB spot FIN-03 com o clone temporário `P06-piloto-FIN03`, preservando o original `OS-fHuXBon4` detached em FIN-01. Usar somente saldo atual, sem recarga, com reserva de US$1; salvar amostras/evidências, executar sync e excluir somente `avatar-p06-pilot-ec4fad2` e o clone autorizado ao terminar/atingir reserva. Não excluir o original nem postar externamente. Confirmar estado, saldo, preço, IP e host key atuais no console/canal confiável. A GPU criada é `bde3697c-2d12-499a-95cd-77c435c2fc78`; o clone, `e5f8c4cb-b83a-4bce-83d6-9e77b6b6f028`. Preservar driver do provedor.
2. Guardar saída de `gpu-host-check.sh`: Ubuntu 24.04, driver ≥560.28.03, Docker/Compose/toolkit, nome da GPU e VRAM vistos no container.
3. Usar o candidato D001, fonte `50fc974ceadff502694522e77a5704e2cbed4c8d`, referência `vccr.io/5e20534f-f96c-42fb-8a52-deb4f7e28efc/avatar-worker@sha256:f2814d283009ef7ebcb941367b531631e5008623ef2667cc92eadd8d1c4f06ff`, sem substituir por `.Id`, reconstrução ou bind mounts de código. Dentro dele, conferir CUDA nos runtimes TTS/avatar, imports `flash_attn`/`xformers` e política comercial do manifesto. Montar receita/manifesto D001 correntes como dados externos em `/pilot/in:ro`; não reconstruir para trocar esses dados nem atribuir a prova histórica T05 do candidato anterior à imagem atual.
4. Completar `models-pull.sh` com a imagem atual: todos os arquivos/tamanhos/SHA-256 do manifesto, incluindo LoRA lightx2v e fontes Kokoro, sem arquivo parcial tratado como peso válido. Copiar os WAVs registrados `pf_dora.wav`/`pm_alex.wav` para `/srv/avatar/models/kokoro-voice-references` e conferir tamanho/hash conforme o guia; componentes derivados não são baixados pelo script. Não regenerar no Linux e aceitar bytes diferentes silenciosamente. Reexecutar o download: exit 0 e zero downloads. Preservar o manifesto completo, inclusive pesos fp8 não usados pelo draft; a prova histórica dos 35 pesos não cobre os componentes novos.
5. Com autorização e host key verificada, estabelecer túnel SSH ou rede privada autenticada CPU↔GPU. Supervisor autentica token em `/internal/v1`; banco não tem porta pública nem credenciais no worker. Pelo domínio público, `/internal/v1/claim` deve responder 404; ausência de credencial interna pública não basta para provar isolamento.

Evidência: observação, logs de host/modelos/runtime e controles de rede, referências/digests e versão do manifesto. Não guardar senha/token/SSH privado.

## SCN-002 — piloto real e C1–C7 (MH-04 e MH-08)

Use os dois avatares e quatro cenários existentes autorizados nesta execução pela DEC-005, com proveniência/prompts/hashes, ombros visíveis e texto pt-BR com números, valores, telefone, nomes e negativas. DEC-005 supera a antiga restrição de insumos DEC-003; não concede aprovação de qualidade, tempos ou assinatura humana. O piloto usa a imagem por digest conferida em SCN-001, receita externa somente de dados em `/pilot/in:ro` e fila declarativa `--queue`, sem rede: somente lo, sem SaaS nem download durante inferência. Modelos ficam somente leitura e o processo roda como `app`, uid 10001. O supervisor precisa de HTTP interno, mas o piloto isolado não recebe rede externa.

A janela DEC-006 não cobre o lote integral pelos tempos históricos: executar
somente o que couber com reserva, preservando evidência e mantendo todos os
gates não executados pendentes. Nesta execução, a raiz privada efetiva é
`/srv/avatar/pilot/p06-current/{in,out}`. Nenhum resultado de pré-medição ou
diagnóstico automático de fala concede aceite C1–C7 ou congelamento.

- Receita de calibração bf16 sem quantização, LoRA lightx2v com escala 1.0, quatro passos, guia de texto 1.0 e de áudio 2.0. Referências `kind: reference`: feminina `pf_dora.wav`, masculina `pm_alex.wav`, com os hashes registrados; Chatterbox permanece o TTS.
- Fala medida de 30 s nas duas vozes e nos dois formatos, 9:16 e 16:9, com `--runs 2`. As entradas `aprox30s` apenas aproximam duração textual; confirmar WAV/MP4 real por voz e reamostrar se necessário. No runner atual, `cold`/`warm` são rótulos da primeira/repetida execução por amostra: TTS/render iniciam novos processos e recarregam modelos em ambos os runs, sem controle de cache frio nem modelos residentes. Registrar esse limite; não alegar medição quente residente.
- Teste de 60 s em 9:16 antes de elevar limite, observando streaming/max_frame_num e deriva de cor.
- Se a GPU tiver **pelo menos 48 GB**, testar 720p sem quantização. A L40S anteriormente observada tinha 46.068 MiB disponíveis; registre capacidade nominal e memória disponível separadamente. Não descarte o teste só por converter GB para GiB ou descontar memória reservada; em dúvida, execute e registre o resultado real. A condição não é uma aprovação antecipada de 720p.
- Por etapa: tempo e pico de VRAM; perfil nativo/final, segundos de computação por segundo de vídeo, taxa de caracteres medida, texto/hash, versões/digests e interfaces de rede. FFprobe confere perfil e duração real.
- Ouvir as duas vozes e registrar diferenciação perceptiva; examinar mãos inventadas, objetos e artefatos de borda em 16:9. Parâmetros de composição/prompt configurados não são prova de qualidade.
- Obter decisão humana explícita sobre qualidade e viabilidade dos tempos medidos antes de congelar. O teste sintético frio anterior (~100 s de computação por segundo de vídeo) é referência histórica, não aprovação de desempenho.

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

1. Resolver domínio/HTTPS e registro de imagens sob controle do cliente. Construir/publicar API e painel com o commit aprovado; manter o worker no mesmo digest publicado e medido em SCN-001/002, sem reconstrução após freeze. Preencher ambiente privado com referências reais.
2. Executar `bash infra/scripts/check-release.sh`: ambas composições válidas, imagens sem build ativo/latest e com digest, todas variáveis no `.env.example`, documentos presentes e segredos privados seguros. Este guard valida configuração, não conteúdo da imagem nem aprovação humana.
3. Executar instalação por papel seguindo só INSTALACAO.md, repetir em clone/diretório limpo, registrar commit/digests e preservar volumes ativos. Confirmar HTTPS externo/certificado, login/logout e isolamento banco/internal. Na CPU só API/PostgreSQL/Caddy; na GPU somente worker, sem banco/storage direto.
4. Executar `backup.sh` no cliente e exercício de recuperação isolado conforme [OPERACAO.md](../operacao/OPERACAO.md). Evidência de dump/tar/manifest/COMPLETE e comparação de banco/mídia; não restaurar sobre instalação ativa.
5. Pelo painel, cadastrar 2 avatares e 4 cenários autorizados, reutilizando os seis materiais existentes da DEC-005 com proveniência e hashes. Ambos avatares precisam ficar ativos e cenários enquadrados nos dois formatos. A autorização não prova cadastro, qualidade ou aceite. Fixtures E2E não são o pacote inicial.

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

P07 está concluída localmente. A T05 foi exercitada em 2026-10-14 no candidato anterior: CUDA dos dois runtimes, 40 arquivos sem downloads, referências e ligação privada com claim/presença/upload reais. Em 2026-10-15, a retomada T06 criou a GPU FIN-03 e o clone autorizados, reutilizou os materiais e revelou publicação indevida de TTS sem EOS. D001 corrigiu essa falha, com RED/GREEN local e GPU e revisão independente; o candidato atual está em [INSTALACAO.md](../operacao/INSTALACAO.md). A política v3 não constitui aprovação semântica: uma amostra masculina real ainda esgotou o orçamento e foi corretamente recusada. Não tratar materiais/autorização como bloqueio. O lote integral, avaliação datada C1–C7, congelamento e instalação final permanecem pendentes, sem flexibilizar critérios pela janela de saldo.

Concluir P06 exige MH-01–MH-08 reais, revisão independente atual e nenhum gap material. Depois construir/identificar RC e executar regressão integrada/homologação de release. Não declare sistema final entregue com apenas preparação local concluída.
