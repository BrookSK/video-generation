import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, request } from "../api";
import { failure, type AspectRatio, type GenerationConfig } from "../jobs";
import {
  MAX_SCENES,
  MAX_TOPIC_CHARS,
  MAX_TOPICS,
  MIN_SCENES,
  SHOT_LABEL,
  type BrandIdentity,
  type LessonCreated,
  type LessonImage,
  type NewLessonInput,
  type Shot,
} from "../lessons";
import { FieldError, Icon } from "../ui";
import type { Avatar } from "./AvatarDialog";
import type { Scene } from "./Scenes";

type Draft = { key: number; text: string; shot: Shot; topics: string; image: (LessonImage & { name: string }) | null; uploading: boolean };
type SceneField = "text" | "topics" | "image";
type Catalog = { avatars: Avatar[]; scenes: Scene[]; config: GenerationConfig; identity: BrandIdentity };

let nextKey = 0;
const draft = (): Draft => ({ key: nextKey++, text: "", shot: "medio", topics: "", image: null, uploading: false });
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const SERVER_FIELD: Record<string, SceneField> = { script_text: "text", topics: "topics", image_file_id: "image" };

/** Um tópico por linha; linhas em branco não contam. O texto do tópico vai como foi escrito. */
const topicLines = (text: string) => text.split("\n").filter((line) => line.trim());

function topicsError(text: string, position: number): string | undefined {
  const topics = topicLines(text);
  if (topics.length > MAX_TOPICS) return `Cena ${position}: no máximo ${MAX_TOPICS} tópicos.`;
  const long = topics.findIndex((topic) => Array.from(topic).length > MAX_TOPIC_CHARS);
  return long >= 0 ? `Cena ${position}: o tópico ${long + 1} passa de ${MAX_TOPIC_CHARS} caracteres.` : undefined;
}

/** Campo do servidor "scenes.N.<campo>" vira a cena N e o campo da tela; "music_enabled", a trilha. */
function errorKey(field: string | null, drafts: Draft[]): string | undefined {
  const name = field?.replace(/^body\./, "");
  if (name === "music_enabled") return "music";
  const match = name?.match(/^scenes\.(\d+)\.(\w+)$/);
  const item = match ? drafts[Number(match[1])] : undefined;
  const kind = match ? SERVER_FIELD[match[2]!] : undefined;
  return item && kind ? `${item.key}:${kind}` : undefined;
}

