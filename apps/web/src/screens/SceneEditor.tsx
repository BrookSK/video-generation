import { Fragment, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { flushSync } from "react-dom";
import { Link, useNavigate } from "react-router";

import { ApiError, request } from "../api";
import { FieldError, Icon } from "../ui";
import type { Avatar } from "./AvatarDialog";

type AspectRatio = "9:16" | "16:9";
type Framing = { scale: number; x: number; y: number };
export type Composition = Record<AspectRatio, Framing>;

type BackgroundKind = "image" | "color";
type Field = "name" | "file" | "background_color" | "composition";
type Errors = Partial<Record<Field | "form", string | undefined>>;

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 20 * 1024 * 1024;
const MB = 1024 * 1024;
const FIELDS: Field[] = ["name", "file", "background_color", "composition"];
const RATIOS: AspectRatio[] = ["9:16", "16:9"];
const SWATCHES = ["#CFE0D6", "#DDE3EC", "#F1E4D3", "#E9D7E4", "#2A2752", "#FFFFFF"];
const NUMBER = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Faixas e geometria de canvas.compose_canvas: scale é a altura do avatar sobre a altura do
// canvas, x o centro horizontal e y a base, em frações do canvas.
const SLIDERS: { key: keyof Framing; label: string; min: number; max: number }[] = [
  { key: "scale", label: "Escala", min: 0.3, max: 1.2 },
  { key: "x", label: "Posição horizontal", min: 0, max: 1 },
  { key: "y", label: "Base", min: 0.5, max: 1.2 },
];

// Enquadramentos padrão do devseed: centro e base, 0,8 em 9:16 e 0,9 em 16:9.
const DEFAULT_COMPOSITION: Composition = {
  "9:16": { scale: 0.8, x: 0.5, y: 1 },
  "16:9": { scale: 0.9, x: 0.5, y: 1 },
};

/** Mesma checagem do cadastro de avatar: tipo e tamanho no navegador; a assinatura real é da API. */
function fileError(file: File): string | undefined {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return "Formato não aceito. Envie JPEG, PNG ou WebP. SVG, PDF e arquivos compactados são recusados.";
  }
  if (file.size > MAX_BYTES) {
    return `A imagem tem ${Math.round(file.size / MB)} MB e o limite é 20 MB. Envie um arquivo menor.`;
  }
  return undefined;
}

/** Erro do servidor no campo indicado por field; "background" vai para o controle do fundo ativo. */
function serverErrors(error: unknown, kind: BackgroundKind): Errors {
  const message = error instanceof ApiError ? error.message : "Não foi possível salvar o cenário. Tente de novo.";
  let field = error instanceof ApiError ? error.field?.replace(/^body\./, "") : undefined;
  if (field === "background") field = kind === "image" ? "file" : "background_color";
  return FIELDS.includes(field as Field) ? { [field as Field]: message } : { form: message };
}

const percent = (fraction: number) => `${+(fraction * 100).toFixed(2)}%`;

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 16V4M7 8.5l5-5 5 5M5 20h14" />
    </svg>
  );
}

function BackgroundPicker({
  file,
  preview,
  error,
  onPick,
  onClear,
}: {
  file: File | null;
  preview: string | null;
  error: string | undefined;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const [over, setOver] = useState(false);

  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) onPick(dropped);
  }

  if (file) {
    return (
      <div className="drop-preview">
        <div className="ph ph-wide">{preview && <img src={preview} alt="Prévia do fundo enviado" />}</div>
        <div className="drop-file">
          <b>{file.name}</b>
          <span className="hint">Imagem aceita.</span>
          <button className="btn btn-sm btn-quiet" type="button" onClick={onClear}>
            Trocar imagem
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <label
        className={["drop", over && "is-over", error && "is-invalid"].filter(Boolean).join(" ")}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
      >
        <UploadIcon />
        <b>Arraste a imagem de fundo ou clique</b>
        <span className="hint" id="sc-file-hint">
          JPEG, PNG ou WebP até 20 MB. De preferência horizontal e sem pessoas.
        </span>
        <input
          type="file"
          name="file"
          accept={ACCEPTED_TYPES.join(",")}
          aria-label="Imagem de fundo"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "sc-file-hint sc-file-err" : "sc-file-hint"}
          onChange={(event) => {
            const picked = event.currentTarget.files?.[0];
            if (picked) onPick(picked);
            event.currentTarget.value = "";
          }}
        />
      </label>
      {error && <FieldError id="sc-file-err" message={error} />}
    </>
  );
}

function Silhouette() {
  return (
    <svg viewBox="0 0 400 480" aria-hidden="true">
      <circle cx="200" cy="170" r="92" />
      <path d="M40 480c14-120 80-190 160-190s146 70 160 190z" />
    </svg>
  );
}

