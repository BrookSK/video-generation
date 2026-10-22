import { useEffect, useRef, useState, type FormEvent } from "react";
import { flushSync } from "react-dom";

import { ApiError, request } from "../api";
import { failure } from "../jobs";
import { HEX_COLOR, type BrandIdentity } from "../lessons";
import { FieldError, Icon } from "../ui";

type Field = "logo" | "background_color" | "accent_color";
type Errors = Partial<Record<Field | "form", string | undefined>>;

const ACCEPTED_TYPES = ["image/png", "image/jpeg"];
const MUSIC_TYPES = ".mp3,.wav,.m4a,.ogg,audio/mpeg,audio/wav,audio/mp4,audio/ogg";
const MAX_MUSIC_BYTES = 20 * 1024 * 1024;
const FIELDS: Field[] = ["logo", "background_color", "accent_color"];
const COLOR_MESSAGE = "Use uma cor no formato #RRGGBB.";
// Cores iniciais só para a prévia antes do primeiro cadastro.
const START = { background_color: "#1B1936", accent_color: "#FFB020" };

function serverErrors(error: unknown): Errors {
  const message = failure(error);
  const field = error instanceof ApiError ? error.field?.replace(/^body\./, "") : undefined;
  return FIELDS.includes(field as Field) ? { [field as Field]: message } : { form: message };
}

function ColorField({
  id,
  label,
  value,
  error,
  disabled,
  onChange,
}: {
  id: Field;
  label: string;
  value: string;
  error: string | undefined;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className={error ? "field is-invalid" : "field"}>
      <label htmlFor={`id-${id}`}>{label}</label>
      <div className="color-field">
        <input
          type="color"
          className="swatch-custom"
          aria-label={`${label}: seletor`}
          value={HEX_COLOR.test(value) ? value.toLowerCase() : "#000000"}
          disabled={disabled}
          onChange={(event) => onChange(event.currentTarget.value.toUpperCase())}
        />
        <input
          className="input mono"
          id={`id-${id}`}
          value={value}
          maxLength={7}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `id-${id}-err` : undefined}
          onChange={(event) => onChange(event.currentTarget.value.trim().toUpperCase())}
        />
      </div>
      {error && <FieldError id={`id-${id}-err`} message={error} />}
    </div>
  );
}

