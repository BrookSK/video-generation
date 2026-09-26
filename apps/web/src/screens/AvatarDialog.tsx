import { Fragment, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { flushSync } from "react-dom";

import { ApiError, request } from "../api";
import { FieldError, Icon } from "../ui";

export type Voice = "feminina" | "masculina";

export type Avatar = {
  id: string;
  name: string;
  voice: Voice;
  status: "preparando" | "ativo" | "falha" | "arquivado";
  prepare_error: string | null;
  authorized_at: string | null;
  created_at: string;
  archived_at: string | null;
};

type Field = "file" | "name" | "voice" | "authorization";
type Errors = Partial<Record<Field | "form", string | undefined>>;

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 20 * 1024 * 1024;
const MB = 1024 * 1024;
const VOICES: { value: Voice; label: string }[] = [
  { value: "feminina", label: "Feminina" },
  { value: "masculina", label: "Masculina" },
];
const FIELDS: Field[] = ["file", "name", "voice", "authorization"];

/** Confere tipo e tamanho no navegador; a assinatura real é conferida pela API. */
function fileError(file: File): string | undefined {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return "Formato não aceito. Envie JPEG, PNG ou WebP. SVG, PDF e arquivos compactados são recusados.";
  }
  if (file.size > MAX_BYTES) {
    return `A imagem tem ${Math.round(file.size / MB)} MB e o limite é 20 MB. Envie um arquivo menor.`;
  }
  return undefined;
}

/** Erro do servidor no campo indicado por field; validação do FastAPI chega como body.<campo>. */
function serverErrors(error: unknown): Errors {
  const message = error instanceof ApiError ? error.message : "Não foi possível cadastrar o avatar. Tente de novo.";
  const field = error instanceof ApiError ? error.field?.replace(/^body\./, "") : undefined;
  return FIELDS.includes(field as Field) ? { [field as Field]: message } : { form: message };
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 16V4M7 8.5l5-5 5 5M5 20h14" />
    </svg>
  );
}

function ImagePicker({
  file,
  error,
  onPick,
  onClear,
}: {
  file: File | null;
  error: string | undefined;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const [over, setOver] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) onPick(dropped);
  }

  if (file) {
    return (
      <div className="field">
        <span className="field-label">Imagem</span>
        <div className="drop-preview">
          <div className="ph">{preview && <img src={preview} alt="Prévia da imagem enviada" />}</div>
          <div className="drop-file">
            <b>{file.name}</b>
            <span className="hint">Imagem aceita. O recorte acontece depois de salvar.</span>
            <button className="btn btn-sm btn-quiet" type="button" onClick={onClear}>
              Trocar imagem
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="field">
      <span className="field-label" id="lbl-drop">
        Imagem
      </span>
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
        <b>Arraste a foto ou clique para escolher</b>
        <span className="hint" id="av-file-hint">
          JPEG, PNG ou WebP até 20 MB. Foto de frente, com rosto e ombros visíveis e boa luz.
        </span>
        <input
          type="file"
          name="file"
          accept={ACCEPTED_TYPES.join(",")}
          aria-labelledby="lbl-drop"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "av-file-hint av-file-err" : "av-file-hint"}
          onChange={(event) => {
            const picked = event.currentTarget.files?.[0];
            if (picked) onPick(picked);
            event.currentTarget.value = "";
          }}
        />
      </label>
      {error && <FieldError id="av-file-err" message={error} />}
    </div>
  );
}

export function AvatarDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (avatar: Avatar) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [voice, setVoice] = useState<Voice | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  // Depois de cada tentativa, o foco vai para o primeiro campo com erro.
  function showErrors(next: Errors) {
    flushSync(() => setErrors(next));
    ref.current?.querySelector<HTMLElement>('[aria-invalid="true"] input, input[aria-invalid="true"]')?.focus();
  }

  function pick(picked: File) {
    const error = fileError(picked);
    setFile(error ? null : picked);
    setErrors((current) => ({ ...current, file: error }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    const authorized = data.get("authorization") === "on";
    const next: Errors = {};
    if (!file) next.file = "Envie a foto do avatar.";
    if (!name) next.name = "Dê um nome ao avatar.";
    if (!voice) next.voice = "Escolha a voz do avatar.";
    if (!authorized) next.authorization = "Confirme a autorização de uso da imagem para continuar.";
    if (!file || !name || !voice || !authorized) {
      showErrors(next);
      return;
    }

    const body = new FormData();
    body.append("file", file, file.name);
    body.append("name", name);
    body.append("voice", voice);
    body.append("authorization_confirmed", "true");
    setBusy(true);
    try {
      onCreated(await request<Avatar>("POST", "/panel/avatars", body));
    } catch (error) {
      const failed = serverErrors(error);
      // Imagem recusada pela API volta para a área de upload, com o motivo junto ao campo.
      if (failed.file) setFile(null);
      setBusy(false);
      showErrors(failed);
    }
  }

  return (
    <dialog ref={ref} aria-labelledby="dlg-title" onClose={onClose}>
      <form className="dlg" noValidate onSubmit={submit}>
        <div className="dlg-head">
          <div>
            <h2 id="dlg-title">Cadastrar avatar</h2>
            <p>O fundo da foto é removido automaticamente. Leva alguns segundos.</p>
          </div>
          <button className="icon-btn" type="button" aria-label="Fechar" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <ImagePicker file={file} error={errors.file} onPick={pick} onClear={() => setFile(null)} />
        <div className={errors.name ? "field is-invalid" : "field"}>
          <label htmlFor="av-name">Nome do avatar</label>
          <input
            className="input"
            id="av-name"
            name="name"
            placeholder="Ex.: Marina"
            autoComplete="off"
            maxLength={80}
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? "av-name-err" : undefined}
          />
          {errors.name && <FieldError id="av-name-err" message={errors.name} />}
        </div>
        <div className="field">
          <span className="field-label" id="lbl-voice">
            Voz
          </span>
          <div
            className="seg"
            role="radiogroup"
            aria-labelledby="lbl-voice"
            aria-invalid={errors.voice ? true : undefined}
            aria-describedby={errors.voice ? "av-voice-err" : undefined}
          >
            {VOICES.map((option) => (
              <Fragment key={option.value}>
                <input
                  type="radio"
                  id={`av-voice-${option.value}`}
                  name="voice"
                  value={option.value}
                  checked={voice === option.value}
                  onChange={() => {
                    setVoice(option.value);
                    setErrors((current) => ({ ...current, voice: undefined }));
                  }}
                />
                <label htmlFor={`av-voice-${option.value}`}>{option.label}</label>
              </Fragment>
            ))}
          </div>
          {errors.voice && <FieldError id="av-voice-err" message={errors.voice} />}
        </div>
        <div className={errors.authorization ? "field is-invalid" : "field"}>
          <label className="check">
            <input
              type="checkbox"
              name="authorization"
              aria-invalid={errors.authorization ? true : undefined}
              aria-describedby={errors.authorization ? "av-auth-err" : undefined}
            />
            <span>
              Confirmo que temos autorização para usar a imagem desta pessoa como avatar. A confirmação fica registrada
              com meu nome e a data.
            </span>
          </label>
          {errors.authorization && <FieldError id="av-auth-err" message={errors.authorization} />}
        </div>
        {errors.form && (
          <div role="alert">
            <FieldError id="av-form-err" message={errors.form} />
          </div>
        )}
        <div className="dlg-foot">
          <button className="btn btn-quiet" type="button" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "Enviando…" : "Cadastrar avatar"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
