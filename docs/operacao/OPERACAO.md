# Operação e recuperação

## Responsabilidades e limites

API, PostgreSQL e `/data` ficam na VPS CPU. A GPU executa o supervisor e os runtimes, monta `/models` somente leitura e fala apenas com a API interna pelo túnel autenticado. Painel, histórico e downloads continuam disponíveis sem GPU; novos vídeos ficam na fila. Ligar/desligar a GPU é operação do cliente, sem automação de nuvem.

Use o clone e o `.env` privados da instalação, permissões `600`, com as referências imutáveis aprovadas. Nunca execute seed, servidor E2E ou fixtures no cliente. Não rode `down --volumes`, `volume prune` nem apague `/data` para corrigir uma falha.

Os comandos abaixo rodam na raiz do clone da VPS CPU:

```bash
CPU=(docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.cpu.yml -f infra/compose/docker-compose.api.yml -f infra/compose/docker-compose.release.yml)
"${CPU[@]}" ps
"${CPU[@]}" logs --tail 100 api postgres caddy
"${CPU[@]}" exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5).status)"
df -h
```

Na VPS GPU:

```bash
GPU=(docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.worker.yml -f infra/compose/docker-compose.worker-release.yml)
"${GPU[@]}" ps
"${GPU[@]}" logs --tail 100 worker
nvidia-smi
df -h /srv/avatar/models /var/lib/docker
```

Logs e arquivos contêm dados do cliente; restrinja acesso e remova credenciais antes de compartilhar diagnóstico. Não publique `.env`, headers, cookies, imagens autorizadas ou backups no repositório. A interface de estado informa o código de erro e o `job_id`; consulte a tentativa correspondente, não crie intenções novas repetidamente.

## Reinício e incidentes

- GPU sem heartbeat: confirme máquina, túnel e worker; API saudável não comprova GPU saudável. Restaure primeiro o túnel e depois `"${GPU[@]}" restart worker`.
- `OUT_OF_MEMORY`: confira a receita/perfil aprovado e a VRAM. Não aumente limites nem troque modelo sem nova calibração e avaliação humana.
- `WORKER_LOST`: lease vencido reenfileira até três tentativas. Não marque `ready` manualmente; o arquivo completo precisa ser validado/publicado pelo worker.
- `INPUT_INVALID`: confira a fala e a duração máxima vigente. `RENDER_FAILED`/`OUTPUT_INVALID`: inspecione logs da tentativa e o manifesto, sem usar um vídeo substituto.
- API/banco: leia logs, confirme disco e saúde do PostgreSQL antes de `"${CPU[@]}" restart api`. O entrypoint aplica migrações na inicialização; um erro de migração bloqueia o serviço, não é ignorado.
- Arquivo pronto indisponível: confira volume `appdata`, backup e caminhos de tentativa; não edite o estado do job para ocultar perda de mídia.
- Atualização: faça backup, registre commit e referências de imagem, valide release, baixe imagens aprovadas e aplique a instalação. Reverter código não reverte automaticamente uma migração; recuperação usa o conjunto banco/arquivos/versão consistente.

No build de preparação P06, `npm audit` encontrou GHSA-68fv-2mgg-jv7q em `source-map-js` 1.2.1. A resolução transitiva de desenvolvimento foi atualizada para 1.2.2; não é uma dependência executada no Caddy final. Em cada nova versão, execute `npm ci`, `npm audit`, build e verificações antes de publicar imagens. Não use `npm audit fix --force` nem aprove scripts de instalação desconhecidos automaticamente. Um audit limpo não substitui revisão de segurança da aplicação ou verificação das imagens.

## Backup consistente

`backup.sh` exige API e PostgreSQL em execução. Reserva um diretório novo, para a API, faz `pg_dump` custom e arquiva `/data` num container sem iniciar a aplicação. Depois reativa a API e espera sua saúde. Com a API parada não há novos jobs, mutações ou uploads; o worker não escreve diretamente no banco nem em `/data`. Planeje essa indisponibilidade e, com autorização, pause o worker antes da janela para evitar uploads interrompidos e reenfileiramento por lease vencido.

```bash
install -d -m 700 /srv/avatar/backups
bash infra/scripts/backup.sh --destination "/srv/avatar/backups/$(date -u +%Y%m%dT%H%M%SZ)"
```

