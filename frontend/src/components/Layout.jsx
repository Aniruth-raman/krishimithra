import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BarChart3, Bot, Home, LogOut, Radio, Shield, UserCog } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const farmerLinks = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/assistant", label: "AI Assistant", icon: Bot },
  { to: "/live", label: "Live Mode", icon: Radio },
  { to: "/profile", label: "Profile", icon: UserCog },
];

const officerLinks = [
  { to: "/officer", label: "Officer Dashboard", icon: BarChart3 },
];

const adminLinks = [
  { to: "/admin", label: "Admin Console", icon: Shield },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const links = user?.role === "admin" ? adminLinks : user?.role === "officer" ? officerLinks : farmerLinks;

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">KM</div>
          <div>
            <h1>KrishiMitra</h1>
            <p>Farmer assistant</p>
          </div>
        </div>

        <nav className="nav-list">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-card">
            <UserCog size={18} />
            <div>
              <strong>{user?.full_name}</strong>
              <span>{user?.role}</span>
            </div>
          </div>
          <button className="ghost-button" onClick={handleLogout}>
            <LogOut size={16} /> Logout
          </button>
        </div>
      </aside>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
