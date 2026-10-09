import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router";

import { logout, onUnauthorized, restoreSession, type SessionUser } from "./api";
import { Access } from "./screens/Access";
import { Avatars } from "./screens/Avatars";
import { History } from "./screens/History";
import { NewVideo } from "./screens/NewVideo";
import { VideoResult } from "./screens/VideoResult";
import { Login } from "./screens/Login";
import { SceneEditor } from "./screens/SceneEditor";
import { Scenes } from "./screens/Scenes";
import { BrandMark, BrandName, Icon, initials, type IconName } from "./ui";

const HOME = "/novo-video";

type NavItem = { to: string; label: string; icon: IconName };

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  { title: "Vídeos", items: [
    { to: "/novo-video", label: "Novo vídeo", icon: "video" },
    { to: "/historico", label: "Histórico", icon: "history" },
  ] },
  {
    title: "Biblioteca",
    items: [
      { to: "/avatares", label: "Avatares", icon: "avatar" },
      { to: "/cenarios", label: "Cenários", icon: "scene" },
    ],
  },
  { title: "Acesso", items: [{ to: "/acesso", label: "Usuários e chaves", icon: "key" }] },
];

function Shell({ user, onSignOut }: { user: SessionUser; onSignOut: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  return (
    <>
      <header className="topbar">
        <button
          className="icon-btn"
          type="button"
          aria-label="Abrir menu"
          aria-expanded={menuOpen}
          aria-controls="side-nav"
          onClick={() => setMenuOpen(true)}
        >
          <Icon name="menu" />
        </button>
        <NavLink className="brand" to={HOME}>
          <BrandMark />
          <BrandName sub={false} />
        </NavLink>
      </header>
      <div className="shell">
        <aside id="side-nav" className={menuOpen ? "side is-open" : "side"} aria-label="Navegação principal">
          <NavLink className="brand" to={HOME}>
            <BrandMark />
            <BrandName />
          </NavLink>
          <nav className="nav">
            {NAV_GROUPS.map((group) => (
              <div key={group.title} className="nav-section">
                <div className="nav-group">{group.title}</div>
                {group.items.map((item) => (
                  <NavLink key={item.to} to={item.to} title={item.label}>
                    <Icon name={item.icon} />
                    <span className="label">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
          <div className="side-foot">
            <span className="initials" aria-hidden="true">
              {initials(user)}
            </span>
            <div className="who">
              <b>{user.display_name || user.username}</b>
              <span>{user.username}</span>
            </div>
            <button className="icon-btn" type="button" aria-label="Sair" title="Sair" onClick={onSignOut}>
              <Icon name="logout" />
            </button>
          </div>
        </aside>
        {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}
        <main className="main" id="main">
          <Outlet context={user} />
        </main>
      </div>
    </>
  );
}

function RequireSession({ user, onSignOut }: { user: SessionUser | null; onSignOut: () => void }) {
  const location = useLocation();
  if (!user) {
    return <Navigate to="/entrar" replace state={{ from: location.pathname }} />;
  }
  return <Shell user={user} onSignOut={onSignOut} />;
}

function SignIn({ user, onSignedIn }: { user: SessionUser | null; onSignedIn: (user: SessionUser) => void }) {
  const location = useLocation();
  if (user) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== "/entrar" ? from : HOME} replace />;
  }
  return <Login onSignedIn={onSignedIn} />;
}

export function App() {
  // undefined: ainda conferindo o cookie; null: sem sessão.
  const [user, setUser] = useState<SessionUser | null | undefined>(undefined);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    restoreSession()
      .then((restored) => active && setUser(restored))
      .catch(() => active && setUser(null));
    const stop = onUnauthorized(() => setUser(null));
    return () => {
      active = false;
      stop();
    };
  }, []);

  async function signOut() {
    try {
      await logout();
    } catch {
      // Sessão já encerrada no servidor ou sem rede: o painel sai do mesmo jeito.
    }
    setUser(null);
    navigate("/entrar", { replace: true });
  }

  if (user === undefined) {
    return <div className="boot" aria-busy="true" />;
  }

  return (
    <Routes>
      <Route path="/entrar" element={<SignIn user={user} onSignedIn={setUser} />} />
      <Route element={<RequireSession user={user} onSignOut={signOut} />}>
        <Route path="/novo-video" element={<NewVideo />} />
        <Route path="/historico" element={<History />} />
        <Route path="/videos/:id" element={<VideoResult />} />
        <Route path="/avatares" element={<Avatars />} />
        <Route path="/cenarios" element={<Scenes />} />
        <Route path="/cenarios/novo" element={<SceneEditor />} />
        <Route path="/acesso" element={<Access />} />
        <Route path="*" element={<Navigate to={HOME} replace />} />
      </Route>
    </Routes>
  );
}
