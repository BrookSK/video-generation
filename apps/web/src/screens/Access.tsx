import { useEffect, useRef, useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { useOutletContext } from "react-router";

import { ApiError, request, type SessionUser } from "../api";
import { FieldError, Icon, initials } from "../ui";

type PanelUser = SessionUser & { created_at: string; disabled_at: string | null };

type ApiKey = {
  id: string;
  prefix: string;
  description: string;
  created_by_username: string;
  created_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
};

/** Resposta do POST de criação: a única vez em que a chave completa chega ao painel. */
type IssuedApiKey = ApiKey & { key: string };

type UserErrors = { name?: string; email?: string; password?: string; form?: string };
type KeyErrors = { description?: string; form?: string };

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;
const MIN_PASSWORD_LENGTH = 12;
const DATE = new Intl.DateTimeFormat("pt-BR");

const formatDate = (iso: string) => DATE.format(new Date(iso));

function failure(error: unknown): string {
  return error instanceof ApiError ? error.message : "Não foi possível concluir a ação. Tente de novo.";
}

function focusFirstInvalid(form: HTMLFormElement, errors: Record<string, string | undefined>) {
  const name = Object.keys(errors).find((field) => field !== "form" && errors[field]);
  const input = name ? form.elements.namedItem(name) : null;
  if (input instanceof HTMLInputElement) input.focus();
}

function Field({
  id,
  label,
  error,
  hint,
  ...input
}: { id: string; label: string; error?: string | undefined; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(" ");
  return (
    <div className={error ? "field is-invalid" : "field"}>
      <label htmlFor={id}>{label}</label>
      <input
        className="input"
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...input}
      />
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && <FieldError id={`${id}-err`} message={error} />}
    </div>
  );
}

function FormError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return (
    <div role="alert">
      <FieldError id="dlg-err" message={message} />
    </div>
  );
}

/** Diálogo modal nativo: Esc e o fechamento do navegador chegam por onClose. */
function Modal({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
  }, []);
  return (
    <dialog ref={ref} aria-labelledby="dlg-title" onClose={onClose}>
      {children}
    </dialog>
  );
}

function DialogHead({ title, description, onClose }: { title: string; description: string; onClose?: () => void }) {
  return (
    <div className="dlg-head">
      <div>
        <h2 id="dlg-title">{title}</h2>
        <p>{description}</p>
      </div>
      {onClose && (
        <button className="icon-btn" type="button" aria-label="Fechar" onClick={onClose}>
          <Icon name="x" />
        </button>
      )}
    </div>
  );
}

function validateUser(name: string, email: string, password: string): UserErrors {
  const errors: UserErrors = {};
  if (!name) errors.name = "Informe o nome.";
  if (!EMAIL_PATTERN.test(email)) errors.email = "Informe um e-mail válido, como nome@empresa.com.br.";
  if (password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `A senha inicial precisa de pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`;
  }
  return errors;
}

function userServerErrors(error: unknown): UserErrors {
  const message = failure(error);
  const field = error instanceof ApiError ? error.field : null;
  if (field === "display_name") return { name: message };
  if (field === "username") return { email: message };
  if (field === "password") return { password: message };
  return { form: message };
}

function UserDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (user: PanelUser) => void }) {
  const [errors, setErrors] = useState<UserErrors>({});
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const name = String(data.get("name") ?? "").trim();
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    let next = validateUser(name, email, password);
    if (Object.keys(next).length === 0) {
      setBusy(true);
      try {
        onAdded(await request<PanelUser>("POST", "/panel/users", { username: email, display_name: name, password }));
        return;
      } catch (error) {
        next = userServerErrors(error);
        setBusy(false);
      }
    }
    setErrors(next);
    focusFirstInvalid(form, next);
  }

  return (
    <Modal onClose={onClose}>
      <form className="dlg" noValidate onSubmit={submit}>
        <DialogHead
          title="Adicionar pessoa"
          description="A pessoa entra no painel com este e-mail e a senha inicial."
          onClose={onClose}
        />
        <Field id="person-name" name="name" label="Nome" autoComplete="off" error={errors.name} data-autofocus />
        <Field id="person-email" name="email" label="E-mail" type="email" autoComplete="off" error={errors.email} />
        <Field
          id="person-password"
          name="password"
          label="Senha inicial"
          type="password"
          autoComplete="new-password"
          hint="Mínimo de 12 caracteres. Passe a senha por um canal seguro."
          error={errors.password}
        />
        <FormError message={errors.form} />
        <div className="dlg-foot">
          <button className="btn btn-quiet" type="button" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "Adicionando…" : "Adicionar pessoa"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function IssuedKey({ issued, onClose }: { issued: IssuedApiKey; onClose: () => void }) {
  const [copy, setCopy] = useState<"idle" | "copied" | "selected">("idle");
  const secretRef = useRef<HTMLElement>(null);

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(issued.key);
      setCopy("copied");
    } catch {
      // Sem acesso à área de transferência (HTTP sem TLS, permissão negada): seleciona para Ctrl+C.
      const range = document.createRange();
      if (secretRef.current) range.selectNodeContents(secretRef.current);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      setCopy("selected");
    }
  }

  return (
    <div className="dlg">
      <DialogHead
        title="Chave criada"
        description={`Copie agora e guarde no sistema ${issued.description}. Por segurança, ela não aparece de novo.`}
      />
      <div className="secret">
        <code ref={secretRef}>{issued.key}</code>
        <button className="btn" type="button" autoFocus onClick={copyKey}>
          <Icon name={copy === "copied" ? "check" : "copy"} />
          {copy === "copied" ? "Copiada" : "Copiar"}
        </button>
      </div>
      {copy === "selected" && (
        <p className="hint" role="alert">
          Chave selecionada. Use Ctrl+C ou Cmd+C para copiar.
        </p>
      )}
      <div className="note">
        <Icon name="info" />
        <span>
          Envie a chave no cabeçalho <span className="mono">Authorization: Bearer</span> de cada chamada. Nunca coloque
          a chave na URL.
        </span>
      </div>
      <div className="dlg-foot">
        <button className="btn btn-primary" type="button" onClick={onClose}>
          Já guardei a chave
        </button>
      </div>
    </div>
  );
}

