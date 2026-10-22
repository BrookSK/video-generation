import { Link } from "react-router";

import { LESSON_STATUS_LABEL, type Lesson, type LessonStatus } from "../lessons";
import { FieldError } from "../ui";
import { useJobPolling } from "./History";

export function LessonChip({ status }: { status: LessonStatus }) {
  return (
    <span className={`chip st-${status}`}>
      <span className="dot" />
      {LESSON_STATUS_LABEL[status]}
    </span>
  );
}

/** Quantas cenas já estão prontas, para a lista e a tela da aula. */
export const readyScenes = (lesson: Lesson) => lesson.scenes.filter((scene) => scene.status === "ready").length;

export function Lessons() {
  const lessons = useJobPolling<Lesson[]>("/panel/lessons");

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Aulas</h1>
          <p>Aulas da equipe com o andamento de cada cena. Atualiza a cada 3 s.</p>
        </div>
        <Link className="btn btn-primary" to="/aulas/nova">
          Nova aula
        </Link>
      </header>
      {lessons.error && (
        <div role="alert">
          <FieldError id="lessons-error" message={lessons.error} />
          <p className="hint">{lessons.data ? "Exibindo o último estado recebido." : "Tentaremos carregar novamente em 3 s."}</p>
        </div>
      )}
      {!lessons.data && !lessons.error && <p role="status">Carregando aulas…</p>}
      {lessons.data?.length === 0 ? (
        <section className="empty-jobs">
          <h2>Ainda não há aulas</h2>
          <p>Monte uma aula com duas ou mais cenas e baixe um único vídeo com abertura e encerramento.</p>
          <Link className="btn" to="/aulas/nova">
            Criar a primeira aula
          </Link>
        </section>
      ) : (
        <ul className="job-list">
          {lessons.data?.map((lesson) => (
            <li className="job-row" key={lesson.id}>
              <div className="job-copy">
                <Link to={`/aulas/${lesson.id}`}>{lesson.scenes[0]?.script_text ?? "Aula"}</Link>
                <div className="job-tags">
                  <span className="tag">{lesson.scenes.length} cenas</span>
                  <span className="tag">{lesson.avatar_name}</span>
                  <span className="tag">{lesson.scene_name}</span>
                  <span className="tag">{lesson.aspect_ratio}</span>
                </div>
                <p className="hint">
                  {new Date(lesson.created_at).toLocaleString("pt-BR")} · {lesson.requested_by}
                </p>
                {lesson.error && (
                  <p className="error-text">
                    {lesson.error.message} <code>{lesson.error.code}</code>
                  </p>
                )}
              </div>
              <div className="job-state">
                <LessonChip status={lesson.status} />
                {lesson.status === "queued" && (
                  <span className="hint">
                    {readyScenes(lesson)} de {lesson.scenes.length} cenas prontas
                  </span>
                )}
                <Link className="btn btn-sm" to={`/aulas/${lesson.id}`}>
                  {lesson.status === "ready" ? "Ver aula" : "Acompanhar"}
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
