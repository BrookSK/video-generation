# Matriz de homologação do cliente

**Estado: não executada no ambiente final. Não há aceite de GPU, receita ou cliente.** A preparação local de P04/P05 e dos scripts de P06 não preenche esta matriz. Os códigos A1/A2 e S1–S4 identificam posições do pacote autorizado, não assets fictícios já cadastrados.

## Pré-requisitos e identificação

- GPU acessível, host/runtimes reais aprovados e todos os pesos conferidos por tamanho/SHA-256; segunda execução do downloader sem downloads.
- Imagem real do worker identificada por digest de publicação, piloto C1–C7 aprovado e receita frozen carregada na API.
- Duas fotos autorizadas, A1 com voz feminina e A2 com voz masculina, ombros visíveis; quatro cenários S1–S4 autorizados e enquadrados nos dois formatos. IDs reais, nomes e autorização devem ser registrados antes da execução. Voz é referência autorizada ou padrão do checkpoint aprovado, nunca material sem licença.
- Instalação do cliente com HTTPS e túnel autenticado, API/banco/storage na CPU, worker sem acesso ao banco. Cliente e avaliador humano presentes.

A última observação de acesso à GPU foi conexão SSH recusada em `117.18.102.52:30108`. Não há ainda amostras reais aprovadas, pesos completos conferidos ou domínio/registro de imagens final resolvidos. Reabrir o acesso não substitui essas verificações.

## Combinações obrigatórias

Metade pela UI, metade pela API. A API usa chave própria e o guia publicado; não usa sessão do painel nem endpoints internos. As falas contêm números, valores, telefone, nomes e negativas; texto não é roteiro por IA. Um resultado rejeitado precisa de nova amostra, sem apagar o registro da rejeição.

| Amostra | Avatar | Cenário | Formato | Origem | Estado observado |
|---|---|---|---|---|---|
| M01 | A1 | S1 | 9:16 | UI | Não executado |
| M02 | A1 | S1 | 16:9 | API | Não executado |
| M03 | A1 | S2 | 9:16 | UI | Não executado |
| M04 | A1 | S2 | 16:9 | API | Não executado |
| M05 | A1 | S3 | 9:16 | UI | Não executado |
| M06 | A1 | S3 | 16:9 | API | Não executado |
| M07 | A1 | S4 | 9:16 | UI | Não executado |
| M08 | A1 | S4 | 16:9 | API | Não executado |
| M09 | A2 | S1 | 9:16 | API | Não executado |
| M10 | A2 | S1 | 16:9 | UI | Não executado |
| M11 | A2 | S2 | 9:16 | API | Não executado |
| M12 | A2 | S2 | 16:9 | UI | Não executado |
| M13 | A2 | S3 | 9:16 | API | Não executado |
| M14 | A2 | S3 | 16:9 | UI | Não executado |
| M15 | A2 | S4 | 9:16 | API | Não executado |
| M16 | A2 | S4 | 16:9 | UI | Não executado |

## Duração e limites

Além das combinações, gerar para **cada avatar e formato** uma amostra de 30 s e outra no limite realmente aprovado na receita. O limite inicial é 40 s; 60 s não entra em produção apenas porque o campo aceita mais caracteres. Uma fala curta não comprova uma amostra de 30 s; a duração vem do áudio/FFprobe.

| Amostra | Avatar | Formato | Duração requerida | Estado observado |
|---|---|---|---|---|
| D01 | A1 | 9:16 | 30 s | Não executado |
| D02 | A1 | 16:9 | 30 s | Não executado |
| D03 | A2 | 9:16 | 30 s | Não executado |
| D04 | A2 | 16:9 | 30 s | Não executado |
| D05 | A1 | 9:16 | Limite aprovado | Não executado |
| D06 | A1 | 16:9 | Limite aprovado | Não executado |
| D07 | A2 | 9:16 | Limite aprovado | Não executado |
| D08 | A2 | 16:9 | Limite aprovado | Não executado |

## Registro obrigatório por amostra real

Após cada geração, acrescentar um registro identificado pelo código acima contendo: `job_id`, tentativa, asset IDs reais, texto literal ou referência privada/hash, formato/origem, receita e seu hash, digest do worker, arquivo e SHA-256, perfil/duração FFprobe, data/hora, nome do avaliador autorizado, naturalidade, movimento além da boca, sincronia, voz, recorte e fundo, avaliação C1–C7 e veredito **aprovado/reprovado**. Não registrar aprovado automaticamente a partir de `ready`, exit 0 ou imagem visualmente plausível.

Reprovação inclui critério/evidência, correção do combinado, nova receita/parâmetro quando necessário e nova amostra vinculada à anterior. O veredito só pode ser escrito após ser fornecido pelo avaliador real. Material privado e tokens ficam fora do repositório/evidências públicas.

## Evidências finais adicionais

- **Instagram manual:** não executado. Equipe do cliente precisa subir um MP4 9:16 real e registrar arquivo/hash, responsável, data e aceitação pela plataforma. Produto nunca recebe credencial Instagram/Meta.
- **Autonomia:** não executada. Equipe precisa criar terceiro avatar, quinto cenário e vídeo usando só painel/documentação, sem terminal ou desenvolvedor.
- **Revogação:** não executada. Operador precisa revogar SSH, usuário/sessões e explicitamente as chaves Bearer temporárias do desenvolvedor; depois um novo job pela API precisa terminar `ready`. Remover usuário sozinho não revoga Bearer.
- **Instalação/backup:** não executados no cliente. Registrar clone limpo, versões/digests, HTTPS externo, limites públicos e backup/restore real conforme OPERACAO.md.

Procedimentos e critérios estão em [PROCEDIMENTO.md](PROCEDIMENTO.md). Pedidos novos ficam em [FORA_DO_ESCOPO.md](FORA_DO_ESCOPO.md); defeitos do combinado não são extra.
