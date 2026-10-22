import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { STAGES } from "../jobs";
import { LESSON_STATUS_LABEL, SHOT_LABEL, type Lesson } from "../lessons";
import { FieldError, Icon } from "../ui";
import { JobChip, useJobPolling } from "./History";
import { LessonChip, readyScenes } from "./Lessons";

const MB = 1024 * 1024;

function StateText({ lesson }: { lesson: Lesson }) {
  if (lesson.status === "queued") {
    return (
      <p>
        {readyScenes(lesson)} de {lesson.scenes.length} cenas prontas. A montagem começa quando todas estiverem prontas.
      </p>
    );
  }
  if (lesson.status === "assembling") return <p>Todas as cenas estão prontas. A aula está sendo montada com abertura e encerramento.</p>;
  return (
    <>
      <p>{lesson.error?.message ?? "A aula falhou."}</p>
      {lesson.error && <code className="mono">{lesson.error.code}</code>}
    </>
  );
}

export function LessonResult() {
  const { id } = useParams();
  const location = useLocation();
  const result = useJobPolling<Lesson>(`/panel/lessons/${id}`);
  const [mediaError, setMediaError] = useState(false);
  const lesson = result.data;
  const download = lesson?.status === "ready" ? lesson.download_url : null;
  const notice = (location.state as { notice?: string } | null)?.notice;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <Link className="back" to="/aulas">
            <Icon name="chev" /> Aulas
          </Link>
          <h1>Aula</h1>
        </div>
        {lesson && <LessonChip status={lesson.status} />}
      </header>
      {notice && lesson?.status === "queued" && (
        <p role="status" className="note">
          {notice}
        </p>
      )}
      {result.error && (
        <div role="alert">
          <FieldError id="lesson-error" message={result.error} />
          {lesson && <p className="hint">Exibindo o último estado recebido; aguardando nova atualização.</p>}
        </div>
      )}
      {!lesson && !result.error && <p role="status">Carregando aula…</p>}
      {lesson && (
        <div className="result">
          <section className="stage result-stage" aria-label="Vídeo e estado da aula">
            <div className="stage-bar">
              <span>
                {lesson.avatar_name} · {lesson.scene_name}
              </span>
              <b>{lesson.aspect_ratio}</b>
            </div>
            {download ? (
              <>
                <video key={lesson.id} src={download} controls preload="metadata" aria-label="Aula gerada" onError={() => setMediaError(true)} onLoadedMetadata={() => setMediaError(false)} />
                {mediaError && <p role="alert">Não foi possível reproduzir o arquivo. Tente baixar o MP4 ou recarregar a página.</p>}
              </>
            ) : (
              <div className="result-state">
                <h2>{LESSON_STATUS_LABEL[lesson.status]}</h2>
                <StateText lesson={lesson} />
              </div>
            )}
          </section>
          <aside className="result-details">
            <h2>Dados da aula</h2>
            <dl>
              <dt>Avatar</dt>
              <dd>{lesson.avatar_name}</dd>
              <dt>Cenário</dt>
              <dd>{lesson.scene_name}</dd>
              <dt>Formato</dt>
              <dd>{lesson.aspect_ratio}</dd>
              <dt>Cores</dt>
              <dd className="mono">
                {lesson.background_color} · {lesson.accent_color}
              </dd>
              <dt>Solicitante</dt>
              <dd>{lesson.requested_by}</dd>
              <dt>Criada</dt>
              <dd>{new Date(lesson.created_at).toLocaleString("pt-BR")}</dd>
              {lesson.finished_at && (
                <>
                  <dt>Concluída</dt>
                  <dd>{new Date(lesson.finished_at).toLocaleString("pt-BR")}</dd>
                </>
              )}
              {lesson.size_bytes != null && (
                <>
                  <dt>Arquivo</dt>
                  <dd>{(lesson.size_bytes / MB).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MB · MP4</dd>
                </>
              )}
            </dl>
            {download ? (
              <a className="btn btn-primary btn-lg" href={download} download>
                Baixar MP4
              </a>
            ) : (
              <button className="btn" type="button" disabled>
                Download indisponível
              </button>
            )}
          </aside>
          <section className="lesson-progress" aria-labelledby="lesson-scenes-title">
            <h2 id="lesson-scenes-title">Cenas</h2>
            <ol className="lesson-scenes">
              {lesson.scenes.map((scene) => (
                <li key={scene.position} className="lesson-scene" aria-label={`Cena ${scene.position}`}>
                  <div className="field-row">
                    <b>
                      Cena {scene.position} · {SHOT_LABEL[scene.shot]}
                    </b>
                    <JobChip status={scene.status} />
                  </div>
                  <p className="literal-text">{scene.script_text}</p>
                  {scene.status === "processing" && (
                    <p className="hint">{STAGES.find((stage) => stage.id === scene.stage)?.label ?? "Preparando geração"}</p>
                  )}
                  {scene.error && (
                    <p className="error-text">
                      {scene.error.message} <code>{scene.error.code}</code>
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </div>
  );
}
