import { useEffect, useState } from "react";
import { Link } from "react-router";

import { request } from "../api";
import { failure, STATUS_LABEL, STAGES, type JobStatus, type VideoJob, type WorkerPresence } from "../jobs";
import { FieldError } from "../ui";

/** Polling serial; um request lento não produz uma fila de requests sobrepostos. */
export function useJobPolling<T>(path: string) {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setState({ data: null, error: null });
    async function poll() {
      try {
        const data = await request<T>("GET", path);
        if (active) setState({ data, error: null });
      } catch (failed) {
        if (active) setState((previous) => ({ ...previous, error: failure(failed) }));
      } finally {
        if (active) timer = setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [path]);
  return state;
}

export function WorkerWarning({ data, error }: { data: WorkerPresence | null; error: string | null }) {
  if (error) return <p className="note" role="status">Não foi possível consultar o gerador: {error} O estado da GPU é desconhecido.</p>;
  if (!data) return null;
  const absent = data.last_heartbeat_at === null || Date.now() - Date.parse(data.last_heartbeat_at) > 120000;
  if (!absent) return null;
  return <aside className="worker-warning" role="status"><p><b>Gerador sem resposta</b></p><p>{data.last_heartbeat_at ? `Último sinal: ${new Date(data.last_heartbeat_at).toLocaleString("pt-BR")}.` : "Ainda não recebemos nenhum sinal do gerador."} A API e o painel estão acessíveis, mas o worker de vídeo na GPU não está confirmado. Vídeos permanecem na fila até o gerador retomar.</p></aside>;
}

export function JobChip({ status }: { status: JobStatus }) {
  return <span className={`chip st-${status}`}><span className="dot" />{STATUS_LABEL[status]}</span>;
}

export function JobStages({ stage }: { stage: string | null }) {
  const index = STAGES.findIndex((s) => s.id === stage);
  return <ol className="steps" aria-label="Etapas da geração">{STAGES.map((item, i) => <li key={item.id} className={i === index ? "current" : i < index ? "complete" : undefined} aria-current={i === index ? "step" : undefined}>{item.label}</li>)}</ol>;
}

export function History() {
  const jobs = useJobPolling<VideoJob[]>("/panel/jobs");
  const presence = useJobPolling<WorkerPresence>("/panel/worker-status");
  const [filter, setFilter] = useState<JobStatus | "all">("all");
  const visible = jobs.data?.filter((job) => filter === "all" || job.status === filter);
  const queue = jobs.data?.filter((job) => job.status === "queued").slice().reverse() ?? [];

  return <div className="page">
    <header className="page-head"><div><h1>Histórico</h1><p>Vídeos da equipe, do painel e da API. Atualiza a cada 3 s.</p></div><Link className="btn btn-primary" to="/novo-video">Novo vídeo</Link></header>
    <WorkerWarning {...presence} />
    <div className="toolbar"><div className="field"><label htmlFor="job-filter">Estado</label><select id="job-filter" className="select" value={filter} onChange={(event) => setFilter(event.target.value as JobStatus | "all")}><option value="all">Todos</option>{Object.entries(STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
    {jobs.error && <div role="alert"><FieldError id="history-error" message={jobs.error} /><p className="hint">{jobs.data ? "Exibindo o último estado recebido. A atualização será tentada novamente." : "Tentaremos carregar novamente em 3 s."}</p></div>}
    {!jobs.data && !jobs.error && <p role="status">Carregando vídeos…</p>}
    {visible?.length === 0 ? <section className="empty-jobs"><h2>{jobs.data?.length ? "Nenhum vídeo neste estado" : "Ainda não há vídeos"}</h2><p>{jobs.data?.length ? "Escolha outro filtro para ver os vídeos da equipe." : "Crie um vídeo com os avatares e cenários cadastrados."}</p>{!jobs.data?.length && <Link className="btn" to="/novo-video">Criar o primeiro vídeo</Link>}</section> : <ul className="job-list">{visible?.map((job) => <li className="job-row" key={job.id}>
      <div className="job-copy"><Link to={`/videos/${job.id}`}>{job.script_text}</Link><div className="job-tags"><span className="tag">{job.avatar_name}</span><span className="tag">{job.scene_name}</span><span className="tag">{job.aspect_ratio}</span><span className="tag">{job.origin === "panel" ? "Painel" : "API"}</span></div><p className="hint">{new Date(job.created_at).toLocaleString("pt-BR")} · {job.requested_by}</p>{job.error && <p className="error-text">{job.error.message} <code>{job.error.code}</code></p>}</div>
      <div className="job-state"><JobChip status={job.status} />{job.status === "queued" && <span className="hint">Posição {queue.findIndex((entry) => entry.id === job.id) + 1}</span>}{job.status === "processing" && <><span>{STAGES.find((stage) => stage.id === job.stage)?.label ?? "Preparando geração"}</span>{job.started_at && <span className="hint">{Math.max(0, Math.floor((Date.now() - Date.parse(job.started_at)) / 1000))} s decorridos</span>}</>}<Link className="btn btn-sm" to={`/videos/${job.id}`}>{job.status === "ready" ? "Ver vídeo" : "Acompanhar"}</Link></div>
    </li>)}</ul>}
  </div>;
}