function Stage({
  name,
  kind,
  color,
  background,
  sample,
  format,
  framing,
}: {
  name: string;
  kind: BackgroundKind;
  color: string;
  background: string | null;
  sample: Avatar | null;
  format: AspectRatio;
  framing: Framing;
}) {
  // Geometria de compose_canvas: altura = scale x altura do visor, centro em x, base em y.
  const place = { height: percent(framing.scale), left: percent(framing.x), bottom: percent(1 - framing.y) };
  let fill = <div className="comp-bg" style={{ background: color }} />;
  if (kind === "image") {
    fill = background ? (
      <div className="comp-bg">
        <img src={background} alt="" />
      </div>
    ) : (
      <div className="comp-bg bg-empty">
        <Icon name="scene" />
        <span>Escolha uma imagem de fundo</span>
      </div>
    );
  }

  return (
    <section className="stage scene-stage" aria-label="Prévia do cenário">
      <div className="stage-bar">
        <span>Prévia do cenário</span>
        <span className="tally">
          <i />
          <b>{format}</b>
        </span>
      </div>
      <div className="stage-view">
        <div className="stage-grid" />
        <div className={format === "9:16" ? "frame v" : "frame h"} data-format={format}>
          <div className="finder" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div className="comp">
            {fill}
            {sample ? (
              <img className="comp-av" src={`/panel/avatars/${sample.id}/files/prepared`} alt={`Avatar de amostra: ${sample.name}`} style={place} />
            ) : (
              <span className="comp-av comp-silhouette" style={place}>
                <Silhouette />
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="stage-meta">
        <span className="tag">{sample ? sample.name : "Silhueta de amostra"}</span>
        <span className="tag">{name.trim() || "Cenário novo"}</span>
      </div>
    </section>
  );
}

export function SceneEditor() {
  const navigate = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BackgroundKind>("image");
  const [color, setColor] = useState("#DDE3EC");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [format, setFormat] = useState<AspectRatio>("9:16");
  const [composition, setComposition] = useState<Composition>(DEFAULT_COMPOSITION);
  const [sample, setSample] = useState<Avatar | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  // Avatar de amostra: o recorte do primeiro avatar ativo; sem ele, uma silhueta.
  useEffect(() => {
    let active = true;
    request<Avatar[]>("GET", "/panel/avatars")
      .then((avatars) => active && setSample(avatars.find((avatar) => avatar.status === "ativo") ?? null))
      .catch(() => undefined);
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

  // Depois de cada tentativa, o foco vai para o primeiro campo com erro.
  function showErrors(next: Errors) {
    flushSync(() => setErrors(next));
    formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }

  function pick(picked: File) {
    const error = fileError(picked);
    setFile(error ? null : picked);
    setErrors((current) => ({ ...current, file: error }));
  }

  function adjust(key: keyof Framing, value: number) {
    setComposition((current) => ({ ...current, [format]: { ...current[format], [key]: value } }));
    setErrors((current) => ({ ...current, composition: undefined }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    const next: Errors = {};
    if (!trimmed) next.name = "Dê um nome ao cenário.";
    if (kind === "image" && !file) next.file = "Escolha a imagem de fundo ou mude para cor sólida.";
    if (next.name || next.file) {
      showErrors(next);
      return;
    }

    const body = new FormData();
    body.append("name", trimmed);
    if (kind === "image" && file) body.append("file", file, file.name);
    else body.append("background_color", color);
    body.append("composition", JSON.stringify(composition));
    setBusy(true);
    try {
      const created = await request<{ name: string }>("POST", "/panel/scenes", body);
      navigate("/cenarios", { state: { notice: `Cenário ${created.name} criado. Ele já aparece em Novo vídeo e na API.` } });
    } catch (error) {
      const failed = serverErrors(error, kind);
      // Imagem recusada pela API volta para a área de upload, com o motivo junto ao campo.
      if (failed.file) setFile(null);
      setBusy(false);
      showErrors(failed);
    }
  }

  const framing = composition[format];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link className="back" to="/cenarios">
            <Icon name="chev" />
            Cenários
          </Link>
          <h1>Criar cenário</h1>
          <p>Escolha o fundo e ajuste onde a pessoa aparece em cada formato. A prévia mostra exatamente o que vai para o vídeo.</p>
        </div>
      </div>
      <div className="editor">
        <form ref={formRef} className="panel" noValidate onSubmit={submit}>
          <div className={errors.name ? "field is-invalid" : "field"}>
            <label htmlFor="sc-name">Nome do cenário</label>
            <input
              className="input"
              id="sc-name"
              value={name}
              placeholder="Ex.: Loja, balcão de atendimento"
              autoComplete="off"
              maxLength={80}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? "sc-name-err" : undefined}
              onChange={(event) => setName(event.currentTarget.value)}
            />
            {errors.name && <FieldError id="sc-name-err" message={errors.name} />}
          </div>

          <div className="panel-section">
            <span className="field-label" id="lbl-bg">
              Fundo
            </span>
            <div className="seg" role="radiogroup" aria-labelledby="lbl-bg">
              {(["image", "color"] as const).map((option) => (
                <Fragment key={option}>
                  <input
                    type="radio"
                    id={`bg-${option}`}
                    name="bgkind"
                    checked={kind === option}
                    onChange={() => setKind(option)}
                  />
                  <label htmlFor={`bg-${option}`}>{option === "image" ? "Imagem" : "Cor sólida"}</label>
                </Fragment>
              ))}
            </div>
            {kind === "image" ? (
              <BackgroundPicker file={file} preview={preview} error={errors.file} onPick={pick} onClear={() => setFile(null)} />
            ) : (
              <div className="field">
                <div className="swatches" role="group" aria-label="Cores prontas">
                  {SWATCHES.map((swatch) => (
                    <button
                      key={swatch}
                      type="button"
                      className="swatch"
                      style={{ background: swatch }}
                      aria-label={`Cor ${swatch}`}
                      aria-pressed={color.toLowerCase() === swatch.toLowerCase()}
                      onClick={() => setColor(swatch)}
                    />
                  ))}
                  <input
                    type="color"
                    className="swatch-custom"
                    value={color.toLowerCase()}
                    aria-label="Outra cor"
                    aria-invalid={errors.background_color ? true : undefined}
                    aria-describedby={errors.background_color ? "sc-color-err" : undefined}
                    onChange={(event) => {
                      setColor(event.currentTarget.value.toUpperCase());
                      setErrors((current) => ({ ...current, background_color: undefined }));
                    }}
                  />
                  <span className="mono">{color}</span>
                </div>
                {errors.background_color && <FieldError id="sc-color-err" message={errors.background_color} />}
              </div>
            )}
          </div>

          <section
            className="panel-section"
            aria-labelledby="lbl-fr"
            aria-describedby={errors.composition ? "sc-comp-err" : undefined}
          >
            <div className="field-row">
              <span className="field-label" id="lbl-fr">
                Enquadramento
              </span>
              <div className="seg" role="radiogroup" aria-label="Formato">
                {RATIOS.map((ratio) => (
                  <Fragment key={ratio}>
                    <input
                      type="radio"
                      id={`sf-${ratio}`}
                      name="scfmt"
                      checked={format === ratio}
                      onChange={() => setFormat(ratio)}
                    />
                    <label htmlFor={`sf-${ratio}`}>
                      <span className={ratio === "9:16" ? "ratio-ico v" : "ratio-ico h"} />
                      {ratio}
                    </label>
                  </Fragment>
                ))}
              </div>
            </div>
            <p className="hint">Ajuste os dois formatos. O vídeo nunca corta nem estica a pessoa.</p>
            {SLIDERS.map((slider) => {
              const id = `fr-${slider.key}`;
              return (
                <div key={slider.key} className="slider">
                  <div className="field-row">
                    <label htmlFor={id}>{slider.label}</label>
                    <output htmlFor={id}>{NUMBER.format(framing[slider.key])}</output>
                  </div>
                  <input
                    type="range"
                    id={id}
                    min={slider.min}
                    max={slider.max}
                    step={0.01}
                    value={framing[slider.key]}
                    onChange={(event) => adjust(slider.key, Number(event.currentTarget.value))}
                  />
                </div>
              );
            })}
            {errors.composition && <FieldError id="sc-comp-err" message={errors.composition} />}
          </section>

          <div className="panel-section">
            <div className="note">
              <Icon name="info" />
              <span>
                Depois de salvo, o cenário não muda. Para trocar o fundo ou o enquadramento, arquive e crie outro. Vídeos
                antigos ficam como estão.
              </span>
            </div>
            {errors.form && (
              <div role="alert">
                <FieldError id="sc-form-err" message={errors.form} />
              </div>
            )}
            <div className="dlg-foot">
              <Link className="btn btn-quiet" to="/cenarios">
                Cancelar
              </Link>
              <button className="btn btn-primary" type="submit" disabled={busy}>
                {busy ? "Salvando…" : "Salvar cenário"}
              </button>
            </div>
          </div>
        </form>
        <Stage name={name} kind={kind} color={color} background={preview} sample={sample} format={format} framing={framing} />
      </div>
    </div>
  );
}
