import { useNavigate, useLocation } from "react-router-dom";
import {
  FaTachometerAlt,
  FaUpload,
  FaBug,
  FaHistory,
  FaCog,
  FaSignOutAlt
} from "react-icons/fa";
import "./sidebar.css";

function Sidebar({ children }) {
  const navigate = useNavigate();
  const location = useLocation();

  /* ✅ ADD THIS */
  const isDashboard =
    location.pathname === "/dashboard" ||
    location.pathname === "/tlu" ||
    location.pathname === "/bd" ||
    location.pathname === "/cb"||
    location.pathname === "/bss";

  const getTitle = () => {
    switch (location.pathname) {
      case "/dashboard":
        return "Dashboard";
      case "/upload":
        return "Upload Logs";
      case "/reports":
        return "Bug Reports";
      case "/history":
        return "History";
      case "/settings":
        return "Settings";
      case "/tlu":
        return "Total Logs Uploaded";
      case "/bd":
        return "Bugs Detected";
      case "/cb":
        return "Critical Bugs";
        case "/bss":
        return "Bug Status Summary";
      default:
        return "Dashboard";
    }
  };

  return (
    <div className="layout">

      {/* SIDEBAR */}
      <div className="sidebar">
        <h2 className="logo">⚡ Bug Detector</h2>

        {/* ✅ UPDATED HERE */}
        <div className={`menu-item ${isDashboard ? "active" : ""}`}
          onClick={() => navigate("/dashboard")}
        >
          <FaTachometerAlt /> Dashboard
        </div>

        <div className={`menu-item ${location.pathname === "/upload" ? "active" : ""}`}
          onClick={() => navigate("/upload")}
        >
          <FaUpload /> Upload Logs
        </div>

        <div className={`menu-item ${location.pathname === "/reports" ? "active" : ""}`}
          onClick={() => navigate("/reports")}
        >
          <FaBug /> Bug Reports
        </div>

        <div className={`menu-item ${location.pathname === "/history" ? "active" : ""}`}
          onClick={() => navigate("/history")}
        >
          <FaHistory /> History
        </div>

        <div className={`menu-item ${location.pathname === "/settings" ? "active" : ""}`}
          onClick={() => navigate("/settings")}
        >
          <FaCog /> Settings
        </div>

        <div className="menu-item logout"
          onClick={() => navigate("/", { replace: true })}
        >
          <FaSignOutAlt /> Logout
        </div>
      </div>

      {/* RIGHT SIDE */}
      <div className="main-area">

        {/* TOPBAR */}
        <div className="topbar">
          <div className="topbar-title">{getTitle()}</div>
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