O diretório contém `database.dump`, `data.tar`, `manifest.json` (SHA-256 e image IDs de runtime, não digests de publicação) e `COMPLETE`. Sem `COMPLETE`, o conjunto é parcial e não serve para recuperação. Destino existente nunca é sobrescrito. Falha no dump/tar não declara sucesso; o trap tenta reativar a API. SIGKILL, queda de host ou perda do Docker não permitem executar trap: o operador precisa conferir `ps` e executar `"${CPU[@]}" start --wait api` quando seguro.

Um lock exclusivo em `/tmp/avatar-backup-<projeto>.lock` impede snapshots concorrentes no host. Após interrupção abrupta, o lock pode permanecer: só remova o diretório vazio depois de confirmar que nenhum backup desse projeto está em execução e que a API voltou saudável. Use um único operador/host para cada projeto; scripts executados em hosts diferentes não compartilham esse lock.

Guarde separadamente, em cofre controlado pelo cliente: `.env`, segredo/túnel/host keys, commit do código, digests publicados, receita aprovada e autorizações. Não os inclua no arquivo público de evidências. Backup é dado sensível, não é criptografado pelo script; copie-o para armazenamento privado protegido/criptografado segundo a política do cliente. Verifique espaço antes, retenção e restauração regularmente. Não remova o último backup comprovado antes de verificar o novo.

Valide integridade antes de restaurar:

```bash
python3 - /srv/avatar/backups/CONJUNTO-ESCOLHIDO <<'PY'
import hashlib, json, sys
from pathlib import Path
p = Path(sys.argv[1])
assert (p / 'COMPLETE').is_file(), 'Backup parcial'
for name, expected in json.loads((p / 'manifest.json').read_text())['sha256'].items():
    with (p / name).open('rb') as source:
        assert hashlib.file_digest(source, 'sha256').hexdigest() == expected, name
print('Integridade conferida; isso ainda não comprova restauração.')
PY
```

## Recuperação em ambiente isolado

Nunca restaure diretamente sobre volumes da instalação ativa. Um backup válido inclui banco e arquivos do mesmo instante, a versão do código/imagens e a receita correspondente. PostgreSQL 18 restaura o dump com ferramentas compatíveis; não use outra major sem validar migração.

1. Com o cliente, escolha um backup íntegro e a versão correspondente. Crie um clone separado e projeto Compose novo, por exemplo `avatar-restore`, com volumes novos. Não publique portas 80/443 nem reutilize nome `avatar`; use um override de recuperação sem portas ou em loopback e não inicie GPU/túnel.
2. No projeto isolado, inicie apenas PostgreSQL e aguarde saúde. O banco de destino precisa estar vazio. Importe o dump antes de iniciar a API:

```bash
# RESTORE é o array Compose do projeto ISOLADO, definido e conferido pelo operador.
"${RESTORE[@]}" exec -T postgres pg_restore --exit-on-error --no-owner --username=avatar --dbname=avatar < "$BACKUP/database.dump"
"${RESTORE[@]}" run --rm --no-deps --user 0 --entrypoint tar api -C /data -xf - < "$BACKUP/data.tar"
"${RESTORE[@]}" up -d --wait api
```

3. Verifique `/readyz`, login, catálogo, IDs/estados de jobs e download de mídia conhecido; compare SHA-256 com o arquivo original. Confira ownership dos arquivos para UID 10001 da API; o tar preserva os IDs originais. Sem mídia original íntegra ou referência registrada não declare recuperação comprovada.
4. Registre resultado e mantenha a instalação ativa intacta. Substituição exige janela/autorização do cliente, novo backup do estado atual, atualização de endpoints e conferência das credenciais. Não conecte dois workers a instalações diferentes com os mesmos acessos por acidente.
5. Revogue acessos temporários criados para o exercício e retome o worker no ambiente escolhido. Uma nova geração real deve concluir `ready` após recuperação.

O exercício local automatizado usa a imagem real da API e PostgreSQL descartável, restaura linha e arquivo sentinela exatos e induz uma falha real de leitura para conferir reativação. Isso não substitui o teste de restauração da instalação do cliente:

```bash
docker build -f infra/docker/api.Dockerfile -t avatar-api:p06-local .
bash infra/scripts/tests/test-backup.sh
```
