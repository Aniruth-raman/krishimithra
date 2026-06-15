import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { api } from "../api/client";
import { ErrorAlert, SuccessAlert } from "../components/Ui";
import { useAuth } from "../context/AuthContext";

export default function ProfilePage() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [userForm, setUserForm] = useState({ full_name: user?.full_name || "", phone: user?.phone || "", preferred_language: user?.preferred_language || "ta" });
  const [profile, setProfile] = useState({ state: "", district: "", land_size_acres: "", primary_crop: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    api.getProfile().then((data) => setProfile((current) => ({ ...current, ...data }))).catch(() => null);
  }, []);

  async function save(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      const updatedUser = await api.updateMe(userForm);
      const updatedProfile = await api.updateProfile({ ...profile, land_size_acres: Number(profile.land_size_acres) || null });
      setUser(updatedUser);
      setProfile(updatedProfile);
      setSuccess("Profile saved.");
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="page mobile-flow-page">
      <header className="page-header simple-header">
        <span className="eyebrow">Profile</span>
        <h2>Your farm information</h2>
      </header>
      <ErrorAlert error={error} />
      <SuccessAlert message={success} />
      <form className="profile-simple-grid" onSubmit={save}>
        <section className="panel">
          <h3>Personal info</h3>
          <label>Name<input value={userForm.full_name} onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })} /></label>
          <label>Phone<input value={userForm.phone || ""} onChange={(event) => setUserForm({ ...userForm, phone: event.target.value })} /></label>
        </section>

        <section className="panel">
          <h3>Farm details</h3>
          <label>State<input value={profile.state || ""} onChange={(event) => setProfile({ ...profile, state: event.target.value })} /></label>
          <label>District<input value={profile.district || ""} onChange={(event) => setProfile({ ...profile, district: event.target.value })} /></label>
          <label>Main crop<input value={profile.primary_crop || ""} onChange={(event) => setProfile({ ...profile, primary_crop: event.target.value })} /></label>
          <label>Farm size<input value={profile.land_size_acres || ""} onChange={(event) => setProfile({ ...profile, land_size_acres: event.target.value })} /></label>
        </section>

        <section className="panel">
          <h3>Language preference</h3>
          <label>Language<select value={userForm.preferred_language} onChange={(event) => setUserForm({ ...userForm, preferred_language: event.target.value })}><option value="ta">Tamil</option><option value="hi">Hindi</option><option value="kn">Kannada</option><option value="en">English</option></select></label>
        </section>

        <div className="profile-actions">
          <button className="primary-button">Save profile</button>
          <button className="secondary-button danger-soft" type="button" onClick={handleLogout}><LogOut size={16} /> Logout</button>
        </div>
      </form>
    </div>
  );
}
