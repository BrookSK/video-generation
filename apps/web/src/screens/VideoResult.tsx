import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { STATUS_LABEL, type VideoJob, type WorkerPresence } from "../jobs";
import { FieldError, Icon } from "../ui";
import { JobChip, JobStages, useJobPolling, WorkerWarning } from "./History";

export function VideoResult() {
  const { id } = useParams();
  const location = useLocation();
  const result = useJobPolling<VideoJob>(`/panel/jobs/${id}`);
  const presence = useJobPolling<WorkerPresence>("/panel/worker-status");
  const [mediaError, setMediaError] = useState(false);
  const job = result.data;
  const downloadable = job?.status === "ready" && job.file_exists && job.download_url;
  const notice = (location.state as { notice?: string } | null)?.notice;

  return <div className="page">
    <header className="page-head"><div><Link className="back" to="/historico"><Icon name="chev" /> Histórico</Link><h1>Resultado do vídeo</h1></div>{job && <JobChip status={job.status} />}</header>
    {notice && <p role="status" className="note">{notice}</p>}
    <WorkerWarning {...presence} />
    {result.error && <div role="alert"><FieldError id="result-error" message={result.error} />{job && <p className="hint">Exibindo o último estado recebido; aguardando nova atualização.</p>}</div>}
    {!job && !result.error && <p role="status">Carregando vídeo…</p>}
    {job && <div className="result">
      <section className="stage result-stage" aria-label="Vídeo e estado da geração">
        <div className="stage-bar"><span>{job.avatar_name} · {job.scene_name}</span><b>{job.aspect_ratio}</b></div>
        {downloadable ? <><video key={job.id} src={job.download_url!} controls preload="metadata" aria-label="Vídeo gerado" onError={() => setMediaError(true)} onLoadedMetadata={() => setMediaError(false)} />{mediaError && <p role="alert">Não foi possível reproduzir o arquivo. Tente baixar o MP4 ou recarregar a página.</p>}</> : <div className="result-state">
          <h2>{job.status === "ready" ? "Arquivo indisponível" : STATUS_LABEL[job.status]}</h2>
          {job.status === "queued" && <p>O pedido está salvo. A geração começa quando o worker de vídeo estiver disponível.</p>}
          {job.status === "processing" && <><p>A geração continua na GPU. Você pode sair e voltar a esta página.</p>{job.started_at && <p>{Math.max(0, Math.floor((Date.now() - Date.parse(job.started_at)) / 1000))} s decorridos</p>}</>}
          {job.status === "failed" && <><p>{job.error?.message ?? "A geração falhou. Confira os dados antes de tentar novamente."}</p>{job.error && <code className="mono">{job.error.code}</code>}</>}
          {job.status === "ready" && <p>O vídeo foi concluído, mas o arquivo não está no armazenamento. Peça ao responsável pela instalação para verificar o volume de dados.</p>}
        </div>}
        {job.status === "processing" && <JobStages stage={job.stage} />}
      </section>
      <aside className="result-details">
        <h2>Dados do vídeo</h2>
        <dl><dt>Avatar</dt><dd>{job.avatar_name}</dd><dt>Voz</dt><dd>{job.voice}</dd><dt>Cenário</dt><dd>{job.scene_name}</dd><dt>Formato</dt><dd>{job.aspect_ratio}</dd><dt>Origem</dt><dd>{job.origin === "panel" ? "Painel" : "API"}</dd><dt>Solicitante</dt><dd>{job.requested_by}</dd><dt>Criado</dt><dd>{new Date(job.created_at).toLocaleString("pt-BR")}</dd>{job.finished_at && <><dt>Concluído</dt><dd>{new Date(job.finished_at).toLocaleString("pt-BR")}</dd></>}{job.duration_seconds != null && <><dt>Duração</dt><dd>{job.duration_seconds.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} s</dd></>}{job.size_bytes != null && <><dt>Arquivo</dt><dd>{(job.size_bytes / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MB · MP4</dd></>}</dl>
        <h3>Texto da fala</h3><p className="literal-text">{job.script_text}</p>
        {downloadable ? <><a className="btn btn-primary btn-lg" href={job.download_url!} download>Baixar MP4</a><p className="hint">Baixe o arquivo e publique manualmente no Instagram ou em outra plataforma. O sistema não publica por você.</p></> : <><button className="btn" disabled>Download indisponível</button><p className="hint">O download é liberado quando o vídeo estiver pronto e o arquivo disponível.</p></>}
        <Link className="btn" to="/novo-video" state={{ redo: { script_text: job.script_text, avatar_id: job.avatar_id, scene_id: job.scene_id, aspect_ratio: job.aspect_ratio } }}>Refazer com os mesmos dados</Link>
      </aside>
    </div>}
  </div>;
}