export function Identity() {
  const formRef = useRef<HTMLFormElement>(null);
  const [saved, setSaved] = useState<BrandIdentity>();
  const [loadError, setLoadError] = useState<string>();
  const [background, setBackground] = useState(START.background_color);
  const [accent, setAccent] = useState(START.accent_color);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [musicBusy, setMusicBusy] = useState(false);
  const [musicError, setMusicError] = useState<string>();
  const [musicNotice, setMusicNotice] = useState<string>();

  function apply(identity: BrandIdentity) {
    setSaved(identity);
    setBackground(identity.background_color ?? START.background_color);
    setAccent(identity.accent_color ?? START.accent_color);
  }

  useEffect(() => {
    let active = true;
    request<BrandIdentity>("GET", "/panel/brand-identity")
      .then((identity) => active && apply(identity))
      .catch((failed) => active && setLoadError(failure(failed)));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function showErrors(next: Errors) {
    flushSync(() => setErrors(next));
    formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }

  function pick(picked: File) {
    const accepted = ACCEPTED_TYPES.includes(picked.type);
    setFile(accepted ? picked : null);
    setNotice(undefined);
    setErrors((current) => ({ ...current, logo: accepted ? undefined : "Envie o logo em PNG ou JPEG." }));
  }

  // A trilha tem rota própria: salvar ou remover não mexe no logo nem nas cores em edição.
  async function changeMusic(method: "PUT" | "DELETE", file?: File) {
    if (file && file.size > MAX_MUSIC_BYTES) {
      setMusicError("A trilha passa do limite de 20 MB.");
      return;
    }
    const body = file ? new FormData() : undefined;
    if (file) body!.append("music", file, file.name);
    setMusicBusy(true);
    setMusicError(undefined);
    setMusicNotice(undefined);
    try {
      setSaved(await request<BrandIdentity>(method, "/panel/brand-identity/music", body));
      setMusicNotice(file ? "Trilha salva. Ela vale para as aulas criadas a partir de agora." : "Trilha removida. As próximas aulas saem sem trilha.");
    } catch (failed) {
      setMusicError(failure(failed));
    } finally {
      setMusicBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked.current) return;
    const next: Errors = {};
    if (!file && !saved?.logo_url) next.logo = "Envie o logo em PNG ou JPEG.";
    if (!HEX_COLOR.test(background)) next.background_color = COLOR_MESSAGE;
    if (!HEX_COLOR.test(accent)) next.accent_color = COLOR_MESSAGE;
    if (Object.values(next).some(Boolean)) {
      showErrors(next);
      return;
    }

    const body = new FormData();
    body.append("background_color", background);
    body.append("accent_color", accent);
    if (file) body.append("logo", file, file.name);
    locked.current = true;
    setBusy(true);
    setNotice(undefined);
    try {
      apply(await request<BrandIdentity>("PUT", "/panel/brand-identity", body));
      setFile(null);
      setErrors({});
      setNotice("Identidade salva. Ela vale para as aulas criadas a partir de agora.");
    } catch (failed) {
      const found = serverErrors(failed);
      if (found.logo) setFile(null);
      // Libera os campos antes de levar o foco ao primeiro erro.
      setBusy(false);
      showErrors(found);
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  const logo = preview ?? saved?.logo_url ?? null;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Identidade</h1>
          <p>Logo e cores da abertura e do encerramento de todas as aulas. A troca vale para as aulas criadas depois.</p>
        </div>
      </div>
      {loadError ? (
        <div role="alert">
          <FieldError id="identity-load-error" message={loadError} />
        </div>
      ) : !saved ? (
        <p role="status">Carregando identidade…</p>
      ) : (
        <div className="editor">
          <form ref={formRef} className="panel" noValidate onSubmit={submit}>
            {!saved.logo_url && (
              <p className="note">
                <Icon name="info" />
                <span>Nenhuma identidade cadastrada. Envie o logo e escolha as cores para liberar a geração de aulas.</span>
              </p>
            )}
            <div className={errors.logo ? "field is-invalid" : "field"}>
              <span className="field-label" id="id-logo-label">
                Logo
              </span>
              <label className={errors.logo ? "drop is-invalid" : "drop"}>
                <Icon name="plus" />
                <b>{file ? file.name : saved.logo_url ? "Trocar o logo" : "Escolha o logo"}</b>
                <span className="hint" id="id-logo-hint">
                  PNG ou JPEG. De preferência com fundo transparente.
                </span>
                <input
                  type="file"
                  name="logo"
                  accept={ACCEPTED_TYPES.join(",")}
                  aria-label="Logo"
                  disabled={busy}
                  aria-invalid={errors.logo ? true : undefined}
                  aria-describedby={errors.logo ? "id-logo-hint id-logo-err" : "id-logo-hint"}
                  onChange={(event) => {
                    const picked = event.currentTarget.files?.[0];
                    if (picked) pick(picked);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              {errors.logo && <FieldError id="id-logo-err" message={errors.logo} />}
            </div>
            <ColorField
              id="background_color"
              label="Cor de fundo"
              value={background}
              error={errors.background_color}
              disabled={busy}
              onChange={(value) => {
                setBackground(value);
                setErrors((current) => ({ ...current, background_color: undefined }));
              }}
            />
            <ColorField
              id="accent_color"
              label="Cor de destaque"
              value={accent}
              error={errors.accent_color}
              disabled={busy}
              onChange={(value) => {
                setAccent(value);
                setErrors((current) => ({ ...current, accent_color: undefined }));
              }}
            />
            <div className={musicError ? "field music-field is-invalid" : "field music-field"}>
              <span className="field-label">Trilha de fundo</span>
              {saved.music_url && (
                <div className="field-row">
                  <audio controls preload="none" src={saved.music_url} aria-label="Trilha de fundo atual" />
                  <button className="btn btn-sm btn-quiet" type="button" disabled={musicBusy} onClick={() => void changeMusic("DELETE")}>
                    Remover trilha
                  </button>
                </div>
              )}
              <label className={musicError ? "drop drop-sm is-invalid" : "drop drop-sm"}>
                <b>{musicBusy ? "Enviando trilha…" : saved.music_url ? "Trocar a trilha" : "Escolha a trilha"}</b>
                <span className="hint" id="id-music-hint">
                  {saved.logo_url
                    ? "Opcional. MP3, WAV, M4A ou OGG, até 20 MB. Toca baixa na aula e abaixa mais quando há fala."
                    : "Salve o logo e as cores antes de enviar a trilha."}
                </span>
                <input
                  type="file"
                  name="music"
                  accept={MUSIC_TYPES}
                  aria-label="Trilha de fundo"
                  disabled={musicBusy || !saved.logo_url}
                  aria-invalid={musicError ? true : undefined}
                  aria-describedby={musicError ? "id-music-hint id-music-err" : "id-music-hint"}
                  onChange={(event) => {
                    const picked = event.currentTarget.files?.[0];
                    if (picked) void changeMusic("PUT", picked);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              {musicError && <FieldError id="id-music-err" message={musicError} />}
              {musicNotice && (
                <p className="note" role="status">
                  {musicNotice}
                </p>
              )}
            </div>
            {errors.form && (
              <div role="alert">
                <FieldError id="id-form-err" message={errors.form} />
              </div>
            )}
            {notice && (
              <p className="note" role="status">
                {notice}
              </p>
            )}
            <div className="dlg-foot spread">
              {saved.updated_at && (
                <span className="hint">
                  Última mudança: {saved.updated_by}, {new Date(saved.updated_at).toLocaleString("pt-BR")}
                </span>
              )}
              <button className="btn btn-primary" type="submit" disabled={busy}>
                {busy ? "Salvando…" : "Salvar identidade"}
              </button>
            </div>
          </form>
          <section className="stage" aria-label="Prévia da abertura">
            <div className="stage-bar">
              <span>Prévia da abertura e do encerramento</span>
            </div>
            <div className="brand-card" style={{ background: HEX_COLOR.test(background) ? background : undefined }}>
              {logo ? <img src={logo} alt="Logo" /> : <span className="brand-card-empty">Seu logo aqui</span>}
              <i style={{ background: HEX_COLOR.test(accent) ? accent : undefined }} />
            </div>
            <p className="stage-hint">3 s no começo e no fim de cada aula. O logo nunca é ampliado.</p>
          </section>
        </div>
      )}
    </div>
  );
}
