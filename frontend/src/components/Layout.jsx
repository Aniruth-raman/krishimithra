import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BarChart3, Bot, FileText, Home, Leaf, LogOut, Mic, PhoneCall, Shield, UserCog, Users } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";

const farmerLinks = [
  { to: "/assistant", label: "AI Assistant", icon: Bot },
  { to: "/voice-live", label: "Voice Assistant", icon: Mic },
];

const farmerDesktopLinks = farmerLinks;

const officerLinks = [
  { to: "/officer", label: "Dashboard", icon: Home },
  { to: "/officer/grievances", label: "Grievances", icon: Shield },
  { to: "/officer/diseases", label: "Disease Reports", icon: Leaf },
  { to: "/officer/analytics", label: "Analytics", icon: BarChart3 },
];

const adminLinks = [
  { to: "/admin", label: "Dashboard", icon: Home },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/schemes", label: "Schemes", icon: FileText },
  { to: "/admin/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/admin/ivr-simulator", label: "IVR", icon: PhoneCall },
  { to: "/admin/settings", label: "Settings", icon: UserCog },
];

function NavItems({ links }) {
  return links.map(({ to, label, icon: Icon }) => (
    <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
      <Icon size={20} />
      <span>{label}</span>
    </NavLink>
  ));
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const desktopLinks = user?.role === "admin" ? adminLinks : user?.role === "officer" ? officerLinks : farmerDesktopLinks;
  const bottomLinks = user?.role === "farmer" ? farmerLinks : desktopLinks.slice(0, 5);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="app-shell farmer-companion-shell">
      <aside className="sidebar simple-sidebar">
        <div className="brand">
          <div className="brand-mark">KM</div>
          <div>
            <h1>KrishiMitra</h1>
            <p>AI farming companion</p>
          </div>
        </div>

        <nav className="nav-list desktop-nav">
          <NavItems links={desktopLinks} />
        </nav>

        <div className="sidebar-footer">
          <button className="theme-toggle" type="button" onClick={toggleTheme}>
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
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

      <nav className="bottom-nav" aria-label="Primary navigation">
        <NavItems links={bottomLinks} />
      </nav>
    </div>
  );
}
