import { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import { getProfile, updateProfile, updatePassword, getClaudeMode, setClaudeMode } from "../api";
import "./setting.css";

function Settings() {
  const userId = localStorage.getItem("user_id") || "";

  const [name, setName]   = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole]   = useState("QA Engineer");

  const [curPass, setCurPass]     = useState("");
  const [newPass, setNewPass]     = useState("");
  const [confirmPass, setConfirm] = useState("");

  const [profileMsg, setProfileMsg] = useState("");
  const [passMsg, setPassMsg]       = useState("");
  const [profileOk, setProfileOk]   = useState(true);
  const [passOk, setPassOk]         = useState(true);

  const [claudeMode, setClaudeModeState] = useState(false);
  const [claudeMsg, setClaudeMsg]        = useState("");
  const [claudeSaving, setClaudeSaving]  = useState(false);

  useEffect(() => {
    if (!userId) return;
    getProfile(userId).then((res) => {
      if (!res.error) {
        setName(res.name || "");
        setEmail(res.email || "");
        setRole(res.role || "QA Engineer");
      }
    });
    getClaudeMode(userId).then((res) => {
      setClaudeModeState(res.claude_mode || false);
      localStorage.setItem("claude_mode", res.claude_mode ? "true" : "false");
    });
  }, [userId]);

  const saveProfile = async () => {
    const res = await updateProfile(userId, { name, email, role });
    setProfileOk(!res.error);
    setProfileMsg(res.error || res.message || "Profile updated");
    setTimeout(() => setProfileMsg(""), 3000);
  };

  const savePassword = async () => {
    if (newPass !== confirmPass) {
      setPassOk(false);
      setPassMsg("New passwords do not match");
      return;
    }
    if (newPass.length < 6) {
      setPassOk(false);
      setPassMsg("Password must be at least 6 characters");
      return;
    }
    const res = await updatePassword(userId, curPass, newPass);
    setPassOk(!res.error);
    setPassMsg(res.error || res.message || "Password updated");
    if (!res.error) { setCurPass(""); setNewPass(""); setConfirm(""); }
    setTimeout(() => setPassMsg(""), 3000);
  };

  const toggleClaude = async (val) => {
    setClaudeSaving(true);
    setClaudeModeState(val);
    localStorage.setItem("claude_mode", val ? "true" : "false");
    const res = await setClaudeMode(userId, val);
    setClaudeSaving(false);
    setClaudeMsg(res.error || (val ? "Claude AI mode enabled — next upload will use Claude for enhanced analysis." : "Switched to Simple ML mode."));
    setTimeout(() => setClaudeMsg(""), 4000);
  };

  return (
    <Sidebar>
      <div className="settings-container">
        <h2 className="settings-title">Settings</h2>

        <div className="settings-tabs">
          <span className="active-tab">Profile</span>
          <span>All Preferences</span>
          <span>File Settings</span>
          <span>Notifications</span>
          <span>Referrals</span>
        </div>

        <div className="settings-content">

          {/* Left — Profile Info */}
          <div className="card1">
            <h3>Profile Information</h3>

            <label>Full Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />

            <label>Email Address</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="example@email.com" />

            <label>Role</label>
            <input type="text" value={role} onChange={(e) => setRole(e.target.value)} placeholder="QA Engineer" />

            {profileMsg && (
              <p style={{ color: profileOk ? "#16a34a" : "#dc2626", fontSize: "14px" }}>{profileMsg}</p>
            )}

            <button className="btn" onClick={saveProfile}>Save Changes</button>
          </div>

          {/* Right — Change Password */}
          <div className="card2">
            <h3>Change Password</h3>

            <label>Current Password</label>
            <input type="password" value={curPass} onChange={(e) => setCurPass(e.target.value)} placeholder="Enter current password" />

            <label>New Password</label>
            <input type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} placeholder="Enter new password" />

            <label>Confirm Password</label>
            <input type="password" value={confirmPass} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirm password" />

            {passMsg && (
              <p style={{ color: passOk ? "#16a34a" : "#dc2626", fontSize: "14px" }}>{passMsg}</p>
            )}

            <button className="btn" onClick={savePassword}>Update Password</button>
          </div>

        </div>

        {/* Claude AI Mode Toggle — full width card */}
        <div style={{
          marginTop: "24px",
          background: "#fff",
          borderRadius: "14px",
          padding: "24px 28px",
          boxShadow: "0 2px 12px rgba(0,0,0,0.07)",
          border: claudeMode ? "2px solid #7c3aed" : "2px solid #e5e7eb",
          transition: "border 0.3s",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>

            {/* Left info */}
            <div style={{ flex: 1, minWidth: "260px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                <span style={{ fontSize: "22px" }}>🤖</span>
                <h3 style={{ margin: 0, fontSize: "17px", color: "#1e293b" }}>Claude AI Enhanced Analysis</h3>
                {claudeMode && (
                  <span style={{
                    background: "#7c3aed", color: "#fff", fontSize: "11px",
                    padding: "2px 8px", borderRadius: "20px", fontWeight: "600"
                  }}>ACTIVE</span>
                )}
              </div>
              <p style={{ color: "#64748b", fontSize: "13px", margin: "0 0 12px 0", lineHeight: "1.6" }}>
                When <b>ON</b> — each detected bug is sent to <b>Claude AI</b> for deep analysis:
                enhanced explanations, specific root-cause reasoning, and <b>actual corrected code</b> for every bug.
                <br />
                When <b>OFF</b> — uses the built-in ML model only (fast, no API calls).
              </p>

              <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
                <div style={{ fontSize: "12px", color: "#64748b" }}>
                  <b style={{ color: "#1e293b" }}>Simple Mode (OFF)</b><br />
                  • ML ensemble model<br />
                  • Fast (~3s per file)<br />
                  • No external API
                </div>
                <div style={{ fontSize: "12px", color: "#64748b" }}>
                  <b style={{ color: "#7c3aed" }}>Claude AI Mode (ON)</b><br />
                  • ML model + Claude API<br />
                  • Slower (~10-30s per bug)<br />
                  • Richer, code-level fixes
                </div>
              </div>

              {claudeMsg && (
                <p style={{
                  marginTop: "12px", fontSize: "13px", padding: "8px 12px", borderRadius: "6px",
                  background: claudeMode ? "#f3e8ff" : "#f1f5f9",
                  color: claudeMode ? "#7c3aed" : "#64748b",
                  border: `1px solid ${claudeMode ? "#ddd6fe" : "#e2e8f0"}`
                }}>{claudeMsg}</p>
              )}
            </div>

            {/* Right toggle */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", paddingTop: "4px" }}>
              <div
                onClick={() => !claudeSaving && toggleClaude(!claudeMode)}
                style={{
                  width: "64px", height: "34px", borderRadius: "34px", cursor: claudeSaving ? "wait" : "pointer",
                  background: claudeMode ? "#7c3aed" : "#d1d5db",
                  position: "relative", transition: "background 0.3s",
                  boxShadow: claudeMode ? "0 0 12px rgba(124,58,237,0.4)" : "none"
                }}
              >
                <div style={{
                  position: "absolute", top: "4px",
                  left: claudeMode ? "34px" : "4px",
                  width: "26px", height: "26px", borderRadius: "50%",
                  background: "#fff", boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                  transition: "left 0.3s",
                }} />
              </div>
              <span style={{ fontSize: "12px", fontWeight: "600", color: claudeMode ? "#7c3aed" : "#94a3b8" }}>
                {claudeSaving ? "Saving..." : claudeMode ? "Claude ON" : "Simple"}
              </span>
            </div>

          </div>
        </div>

      </div>
    </Sidebar>
  );
}

export default Settings;