// A chave completa vive só no estado deste diálogo: ao fechar, ele desmonta e ela some do painel.
function KeyDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (key: ApiKey) => void }) {
  const [issued, setIssued] = useState<IssuedApiKey | null>(null);
  const [errors, setErrors] = useState<KeyErrors>({});
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const description = String(new FormData(form).get("description") ?? "").trim();
    let next: KeyErrors = description ? {} : { description: "Dê um nome à chave para saber qual sistema a usa." };
    if (description) {
      setBusy(true);
      try {
        const created = await request<IssuedApiKey>("POST", "/panel/api-keys", { description });
        const { key: _key, ...listed } = created;
        onCreated(listed);
        setIssued(created);
        return;
      } catch (error) {
        next = error instanceof ApiError && error.field === "description" ? { description: error.message } : { form: failure(error) };
        setBusy(false);
      }
    }
    setErrors(next);
    focusFirstInvalid(form, next);
  }

  return (
    <Modal onClose={onClose}>
      {issued ? (
        <IssuedKey issued={issued} onClose={onClose} />
      ) : (
        <form className="dlg" noValidate onSubmit={submit}>
          <DialogHead
            title="Criar chave de API"
            description="Dê um nome que identifique o sistema que vai usar esta chave."
            onClose={onClose}
          />
          <Field
            id="key-description"
            name="description"
            label="Nome da chave"
            placeholder="Ex.: Site institucional"
            autoComplete="off"
            error={errors.description}
            data-autofocus
          />
          <FormError message={errors.form} />
          <div className="dlg-foot">
            <button className="btn btn-quiet" type="button" onClick={onClose}>
              Cancelar
            </button>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? "Criando…" : "Criar chave"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function ConfirmInline({
  text,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  text: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
    } catch (failed) {
      setError(failure(failed));
      setBusy(false);
    }
  }

  return (
    <div className="confirm-inline" role="group" aria-label="Confirmação">
      <span>{text}</span>
      <div className="row">
        <button className="btn btn-sm btn-danger-solid" type="button" autoFocus disabled={busy} onClick={confirm}>
          {confirmLabel}
        </button>
        <button className="btn btn-sm btn-quiet" type="button" onClick={onCancel}>
          Cancelar
        </button>
      </div>
      {error && (
        <div role="alert">
          <FieldError id="confirm-err" message={error} />
        </div>
      )}
    </div>
  );
}

function keyDates(key: ApiKey): string {
  const created = `Criada em ${formatDate(key.created_at)} por ${key.created_by_username}.`;
  if (key.revoked_at) return `${created} Revogada em ${formatDate(key.revoked_at)}.`;
  return `${created} ${key.last_used_at ? `Último uso em ${formatDate(key.last_used_at)}.` : "Ainda não usada."}`;
}

export function Access() {
  const me = useOutletContext<SessionUser>();
  const [users, setUsers] = useState<PanelUser[]>([]);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"user" | "key" | null>(null);
  // Um item por vez pede confirmação: "user:<id>" ou "key:<id>".
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([request<PanelUser[]>("GET", "/panel/users"), request<ApiKey[]>("GET", "/panel/api-keys")])
      .then(([loadedUsers, loadedKeys]) => {
        if (!active) return;
        setUsers(loadedUsers.filter((user) => !user.disabled_at));
        setKeys(loadedKeys);
      })
      .catch((error: unknown) => active && setLoadError(failure(error)));
    return () => {
      active = false;
    };
  }, []);

  async function removeUser(user: PanelUser) {
    await request<PanelUser>("POST", `/panel/users/${user.id}/disable`);
    setUsers((current) => current.filter((item) => item.id !== user.id));
    setConfirming(null);
  }

  async function revokeKey(key: ApiKey) {
    const revoked = await request<ApiKey>("POST", `/panel/api-keys/${key.id}/revoke`);
    setKeys((current) => current.map((item) => (item.id === key.id ? revoked : item)));
    setConfirming(null);
  }

  const cancel = () => setConfirming(null);
  const exampleKey = keys.find((key) => !key.revoked_at)?.prefix ?? "avk_";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Usuários e chaves</h1>
          <p>Quem entra no painel e quais sistemas podem pedir vídeos pela API.</p>
        </div>
      </div>
      {loadError && (
        <div role="alert">
          <FieldError id="access-err" message={loadError} />
        </div>
      )}
      <div className="split">
        <section className="panel" aria-labelledby="h-users">
          <div className="panel-head">
            <h2 id="h-users">Pessoas da equipe</h2>
            <button className="btn btn-sm" type="button" onClick={() => setDialog("user")}>
              <Icon name="plus" />
              Adicionar pessoa
            </button>
          </div>
          <p className="hint">
            Todas as pessoas têm o mesmo acesso: gerar vídeos, cadastrar avatares e cenários, gerenciar pessoas e chaves.
          </p>
          <ul className="list" aria-label="Pessoas com acesso">
            {users.map((user) => {
              const isMe = user.id === me.id;
              const isConfirming = confirming === `user:${user.id}`;
              const name = user.display_name || user.username;
              return (
                <li key={user.id} className="list-item">
                  <span className="initials" aria-hidden="true">
                    {initials(user)}
                  </span>
                  <div className="grow">
                    <b>
                      {name}
                      {isMe && (
                        <>
                          {" "}
                          <span className="tag">Você</span>
                        </>
                      )}
                    </b>
                    <span>{user.username}</span>
                    {isConfirming && (
                      <ConfirmInline
                        text={`Remover o acesso de ${name}? A pessoa deixa de entrar no painel. Vídeos pedidos por ela continuam no histórico.`}
                        confirmLabel="Remover acesso"
                        onConfirm={() => removeUser(user)}
                        onCancel={cancel}
                      />
                    )}
                  </div>
                  {!isMe && !isConfirming && (
                    <button
                      className="btn btn-sm btn-quiet"
                      type="button"
                      aria-label={`Remover ${name}`}
                      onClick={() => setConfirming(`user:${user.id}`)}
                    >
                      Remover
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
        <div className="stack">
          <section className="panel" aria-labelledby="h-keys">
            <div className="panel-head">
              <h2 id="h-keys">Chaves de API</h2>
              <button className="btn btn-sm btn-primary" type="button" onClick={() => setDialog("key")}>
                <Icon name="plus" />
                Criar chave
              </button>
            </div>
            <p className="hint">Use uma chave para cada sistema externo. A chave completa aparece uma única vez, na criação.</p>
            <ul className="list" aria-label="Chaves de API">
              {keys.map((key) => {
                const isConfirming = confirming === `key:${key.id}`;
                return (
                  <li key={key.id} className={key.revoked_at ? "list-item is-revoked" : "list-item"}>
                    <div className="grow">
                      <b>{key.description}</b>
                      <span>
                        <span className="key-prefix">{key.prefix}…</span>
                      </span>
                      <span>{keyDates(key)}</span>
                      {isConfirming && (
                        <ConfirmInline
                          text={`Revogar a chave ${key.description}? O sistema que usa esta chave deixa de conseguir pedir e baixar vídeos na próxima chamada. Não dá para desfazer.`}
                          confirmLabel="Revogar chave"
                          onConfirm={() => revokeKey(key)}
                          onCancel={cancel}
                        />
                      )}
                    </div>
                    {key.revoked_at ? (
                      <span className="chip st-archived">Revogada</span>
                    ) : (
                      !isConfirming && (
                        <>
                          <span className="chip st-ready">
                            <span className="dot" />
                            Ativa
                          </span>
                          <button
                            className="btn btn-sm btn-danger"
                            type="button"
                            aria-label={`Revogar ${key.description}`}
                            onClick={() => setConfirming(`key:${key.id}`)}
                          >
                            Revogar
                          </button>
                        </>
                      )
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
          <section className="panel" aria-labelledby="h-example">
            <h2 id="h-example">Como o sistema externo pede um vídeo</h2>
            <pre className="code" tabIndex={0} aria-label="Exemplo de chamada da API">
              <span className="k">POST</span>
              {` /api/v1/jobs
Authorization: Bearer ${exampleKey}…
Idempotency-Key: 7d1e2b90

{
  "script_text": "Oi! Este texto é falado literalmente.",
  "avatar_id": "av_helena",
  "scene_id": "sc_escritorio",
  "aspect_ratio": "9:16"
}

`}
              <span className="c"># Resposta 202: o vídeo entrou na fila</span>
              {`
{ "id": "job_8c21", "status": "queued" }`}
            </pre>
            <p className="hint">
              Depois, o sistema consulta <span className="mono">GET /api/v1/jobs/{"{id}"}</span> e baixa em{" "}
              <span className="mono">/download</span> quando o estado for <span className="mono">ready</span>. O guia
              completo acompanha a instalação.
            </p>
          </section>
        </div>
      </div>
      {dialog === "user" && (
        <UserDialog
          onClose={() => setDialog(null)}
          onAdded={(user) => {
            setUsers((current) => [...current, user]);
            setDialog(null);
          }}
        />
      )}
      {dialog === "key" && (
        <KeyDialog onClose={() => setDialog(null)} onCreated={(key) => setKeys((current) => [key, ...current])} />
      )}
    </div>
  );
}
