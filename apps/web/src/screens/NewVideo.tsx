import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { ApiError, request } from "../api";
import { failure, type AspectRatio, type GenerationConfig, type JobCreated, type VideoInput } from "../jobs";
import { FieldError } from "../ui";
import type { Avatar } from "./AvatarDialog";
import type { Scene } from "./Scenes";

export function NewVideo() {
  const navigate = useNavigate();
  const location = useLocation();
  const copied = (location.state as { redo?: VideoInput } | null)?.redo;
  const [text, setText] = useState(copied?.script_text ?? "");
  const [avatarId, setAvatarId] = useState(copied?.avatar_id ?? "");
  const [sceneId, setSceneId] = useState(copied?.scene_id ?? "");
  const [format, setFormat] = useState<AspectRatio>(copied?.aspect_ratio ?? "9:16");
  const [catalog, setCatalog] = useState<{ avatars: Avatar[]; scenes: Scene[]; config: GenerationConfig }>();
  const [loadError, setLoadError] = useState<string>();
  const [error, setError] = useState<{ message: string; field?: string | undefined }>();
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
    ]).then(([avatars, scenes, config]) => {
      if (active) setCatalog({ avatars, scenes, config });
    }).catch((failed) => { if (active) setLoadError(failure(failed)); });
    return () => { active = false; };
  }, []);

  const avatar = catalog?.avatars.find((a) => a.id === avatarId && a.status === "ativo");
  const scene = catalog?.scenes.find((s) => s.id === sceneId && s.status === "ativo");
  const count = Array.from(text).length;
  const limit = catalog?.config.max_script_chars;
  const tooLong = limit != null && count > limit;
  const rate = catalog?.config.chars_per_second;
  const seconds = rate != null && rate > 0 && Number.isFinite(rate) ? Math.ceil(count / rate) : null;
  const framing = scene?.composition[format];
  const textError = tooLong ? `O limite vigente é ${limit} caracteres. Encurte a fala.` : error?.field === "script_text" ? error.message : undefined;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked.current) return;
    setError(undefined);
    if (!text.trim()) { setError({ field: "script_text", message: "Escreva o texto da fala." }); return; }
    if (tooLong || !avatar || !scene || limit == null) return;
    locked.current = true;
    setSending(true);
    const payload: VideoInput = { script_text: text, avatar_id: avatar.id, scene_id: scene.id, aspect_ratio: format };
    const fingerprint = JSON.stringify(payload);
    if (intent.current?.fingerprint !== fingerprint) intent.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const created = await request<JobCreated>("POST", "/panel/jobs", payload, { idempotencyKey: intent.current.key });
      navigate(`/videos/${created.id}`, { state: { notice: "Vídeo na fila." } });
    } catch (failed) {
      setError({ message: failure(failed), field: failed instanceof ApiError ? failed.field?.replace(/^body\./, "") : undefined });
    } finally {
      locked.current = false;
      setSending(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head"><div><h1>Novo vídeo</h1><p>Escreva a fala, escolha quem fala e onde. Baixe o vídeo pronto para postar.</p></div></header>
      {copied && <p className="note" role="status">Dados copiados. Confira as escolhas e clique em Gerar vídeo. Assets arquivados precisam ser substituídos.</p>}
      {loadError ? <div role="alert"><FieldError id="catalog-error" message={loadError} /><button className="btn" onClick={() => window.location.reload()}>Carregar novamente</button></div> : !catalog ? <p role="status">Carregando avatares, cenários e limites…</p> : (
        <form className="generation" onSubmit={submit}>
          <div className="generation-fields">
            <section className="generation-step" aria-labelledby="speech-title">
              <h2 id="speech-title"><span>1</span> Texto da fala</h2>
              <div className="field">
                <label className="sr-only" htmlFor="speech">Texto da fala</label>
                <textarea id="speech" className="textarea" value={text} disabled={sending} onChange={(event) => { setText(event.target.value); setError(undefined); }} aria-invalid={textError ? true : undefined} aria-describedby={`speech-hint speech-count${textError ? " speech-error" : ""}`} />
                <p id="speech-hint" className="hint">O texto será falado literalmente. Não escreva instruções de cena.</p>
                <div className="field-row hint" id="speech-count"><span>{count}{limit == null ? " caracteres" : ` / ${limit} caracteres`}</span><span>{seconds == null ? "Estimativa indisponível" : `≈ ${seconds} s de fala (estimativa)`}</span></div>
                {catalog.config.max_audio_seconds != null && <p className="hint">Áudio final limitado a {catalog.config.max_audio_seconds} s; a duração real é verificada após a voz.</p>}
                {textError && <FieldError id="speech-error" message={textError} />}
              </div>
            </section>
            <fieldset className="generation-step" disabled={sending}>
              <legend><span>2</span> Avatar</legend>
              <div className="picks" role="radiogroup" aria-label="Avatar">
                {catalog.avatars.filter((a) => a.status !== "arquivado" && a.status !== "falha").map((a) => (
                  <label className="pick" key={a.id}>
                    <input type="radio" name="avatar" value={a.id} checked={avatar?.id === a.id} disabled={a.status !== "ativo"} onChange={() => setAvatarId(a.id)} />
                    <img src={`/panel/avatars/${a.id}/files/${a.status === "ativo" ? "prepared" : "original"}`} alt="" />
                    <span><b>{a.name}</b><small>{a.status === "ativo" ? `Voz ${a.voice}` : "Preparando recorte"}</small></span>
                  </label>
                ))}
              </div>
              {!catalog.avatars.some((a) => a.status === "ativo") && <p className="note">Nenhum avatar ativo. <Link to="/avatares">Cadastre um avatar</Link> e aguarde a preparação.</p>}
            </fieldset>
            <fieldset className="generation-step" disabled={sending}>
              <legend><span>3</span> Cenário</legend>
              <div className="picks" role="radiogroup" aria-label="Cenário">
                {catalog.scenes.filter((s) => s.status === "ativo").map((s) => (
                  <label className="pick pick-scene" key={s.id}>
                    <input type="radio" name="scene" value={s.id} checked={scene?.id === s.id} onChange={() => setSceneId(s.id)} />
                    <img src={`/panel/scenes/${s.id}/files/preview-16x9`} alt="" /><span><b>{s.name}</b><small>{s.background_color ? "Cor sólida" : "Imagem de fundo"}</small></span>
                  </label>
                ))}
              </div>
              {!catalog.scenes.some((s) => s.status === "ativo") && <p className="note">Nenhum cenário ativo. <Link to="/cenarios/novo">Crie um cenário</Link> antes de gerar.</p>}
            </fieldset>
            <fieldset className="generation-step" disabled={sending}>
              <legend><span>4</span> Formato</legend>
              <div className="seg" role="radiogroup" aria-label="Formato">
                {(["9:16", "16:9"] as const).map((ratio) => <Fragment key={ratio}><input id={`ratio-${ratio}`} name="format" type="radio" checked={format === ratio} onChange={() => setFormat(ratio)} /><label htmlFor={`ratio-${ratio}`}><i className={ratio === "9:16" ? "ratio-ico v" : "ratio-ico h"} />{ratio}</label></Fragment>)}
              </div>
            </fieldset>
            {limit == null && <p role="status" className="note">Geração indisponível: nenhuma receita vigente. A configuração será liberada após a calibração do gerador.</p>}
            {error && error.field !== "script_text" && <div role="alert"><FieldError id="generation-error" message={error.message} /></div>}
            <div className="generation-action"><button className="btn btn-primary btn-lg" disabled={sending || !avatar || !scene || tooLong || limit == null} type="submit"><span className="generate-tally" />{sending ? "Enviando…" : "Gerar vídeo"}</button><p className="hint">A geração continua mesmo se você fechar esta tela.</p></div>
          </div>
          <section className="stage scene-stage generation-stage" aria-label="Prévia da composição">
            <div className="stage-bar"><span>Prévia da composição</span><span className="tally"><i /><b>{format}</b></span></div>
            <div className="stage-view">
              <div className="stage-grid" />
              <div className={format === "9:16" ? "frame v" : "frame h"} data-format={format}>
                <div className="finder" aria-hidden="true"><span /><span /><span /><span /></div>
                <div className="comp">
                  {scene ? <div className="comp-bg" style={scene.background_color ? { background: scene.background_color } : undefined}>{!scene.background_color && <img src={`/panel/scenes/${scene.id}/files/background`} alt="" />}</div> : <div className="composition-empty">Escolha um cenário e um avatar</div>}
                  {avatar && framing && <img className="comp-av" src={`/panel/avatars/${avatar.id}/files/prepared`} alt={avatar.name} style={{ height: `${framing.scale * 100}%`, left: `${framing.x * 100}%`, bottom: `${(1 - framing.y) * 100}%` }} />}
                </div>
              </div>
            </div>
            <div className="stage-meta">{avatar && <span className="tag">{avatar.name} · {avatar.voice}</span>}{scene && <span className="tag">{scene.name}</span>}</div>
            <p className="stage-hint">Prévia estática do enquadramento salvo. Voz e animação só no vídeo gerado.</p>
          </section>
        </form>
      )}
    </div>
  );
}
