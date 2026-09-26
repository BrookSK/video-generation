import { useEffect, useState } from "react";

import { ApiError, request } from "../api";
import { FieldError, Icon } from "../ui";
import { AvatarDialog, type Avatar } from "./AvatarDialog";

const POLL_MS = 3000;
const NOTICE_MS = 4200;
const DATE = new Intl.DateTimeFormat("pt-BR");

const CHIPS: Record<Avatar["status"], { label: string; className: string }> = {
  preparando: { label: "Preparando", className: "chip st-processing" },
  ativo: { label: "Ativo", className: "chip st-ready" },
  falha: { label: "Falha", className: "chip st-failed" },
  arquivado: { label: "Arquivado", className: "chip st-archived" },
};

function failure(error: unknown): string {
  return error instanceof ApiError ? error.message : "Não foi possível concluir a ação. Tente de novo.";
}

// Antes da preparação terminar só existe o arquivo enviado; depois, a prévia 9:16 recortada.
function artUrl(avatar: Avatar): string {
  const kind = avatar.status === "preparando" || avatar.status === "falha" ? "source" : "preview-9x16";
  return `/panel/avatars/${avatar.id}/files/${kind}`;
}

function ArchiveConfirm({ avatar, onArchived, onCancel }: { avatar: Avatar; onArchived: (avatar: Avatar) => void; onCancel: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function confirm() {
    setBusy(true);
    try {
      onArchived(await request<Avatar>("POST", `/panel/avatars/${avatar.id}/archive`));
    } catch (failed) {
      setError(failure(failed));
      setBusy(false);
    }
  }

  return (
    <div className="confirm-inline" role="group" aria-label="Confirmação">
      <span>
        Arquivar {avatar.name}? Vídeos já gerados continuam disponíveis. O avatar sai da lista de novos vídeos e da API.
      </span>
      <div className="row">
        <button className="btn btn-sm btn-danger-solid" type="button" autoFocus disabled={busy} onClick={confirm}>
          Arquivar
        </button>
        <button className="btn btn-sm btn-quiet" type="button" onClick={onCancel}>
          Cancelar
        </button>
      </div>
      {error && (
        <div role="alert">
          <FieldError id={`archive-err-${avatar.id}`} message={error} />
        </div>
      )}
    </div>
  );
}

function AvatarCard({
  avatar,
  confirming,
  onAskArchive,
  onCancelArchive,
  onArchived,
  onRetry,
}: {
  avatar: Avatar;
  confirming: boolean;
  onAskArchive: () => void;
  onCancelArchive: () => void;
  onArchived: (avatar: Avatar) => void;
  onRetry: () => void;
}) {
  const chip = CHIPS[avatar.status];
  let foot = null;
  if (confirming) {
    foot = <ArchiveConfirm avatar={avatar} onArchived={onArchived} onCancel={onCancelArchive} />;
  } else if (avatar.status === "falha") {
    foot = (
      <div className="asset-foot">
        <button className="btn btn-sm" type="button" onClick={onRetry}>
          Enviar outra imagem
        </button>
      </div>
    );
  } else if (avatar.status !== "arquivado") {
    foot = (
      <div className="asset-foot">
        <button
          className="btn btn-sm btn-quiet"
          type="button"
          aria-label={`Arquivar ${avatar.name}`}
          disabled={avatar.status !== "ativo"}
          onClick={onAskArchive}
        >
          Arquivar
        </button>
      </div>
    );
  }

  return (
    <article className={avatar.status === "arquivado" ? "asset is-archived" : "asset"} aria-label={avatar.name}>
      <div className="asset-art">
        <img src={artUrl(avatar)} alt="" />
        {avatar.status === "preparando" && (
          <div className="scan">
            <span>Recortando o fundo</span>
          </div>
        )}
        {avatar.status === "falha" && (
          <div className="fail-ov">
            <Icon name="error" />
            <span>{avatar.prepare_error ?? "Não foi possível preparar a imagem. Envie outra foto."}</span>
          </div>
        )}
      </div>
      <div className="asset-body">
        <div className="asset-title">
          <h3>{avatar.name}</h3>
          <span className={chip.className}>
            {avatar.status !== "arquivado" && <span className="dot" />}
            {chip.label}
          </span>
        </div>
        <div className="asset-tags">
          <span className="tag">Voz {avatar.voice}</span>
          <span className="tag">Cadastrado em {DATE.format(new Date(avatar.created_at))}</span>
        </div>
        {foot}
      </div>
    </article>
  );
}

export function Avatars() {
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [reload, setReload] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    request<Avatar[]>("GET", showArchived ? "/panel/avatars?include_archived=true" : "/panel/avatars")
      .then((loaded) => {
        if (!active) return;
        setAvatars(loaded);
        setLoadError(null);
      })
      .catch((error: unknown) => active && setLoadError(failure(error)));
    return () => {
      active = false;
    };
  }, [showArchived, reload]);

  // Polling só enquanto algum avatar está em preparação.
  const preparing = avatars.some((avatar) => avatar.status === "preparando");
  useEffect(() => {
    if (!preparing) return;
    const timer = setInterval(() => setReload((count) => count + 1), POLL_MS);
    return () => clearInterval(timer);
  }, [preparing]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  function archived(avatar: Avatar) {
    setAvatars((current) =>
      showArchived ? current.map((item) => (item.id === avatar.id ? avatar : item)) : current.filter((item) => item.id !== avatar.id),
    );
    setConfirming(null);
    setNotice(`Avatar ${avatar.name} arquivado.`);
  }

  function created(avatar: Avatar) {
    setAvatars((current) => [...current, avatar]);
    setDialogOpen(false);
    setNotice(`Avatar ${avatar.name} enviado. O recorte do fundo leva alguns segundos.`);
  }

  const activeCount = avatars.filter((avatar) => avatar.status === "ativo").length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Avatares</h1>
          <p>Pessoas que falam nos vídeos. Cada avatar vem de uma foto autorizada e tem uma voz, masculina ou feminina.</p>
        </div>
        <button className="btn btn-primary" type="button" onClick={() => setDialogOpen(true)}>
          <Icon name="plus" />
          Cadastrar avatar
        </button>
      </div>
      <div className="toolbar">
        <span className="hint">{activeCount} ativos. Não há limite de cadastro.</span>
        <label className="check">
          <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.currentTarget.checked)} />
          <span>Mostrar arquivados</span>
        </label>
      </div>
      {loadError && (
        <div role="alert">
          <FieldError id="avatars-err" message={loadError} />
        </div>
      )}
      <div className="asset-grid">
        {avatars.map((avatar) => (
          <AvatarCard
            key={avatar.id}
            avatar={avatar}
            confirming={confirming === avatar.id}
            onAskArchive={() => setConfirming(avatar.id)}
            onCancelArchive={() => setConfirming(null)}
            onArchived={archived}
            onRetry={() => setDialogOpen(true)}
          />
        ))}
      </div>
      <div className="toasts" role="status" aria-live="polite">
        {notice && (
          <div className="toast ok">
            <Icon name="check" />
            <span>{notice}</span>
          </div>
        )}
      </div>
      {dialogOpen && <AvatarDialog onClose={() => setDialogOpen(false)} onCreated={created} />}
    </div>
  );
}
