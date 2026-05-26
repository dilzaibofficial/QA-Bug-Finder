import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  FaTachometerAlt,
  FaUpload,
  FaBug,
  FaHistory,
  FaCog,
  FaSignOutAlt,
  FaBars,
  FaTimes
} from "react-icons/fa";
import "./sidebar.css";

function Sidebar({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const isDashboard =
    location.pathname === "/dashboard" ||
    location.pathname === "/tlu" ||
    location.pathname === "/bd" ||
    location.pathname === "/cb" ||
    location.pathname === "/bss";

  const getTitle = () => {
    switch (location.pathname) {
      case "/dashboard": return "Dashboard";
      case "/upload":    return "Upload Logs";
      case "/reports":   return "Bug Reports";
      case "/history":   return "History";
      case "/settings":  return "Settings";
      case "/tlu":       return "Total Logs Uploaded";
      case "/bd":        return "Bugs Detected";
      case "/cb":        return "Critical Bugs";
      case "/bss":       return "Bug Status Summary";
      default:           return "Dashboard";
    }
  };

  const handleNav = (path) => {
    navigate(path);
    setSidebarOpen(false);
  };

  return (
    <div className="layout">

      {/* OVERLAY */}
      <div
        className={`sidebar-overlay ${sidebarOpen ? "open" : ""}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* SIDEBAR */}
      <div className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <h2 className="logo">⚡ Bug Detector</h2>

        <div className={`menu-item ${isDashboard ? "active" : ""}`}
          onClick={() => handleNav("/dashboard")}
        >
          <FaTachometerAlt /> Dashboard
        </div>

        <div className={`menu-item ${location.pathname === "/upload" ? "active" : ""}`}
          onClick={() => handleNav("/upload")}
        >
          <FaUpload /> Upload Logs
        </div>

        <div className={`menu-item ${location.pathname === "/reports" ? "active" : ""}`}
          onClick={() => handleNav("/reports")}
        >
          <FaBug /> Bug Reports
        </div>

        <div className={`menu-item ${location.pathname === "/history" ? "active" : ""}`}
          onClick={() => handleNav("/history")}
        >
          <FaHistory /> History
        </div>

        <div className={`menu-item ${location.pathname === "/settings" ? "active" : ""}`}
          onClick={() => handleNav("/settings")}
        >
          <FaCog /> Settings
        </div>

        <div className="menu-item logout"
          onClick={() => { navigate("/", { replace: true }); setSidebarOpen(false); }}
        >
          <FaSignOutAlt /> Logout
        </div>
      </div>

      {/* RIGHT SIDE */}
      <div className="main-area">

        {/* TOPBAR */}
        <div className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <button
              className="hamburger-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label="Toggle menu"
            >
              {sidebarOpen ? <FaTimes /> : <FaBars />}
            </button>
            <div className="topbar-title">{getTitle()}</div>
          </div>
          <div className="topbar-user">Welcome 👋</div>
        </div>

        {/* CONTENT */}
        <div className="content">
          {children}
        </div>

      </div>

    </div>
  );
}

export default Sidebar;
