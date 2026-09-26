import { useRef, useState, type FormEvent } from "react";

import { ApiError, login, type SessionUser } from "../api";
import { BrandMark, BrandName, FieldError, Icon } from "../ui";

type Errors = { email?: string; password?: string; form?: string };

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;
const WAVE_BARS = 56;

function validate(email: string, password: string): Errors {
  const errors: Errors = {};
  if (!email) errors.email = "Informe o e-mail.";
  else if (!EMAIL_PATTERN.test(email)) errors.email = "Confira o e-mail: falta algo como nome@empresa.com.br.";
  if (!password) errors.password = "Informe a senha.";
  return errors;
}

function serverErrors(error: unknown): Errors {
  if (!(error instanceof ApiError)) {
    return { form: "Não foi possível entrar agora. Tente de novo em instantes." };
  }
  if (error.code === "INVALID_CREDENTIALS") {
    return { password: "E-mail ou senha incorretos. Confira e tente de novo." };
  }
  if (error.field === "username") return { email: error.message };
  if (error.field === "password") return { password: error.message };
  return { form: error.message };
}

// Onda estática do palco: a fala animada fica para o player (DS-005).
function Wave() {
  return (
    <svg className="wave" viewBox={`0 0 ${WAVE_BARS * 6} 44`} preserveAspectRatio="none" aria-hidden="true">
      {Array.from({ length: WAVE_BARS }, (_, i) => {
        const on = i > WAVE_BARS - 14;
        const height = on ? 8 + ((i * 7) % 28) : 4;
        return <rect key={i} className={on ? "on" : undefined} x={i * 6 + 1.5} y={22 - height / 2} width="3" height={height} rx="1.5" />;
      })}
    </svg>
  );
}

export function Login({ onSignedIn }: { onSignedIn: (user: SessionUser) => void }) {
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  function focusFirstInvalid(next: Errors) {
    if (next.email) emailRef.current?.focus();
    else if (next.password) passwordRef.current?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    const invalid = validate(email, password);
    setErrors(invalid);
    if (invalid.email || invalid.password) {
      focusFirstInvalid(invalid);
      return;
    }
    setBusy(true);
    try {
      onSignedIn(await login(email, password));
    } catch (error) {
      const next = serverErrors(error);
      setErrors(next);
      setBusy(false);
      focusFirstInvalid(next);
    }
  }

  return (
    <div className="login">
      <section className="stage login-stage" aria-label="Demonstração: texto vira vídeo">
        <div className="stage-bar">
          <span className="brand">
            <BrandMark />
            <BrandName />
          </span>
          <span className="tally">
            <i />
            <b>Gerando na sua GPU</b>
          </span>
        </div>
        <div className="stage-view">
          <div className="stage-grid" />
          <div className="frame">
            <div className="finder" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </div>
            <div className="comp" />
          </div>
        </div>
        <Wave />
        <div className="login-caption">
          <h2>Do texto ao vídeo com avatar, no seu próprio servidor.</h2>
          <div className="pipeline">
            <span className="on">Texto</span>
            <Icon name="chev" />
            <span>Voz</span>
            <Icon name="chev" />
            <span>Avatar</span>
            <Icon name="chev" />
            <span>MP4 9:16 ou 16:9</span>
          </div>
        </div>
      </section>
      <div className="login-form-wrap">
        <form className="login-form" noValidate onSubmit={submit} aria-label="Entrar no Estúdio">
          <h1>Entrar no Estúdio</h1>
          <p>Use o e-mail e a senha que a sua equipe cadastrou.</p>
          <div className={errors.email ? "field is-invalid" : "field"}>
            <label htmlFor="email">E-mail</label>
            <input
              ref={emailRef}
              className="input"
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              aria-invalid={errors.email ? true : undefined}
              aria-describedby={errors.email ? "email-err" : undefined}
            />
            {errors.email && <FieldError id="email-err" message={errors.email} />}
          </div>
          <div className={errors.password ? "field is-invalid" : "field"}>
            <label htmlFor="password">Senha</label>
            <div className="pw">
              <input
                ref={passwordRef}
                className="input"
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                aria-invalid={errors.password ? true : undefined}
                aria-describedby={errors.password ? "password-err" : undefined}
              />
              <button
                className="icon-btn"
                type="button"
                aria-label={showPassword ? "Esconder senha" : "Mostrar senha"}
                aria-pressed={showPassword}
                onClick={() => setShowPassword((shown) => !shown)}
              >
                <Icon name={showPassword ? "eyeOff" : "eye"} />
              </button>
            </div>
            {errors.password && <FieldError id="password-err" message={errors.password} />}
          </div>
          <button className="btn btn-primary btn-lg" type="submit" disabled={busy}>
            {busy ? "Entrando…" : "Entrar"}
          </button>
          {errors.form && (
            <div role="alert">
              <FieldError id="form-err" message={errors.form} />
            </div>
          )}
          <p className="hint">Sem acesso? Peça a alguém da equipe para cadastrar você em Usuários e chaves.</p>
        </form>
      </div>
    </div>
  );
}