export function NewLesson() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<Catalog>();
  const [loadError, setLoadError] = useState<string>();
  const [avatarId, setAvatarId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [format, setFormat] = useState<AspectRatio>("9:16");
  const [drafts, setDrafts] = useState<Draft[]>(() => [draft(), draft()]);
  const [music, setMusic] = useState(false);
  // Erros por campo: "<chave da cena>:text|topics|image" ou "music".
  const [errors, setErrors] = useState<Record<string, string>>({});
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
  const hasMusic = Boolean(catalog?.identity.music_url);
  const tooLong = (text: string) => limit != null && Array.from(text).length > limit;
  const anyInvalid = drafts.some((item, index) => tooLong(item.text) || topicsError(item.topics, index + 1));
  const uploading = drafts.some((item) => item.uploading);

  function change(key: number, next: Partial<Draft>) {
    setDrafts((current) => current.map((item) => (item.key === key ? { ...item, ...next } : item)));
  }

  function update(index: number, next: Partial<Draft>) {
    change(drafts[index]!.key, next);
    setErrors({});
    setFormError(undefined);
  }

  async function attach(item: Draft, position: number, file: File) {
    const fail = (message: string) => setErrors((current) => ({ ...current, [`${item.key}:image`]: message }));
    setErrors(({ [`${item.key}:image`]: _old, ...rest }) => rest);
    if (!IMAGE_TYPES.includes(file.type)) {
      fail(`Cena ${position}: envie a imagem em JPEG, PNG ou WebP.`);
      return;
    }
    const body = new FormData();
    body.append("file", file, file.name);
    change(item.key, { uploading: true });
    try {
      const image = await request<LessonImage>("POST", "/panel/lessons/images", body);
      change(item.key, { image: { ...image, name: file.name }, uploading: false });
    } catch (failed) {
      change(item.key, { uploading: false });
      fail(failure(failed));
    }
  }

  function move(index: number, offset: number) {
    setDrafts((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(index + offset, 0, item!);
      return next;
    });
    setErrors({});
  }

  function remove(index: number) {
    setDrafts((current) => current.filter((_, i) => i !== index));
    setErrors({});
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked.current) return;
    setFormError(undefined);
    const empty = drafts.findIndex((item) => !item.text.trim());
    if (empty >= 0) {
      setErrors({ [`${drafts[empty]!.key}:text`]: `Cena ${empty + 1}: escreva o texto da fala.` });
      document.getElementById(`lesson-scene-${empty}`)?.focus();
      return;
    }
    if (!hasIdentity || anyInvalid || uploading || !avatar || !scene || limit == null) return;
    locked.current = true;
    setSending(true);
    const payload: NewLessonInput = {
      avatar_id: avatar.id,
      scene_id: scene.id,
      aspect_ratio: format,
      scenes: drafts.map((item) => ({
        script_text: item.text,
        shot: item.shot,
        topics: topicLines(item.topics),
        image_file_id: item.image?.id ?? null,
      })),
      music_enabled: music,
    };
    const fingerprint = JSON.stringify(payload);
    if (intent.current?.fingerprint !== fingerprint) intent.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const created = await request<LessonCreated>("POST", "/panel/lessons", payload, { idempotencyKey: intent.current.key });
      navigate(`/aulas/${created.id}`, { state: { notice: "Aula na fila. As cenas são geradas uma a uma e depois montadas." } });
    } catch (failed) {
      const key = failed instanceof ApiError ? errorKey(failed.field, drafts) : undefined;
      if (key !== undefined) setErrors({ [key]: failure(failed) });
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
                  const error = tooLong(item.text) ? `Cena ${position}: o limite vigente é ${limit} caracteres. Encurte a fala.` : errors[`${item.key}:text`];
                  const topics = topicLines(item.topics);
                  const topicsMessage = topicsError(item.topics, position) ?? errors[`${item.key}:topics`];
                  const imageMessage = errors[`${item.key}:image`];
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
                      <div className="field-row">
                        <label htmlFor={`lesson-topics-${index}`}>Tópicos da cena {position}</label>
                        <span className="hint" id={`lesson-topics-count-${index}`}>
                          {topics.length} / {MAX_TOPICS} tópicos
                        </span>
                      </div>
                      <textarea
                        id={`lesson-topics-${index}`}
                        className="textarea"
                        rows={2}
                        value={item.topics}
                        placeholder="Opcional. Um tópico por linha."
                        aria-invalid={topicsMessage ? true : undefined}
                        aria-describedby={`lesson-topics-count-${index}${topicsMessage ? ` lesson-topics-error-${index}` : ""}`}
                        onChange={(event) => update(index, { topics: event.target.value })}
                      />
                      {topicsMessage && <FieldError id={`lesson-topics-error-${index}`} message={topicsMessage} />}
                      {item.image ? (
                        <div className="lesson-image">
                          <img src={item.image.url} alt={`Imagem da cena ${position}`} />
                          <span>{item.image.name}</span>
                          <button className="btn btn-sm btn-quiet" type="button" aria-label={`Remover imagem da cena ${position}`} onClick={() => change(item.key, { image: null })}>
                            Remover imagem
                          </button>
                        </div>
                      ) : (
                        <label className={imageMessage ? "drop drop-sm is-invalid" : "drop drop-sm"}>
                          <b>{item.uploading ? "Enviando imagem…" : "Adicionar imagem"}</b>
                          <span className="hint" id={`lesson-image-hint-${index}`}>
                            Opcional. JPEG, PNG ou WebP. Ocupa a tela durante a cena, com o apresentador num quadro menor.
                          </span>
                          <input
                            type="file"
                            accept={IMAGE_TYPES.join(",")}
                            aria-label={`Imagem da cena ${position}`}
                            disabled={item.uploading}
                            aria-invalid={imageMessage ? true : undefined}
                            aria-describedby={`lesson-image-hint-${index}${imageMessage ? ` lesson-image-error-${index}` : ""}`}
                            onChange={(event) => {
                              const picked = event.currentTarget.files?.[0];
                              if (picked) void attach(item, position, picked);
                              event.currentTarget.value = "";
                            }}
                          />
                        </label>
                      )}
                      {imageMessage && <FieldError id={`lesson-image-error-${index}`} message={imageMessage} />}
                    </li>
                  );
                })}
              </ol>
              <button className="btn" type="button" disabled={drafts.length >= MAX_SCENES} onClick={() => setDrafts((current) => [...current, draft()])}>
                <Icon name="plus" />
                Adicionar cena
              </button>
            </fieldset>
            <fieldset className="generation-step" disabled={sending}>
              <legend>
                <span>5</span> Trilha
              </legend>
              <label className="check">
                <input
                  type="checkbox"
                  checked={music && hasMusic}
                  disabled={!hasMusic}
                  aria-invalid={errors.music ? true : undefined}
                  aria-describedby={errors.music ? "lesson-music-error" : undefined}
                  onChange={(event) => {
                    setMusic(event.currentTarget.checked);
                    setErrors({});
                  }}
                />
                <span>Tocar a trilha de fundo da identidade, mais baixa enquanto o apresentador fala</span>
              </label>
              {!hasMusic && (
                <p className="note">
                  A identidade não tem trilha de fundo. <Link to="/identidade">Enviar trilha na Identidade</Link>
                </p>
              )}
              {errors.music && <FieldError id="lesson-music-error" message={errors.music} />}
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
                disabled={sending || uploading || !hasIdentity || !avatar || !scene || anyInvalid || limit == null}
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
