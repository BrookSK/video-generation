import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, request } from "../api";
import { failure, type AspectRatio, type GenerationConfig } from "../jobs";
import { MAX_SCENES, MIN_SCENES, SHOT_LABEL, type BrandIdentity, type LessonCreated, type NewLessonInput, type Shot } from "../lessons";
import { FieldError, Icon } from "../ui";
import type { Avatar } from "./AvatarDialog";
import type { Scene } from "./Scenes";

type Draft = { key: number; text: string; shot: Shot };
type Catalog = { avatars: Avatar[]; scenes: Scene[]; config: GenerationConfig; identity: BrandIdentity };

let nextKey = 0;
const draft = (): Draft => ({ key: nextKey++, text: "", shot: "medio" });

/** Campo do servidor "scenes.N.script_text" vira o índice N; outros campos ficam no formulário. */
function sceneIndex(field: string | undefined): number | undefined {
  const match = field?.replace(/^body\./, "").match(/^scenes\.(\d+)\.script_text$/);
  return match ? Number(match[1]) : undefined;
}

export function NewLesson() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<Catalog>();
  const [loadError, setLoadError] = useState<string>();
  const [avatarId, setAvatarId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [format, setFormat] = useState<AspectRatio>("9:16");
  const [drafts, setDrafts] = useState<Draft[]>(() => [draft(), draft()]);
  const [sceneErrors, setSceneErrors] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState<string>();
  const [sending, setSending] = useState(false);
  const locked = useRef(false);
  // Uma resposta perdida não é uma nova intenção; o retry conserva chave e pedido.
  const intent = useRef<{ fingerprint: string; key: string } | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      request<Avatar[]>("GET", "/panel/avatars"),
      request<Scene[]>("GET", "/panel/scenes"),
      request<GenerationConfig>("GET", "/panel/generation-config"),
      request<BrandIdentity>("GET", "/panel/brand-identity"),
    ])
      .then(([avatars, scenes, config, identity]) => active && setCatalog({ avatars, scenes, config, identity }))
      .catch((failed) => active && setLoadError(failure(failed)));
    return () => {
      active = false;
    };
  }, []);

  const avatar = catalog?.avatars.find((a) => a.id === avatarId && a.status === "ativo");
  const scene = catalog?.scenes.find((s) => s.id === sceneId && s.status === "ativo");
  const limit = catalog?.config.max_script_chars;
  const hasIdentity = Boolean(catalog?.identity.logo_url);
  const tooLong = (text: string) => limit != null && Array.from(text).length > limit;
  const anyTooLong = drafts.some((item) => tooLong(item.text));

  function update(index: number, change: Partial<Draft>) {
    setDrafts((current) => current.map((item, i) => (i === index ? { ...item, ...change } : item)));
    setSceneErrors({});
    setFormError(undefined);
  }

  function move(index: number, offset: number) {
    setDrafts((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(index + offset, 0, item!);
      return next;
    });
    setSceneErrors({});
  }

  function remove(index: number) {
    setDrafts((current) => current.filter((_, i) => i !== index));
    setSceneErrors({});
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked.current) return;
    setFormError(undefined);
    const empty = drafts.findIndex((item) => !item.text.trim());
    if (empty >= 0) {
      setSceneErrors({ [empty]: `Cena ${empty + 1}: escreva o texto da fala.` });
      document.getElementById(`lesson-scene-${empty}`)?.focus();
      return;
    }
    if (!hasIdentity || anyTooLong || !avatar || !scene || limit == null) return;
    locked.current = true;
    setSending(true);
    const payload: NewLessonInput = {
      avatar_id: avatar.id,
      scene_id: scene.id,
      aspect_ratio: format,
      scenes: drafts.map((item) => ({ script_text: item.text, shot: item.shot })),
    };
    const fingerprint = JSON.stringify(payload);
    if (intent.current?.fingerprint !== fingerprint) intent.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const created = await request<LessonCreated>("POST", "/panel/lessons", payload, { idempotencyKey: intent.current.key });
      navigate(`/aulas/${created.id}`, { state: { notice: "Aula na fila. As cenas são geradas uma a uma e depois montadas." } });
    } catch (failed) {
      const index = failed instanceof ApiError ? sceneIndex(failed.field ?? undefined) : undefined;
      if (index !== undefined) setSceneErrors({ [index]: failure(failed) });
      else setFormError(failure(failed));
    } finally {
      locked.current = false;
      setSending(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Nova aula</h1>
          <p>Divida a aula em cenas curtas. Cada cena vira um vídeo, e a aula sai em um arquivo com abertura e encerramento.</p>
        </div>
      </header>
      {loadError ? (
        <div role="alert">
          <FieldError id="lesson-load-error" message={loadError} />
        </div>
      ) : !catalog ? (
        <p role="status">Carregando avatares, cenários e identidade…</p>
      ) : (
        <form className="generation lesson-form" onSubmit={submit}>
          <div className="generation-fields">
            {!hasIdentity && (
              <p className="note" role="status">
                <Icon name="info" />
                <span>
                  Cadastre o logo e as cores antes de gerar uma aula. <Link to="/identidade">Abrir Identidade</Link>
                </span>
              </p>
            )}
            <fieldset className="generation-step" disabled={sending}>
              <legend>
                <span>1</span> Avatar
              </legend>
              <div className="picks" role="radiogroup" aria-label="Avatar">
                {catalog.avatars
                  .filter((a) => a.status === "ativo")
                  .map((a) => (
                    <label className="pick" key={a.id}>
                      <input type="radio" name="avatar" value={a.id} checked={avatar?.id === a.id} onChange={() => setAvatarId(a.id)} />
                      <img src={`/panel/avatars/${a.id}/files/prepared`} alt="" />
                      <span>
                        <b>{a.name}</b>
                        <small>Voz {a.voice}</small>
                      </span>
                    </label>
                  ))}
              </div>
              {!avatar && !catalog.avatars.some((a) => a.status === "ativo") && (
                <p className="note">
                  Nenhum avatar ativo. <Link to="/avatares">Cadastre um avatar</Link> e aguarde a preparação.
                </p>
              )}
            </fieldset>
            <fieldset className="generation-step" disabled={sending}>
              <legend>
                <span>2</span> Cenário
              </legend>
              <div className="picks" role="radiogroup" aria-label="Cenário">
                {catalog.scenes
                  .filter((s) => s.status === "ativo")
                  .map((s) => (
                    <label className="pick pick-scene" key={s.id}>
                      <input type="radio" name="scene" value={s.id} checked={scene?.id === s.id} onChange={() => setSceneId(s.id)} />
                      <img src={`/panel/scenes/${s.id}/files/preview-16x9`} alt="" />
                      <span>
                        <b>{s.name}</b>
                        <small>{s.background_color ? "Cor sólida" : "Imagem de fundo"}</small>
                      </span>
                    </label>
                  ))}
              </div>
              {!catalog.scenes.some((s) => s.status === "ativo") && (
                <p className="note">
                  Nenhum cenário ativo. <Link to="/cenarios/novo">Crie um cenário</Link> antes de gerar.
                </p>
              )}
            </fieldset>
            <fieldset className="generation-step" disabled={sending}>
              <legend>
                <span>3</span> Formato
              </legend>
              <div className="seg" role="radiogroup" aria-label="Formato">
                {(["9:16", "16:9"] as const).map((ratio) => (
                  <Fragment key={ratio}>
                    <input id={`lesson-ratio-${ratio}`} name="format" type="radio" checked={format === ratio} onChange={() => setFormat(ratio)} />
                    <label htmlFor={`lesson-ratio-${ratio}`}>
                      <i className={ratio === "9:16" ? "ratio-ico v" : "ratio-ico h"} />
                      {ratio}
                    </label>
                  </Fragment>
                ))}
              </div>
            </fieldset>
            <fieldset className="generation-step" disabled={sending}>
              <legend>
                <span>4</span> Cenas
              </legend>
              <p className="hint">
                De {MIN_SCENES} a {MAX_SCENES} cenas. O texto de cada cena é falado literalmente.
                {limit != null && ` Limite de ${limit} caracteres por cena.`}
              </p>
              <ol className="lesson-scenes">
                {drafts.map((item, index) => {
                  const position = index + 1;
                  const count = Array.from(item.text).length;
                  const error = tooLong(item.text) ? `Cena ${position}: o limite vigente é ${limit} caracteres. Encurte a fala.` : sceneErrors[index];
                  return (
                    <li key={item.key} className="lesson-scene">
                      <div className="field-row">
                        <label htmlFor={`lesson-scene-${index}`}>Cena {position}</label>
                        <div className="lesson-scene-tools">
                          <button className="btn btn-sm btn-quiet" type="button" aria-label={`Subir cena ${position}`} disabled={index === 0} onClick={() => move(index, -1)}>
                            Subir
                          </button>
                          <button className="btn btn-sm btn-quiet" type="button" aria-label={`Descer cena ${position}`} disabled={index === drafts.length - 1} onClick={() => move(index, 1)}>
                            Descer
                          </button>
                          <button className="btn btn-sm btn-quiet" type="button" aria-label={`Remover cena ${position}`} disabled={drafts.length <= MIN_SCENES} onClick={() => remove(index)}>
                            Remover
                          </button>
                        </div>
                      </div>
                      <textarea
                        id={`lesson-scene-${index}`}
                        className="textarea"
                        rows={3}
                        value={item.text}
                        aria-invalid={error ? true : undefined}
                        aria-describedby={`lesson-count-${index}${error ? ` lesson-error-${index}` : ""}`}
                        onChange={(event) => update(index, { text: event.target.value })}
                      />
                      <div className="field-row">
                        <div className="seg" role="radiogroup" aria-label={`Plano da cena ${position}`}>
                          {(["medio", "close"] as const).map((shot) => (
                            <Fragment key={shot}>
                              <input
                                id={`lesson-shot-${item.key}-${shot}`}
                                name={`lesson-shot-${item.key}`}
                                type="radio"
                                checked={item.shot === shot}
                                onChange={() => update(index, { shot })}
                              />
                              <label htmlFor={`lesson-shot-${item.key}-${shot}`}>{SHOT_LABEL[shot]}</label>
                            </Fragment>
                          ))}
                        </div>
                        <span className="hint" id={`lesson-count-${index}`}>
                          {count}
                          {limit == null ? " caracteres" : ` / ${limit} caracteres`}
                        </span>
                      </div>
                      {error && <FieldError id={`lesson-error-${index}`} message={error} />}
                    </li>
                  );
                })}
              </ol>
              <button className="btn" type="button" disabled={drafts.length >= MAX_SCENES} onClick={() => setDrafts((current) => [...current, draft()])}>
                <Icon name="plus" />
                Adicionar cena
              </button>
            </fieldset>
            {limit == null && (
              <p role="status" className="note">
                Geração indisponível: nenhuma receita vigente. A configuração será liberada após a calibração do gerador.
              </p>
            )}
            {formError && (
              <div role="alert">
                <FieldError id="lesson-form-error" message={formError} />
              </div>
            )}
            <div className="generation-action">
              <button
                className="btn btn-primary btn-lg"
                type="submit"
                disabled={sending || !hasIdentity || !avatar || !scene || anyTooLong || limit == null}
              >
                <span className="generate-tally" />
                {sending ? "Enviando…" : "Gerar aula"}
              </button>
              <p className="hint">A geração continua mesmo se você fechar esta tela.</p>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}
