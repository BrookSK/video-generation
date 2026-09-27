import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { ApiError, request } from "../api";
import { FieldError, Icon } from "../ui";
import type { Composition } from "./SceneEditor";

export type Scene = {
  id: string;
  name: string;
  background_color: string | null;
  composition: Composition;
  status: "ativo" | "arquivado";
  created_at: string;
  archived_at: string | null;
};

const NOTICE_MS = 4200;
const DATE = new Intl.DateTimeFormat("pt-BR");

function failure(error: unknown): string {
  return error instanceof ApiError ? error.message : "Não foi possível concluir a ação. Tente de novo.";
}

const previewUrl = (scene: Scene, kind: "preview-9x16" | "preview-16x9") => `/panel/scenes/${scene.id}/files/${kind}`;

function ArchiveConfirm({ scene, onArchived, onCancel }: { scene: Scene; onArchived: (scene: Scene) => void; onCancel: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function confirm() {
    setBusy(true);
    try {
      onArchived(await request<Scene>("POST", `/panel/scenes/${scene.id}/archive`));
    } catch (failed) {
      setError(failure(failed));
      setBusy(false);
    }
  }

  return (
    <div className="confirm-inline" role="group" aria-label="Confirmação">
      <span>
        Arquivar {scene.name}? Vídeos já gerados continuam disponíveis. O cenário sai da lista de novos vídeos e da API.
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
          <FieldError id={`archive-err-${scene.id}`} message={error} />
        </div>
      )}
    </div>
  );
}

function SceneCard({
  scene,
  confirming,
  onAskArchive,
  onCancelArchive,
  onArchived,
}: {
  scene: Scene;
  confirming: boolean;
  onAskArchive: () => void;
  onCancelArchive: () => void;
  onArchived: (scene: Scene) => void;
}) {
  const archived = scene.status === "arquivado";
  let foot = null;
  if (confirming) {
    foot = <ArchiveConfirm scene={scene} onArchived={onArchived} onCancel={onCancelArchive} />;
  } else if (!archived) {
    foot = (
      <div className="asset-foot">
        <button className="btn btn-sm btn-quiet" type="button" aria-label={`Arquivar ${scene.name}`} onClick={onAskArchive}>
          Arquivar
        </button>
      </div>
    );
  }

  return (
    <article className={archived ? "asset is-archived" : "asset"} aria-label={scene.name}>
      <div className="asset-art">
        <img src={previewUrl(scene, "preview-16x9")} alt="" />
        <div className="mini-frames">
          <img className="v" src={previewUrl(scene, "preview-9x16")} alt="Prévia 9:16" />
          <img className="h" src={previewUrl(scene, "preview-16x9")} alt="Prévia 16:9" />
        </div>
      </div>
      <div className="asset-body">
        <div className="asset-title">
          <h3>{scene.name}</h3>
          {archived ? (
            <span className="chip st-archived">Arquivado</span>
          ) : (
            <span className="chip st-ready">
              <span className="dot" />
              Ativo
            </span>
          )}
        </div>
        <div className="asset-tags">
          <span className="tag">{scene.background_color ? `Cor sólida ${scene.background_color}` : "Imagem"}</span>
          <span className="tag">Cadastrado em {DATE.format(new Date(scene.created_at))}</span>
        </div>
        {foot}
      </div>
    </article>
  );
}

export function Scenes() {
  const location = useLocation();
  const navigate = useNavigate();
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  // O editor volta para cá com o aviso do cenário criado.
  const [notice, setNotice] = useState<string | null>((location.state as { notice?: string } | null)?.notice ?? null);

  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null });
  }, [location, navigate]);

  useEffect(() => {
    let active = true;
    request<Scene[]>("GET", showArchived ? "/panel/scenes?include_archived=true" : "/panel/scenes")
      .then((loaded) => {
        if (!active) return;
        setScenes(loaded);
        setLoadError(null);
      })
      .catch((error: unknown) => active && setLoadError(failure(error)));
    return () => {
      active = false;
    };
  }, [showArchived]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  function archived(scene: Scene) {
    setScenes((current) =>
      showArchived ? current.map((item) => (item.id === scene.id ? scene : item)) : current.filter((item) => item.id !== scene.id),
    );
    setConfirming(null);
    setNotice(`Cenário ${scene.name} arquivado.`);
  }

  const activeCount = scenes.filter((scene) => scene.status === "ativo").length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Cenários</h1>
          <p>O fundo atrás do avatar. Cada cenário guarda o tamanho e a posição da pessoa em 9:16 e em 16:9.</p>
        </div>
        <Link className="btn btn-primary" to="/cenarios/novo">
          <Icon name="plus" />
          Criar cenário
        </Link>
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
          <FieldError id="scenes-err" message={loadError} />
        </div>
      )}
      <div className="asset-grid scenes">
        {scenes.map((scene) => (
          <SceneCard
            key={scene.id}
            scene={scene}
            confirming={confirming === scene.id}
            onAskArchive={() => setConfirming(scene.id)}
            onCancelArchive={() => setConfirming(null)}
            onArchived={archived}
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
    </div>
  );
}
