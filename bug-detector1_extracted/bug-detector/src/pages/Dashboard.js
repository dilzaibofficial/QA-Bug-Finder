import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import { FaUpload, FaBug } from "react-icons/fa";
import { getDashboardStats } from "../api";
import "./dashboard.css";

function Dashboard() {
  const navigate = useNavigate();
  const [showSteps, setShowSteps] = useState(true);
  const [stats, setStats] = useState({
    total_uploads: 0,
    total_bugs: 0,
    critical_bugs: 0,
    bug_status: { fixed: 0, in_progress: 0, pending: 0 },
    progress: { uploads: 0, bugs: 0, critical: 0 },
  });

  useEffect(() => {
    const userId = localStorage.getItem("user_id") || "demo_user";
    getDashboardStats(userId)
      .then((data) => { if (!data.error) setStats(data); })
      .catch(() => {});
  }, []);

  const { total_uploads, total_bugs, critical_bugs, bug_status, progress } = stats;
  const total = total_bugs || 1;
  const fixedPct   = Math.round((bug_status.fixed   / total) * 100);
  const inProgPct  = Math.round((bug_status.in_progress / total) * 100);
  const pendingPct = Math.round((bug_status.pending  / total) * 100);

  return (
    <Sidebar>

      <div className="cards" style={{ flexWrap: "nowrap", overflowX: "auto" }}>

        <div className="card">
          <div className="card-header">
            <p>Total Logs Uploaded</p>
            <div className="icon green"><FaUpload /></div>
          </div>
          <h2 className="green-text" style={{ fontSize: "36px", fontWeight: "bold", margin: "10px 0", color: "#0e7a3f" }}>{total_uploads}</h2>
          <div className="progress">
            <div className="green-bar" style={{ width: `${progress.uploads}%` }}></div>
          </div>
          <div className="divider"></div>
          <div className="card-footer" onClick={() => navigate("/tlu")}>
            <span>View details</span><span className="arrow">→</span>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <p>Bugs Detected</p>
            <div className="icon blue"><FaBug /></div>
          </div>
          <h2 className="blue-text" style={{ fontSize: "36px", fontWeight: "bold", margin: "10px 0", color: "#1667a8" }}>{total_bugs}</h2>
          <div className="progress">
            <div className="blue-bar" style={{ width: `${progress.bugs}%` }}></div>
          </div>
          <div className="divider"></div>
          <div className="card-footer" onClick={() => navigate("/bd")}>
            <span>View details</span><span className="arrow">→</span>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <p>Critical Bugs</p>
            <div className="icon red">⚠</div>
          </div>
          <h2 className="red-text" style={{ fontSize: "36px", fontWeight: "bold", margin: "10px 0", color: "#c00d0d" }}>{critical_bugs}</h2>
          <div className="progress">
            <div className="red-bar" style={{ width: `${progress.critical}%` }}></div>
          </div>
          <div className="divider"></div>
          <div className="card-footer" onClick={() => navigate("/cb")}>
            <span>View details</span><span className="arrow">→</span>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <p>Bug Status Summary</p>
            <div className="icon" style={{ background: "#8e9db3" }}>📊</div>
          </div>
          <div style={{ display: "flex", gap: "20px", alignItems: "center" }}>
            <h2 style={{ fontSize: "36px", fontWeight: "bold", margin: "10px 0", color: "#ec4899" }}>{bug_status.fixed}</h2>
            <h2 style={{ fontSize: "36px", fontWeight: "bold", margin: "10px 0", color: "#facc15" }}>{bug_status.in_progress}</h2>
            <h2 style={{ fontSize: "36px", fontWeight: "bold", margin: "10px 0", color: "#8b5cf6" }}>{bug_status.pending}</h2>
          </div>
          <div className="progress" style={{ display: "flex", overflow: "hidden" }}>
            <div style={{ width: `${fixedPct}%`, background: "#ec4899" }}></div>
            <div style={{ width: `${inProgPct}%`, background: "#facc15" }}></div>
            <div style={{ width: `${pendingPct}%`, background: "#8b5cf6" }}></div>
          </div>
          <div className="divider"></div>
          <div className="card-footer" style={{ color: "#64748b", cursor: "pointer" }} onClick={() => navigate("/bss")}>
            <span>View details</span><span className="arrow">→</span>
          </div>
        </div>

      </div>

      {/* WORKFLOW */}
      <div className="workflow-box">
        <div className="workflow-header">
          <div>
            <h3>How This Platform Works</h3>
            <p>Step-by-step process from file upload to bug resolution</p>
          </div>
          <button className="hide-btn" onClick={() => setShowSteps(!showSteps)}>
            {showSteps ? "Hide Steps ▲" : "Show Steps ▼"}
          </button>
        </div>

        {showSteps && (
          <>
            <div className="steps-line">
              {[1,2,3,4,5,6,7].map((num, index) => (
                <div className="step-top" key={num}>
                  <div className={`step-number step-${num}`}>{num}</div>
                  {index !== 6 && (
                    <svg className="arrow-svg" viewBox="0 0 100 10">
                      <line x1="0" y1="5" x2="90" y2="5" stroke="#9ca3af" strokeWidth="2"/>
                      <polygon points="90,0 100,5 90,10" fill="#9ca3af"/>
                    </svg>
                  )}
                </div>
              ))}
            </div>

            <div className="steps-cards">
              <div className="step-card">
                <div className="icon-box icon-blue">⬆</div>
                <h4 style={{ color: "#0bc0d8" }}>File Upload</h4>
                <p>QA uploads .log or .zip or .txt file to the platform.</p>
              </div>
              <div className="step-card">
                <div className="icon-box icon-green">📄</div>
                <h4 style={{ color: "#f8dc3d" }}>File Reading & Analysis</h4>
                <p>System reads and analyzes the code & logs deeply.</p>
              </div>
              <div className="step-card">
                <div className="icon-box icon-orange">🤖</div>
                <h4 style={{ color: "#fd8e3e" }}>AI Bug Detection</h4>
                <p>AI scans the file & detects all types of bugs automatically.</p>
              </div>
              <div className="step-card">
                <div className="icon-box icon-purple">📋</div>
                <h4 style={{ color: "#26d667" }}>Bug Details Display</h4>
                <ul><li>Bug Type</li><li>Line Number</li><li>Reason of bug</li><li>Suggested Fix</li></ul>
              </div>
              <div className="step-card">
                <div className="icon-box icon-pink">👥</div>
                <h4 style={{ color: "#e6308b" }}>Bug Responsibility</h4>
                <p>AI identifies who should fix it:</p>
                <ul><li>QA</li><li>Developer</li><li>Analyst</li><li>Other Role</li></ul>
              </div>
              <div className="step-card">
                <div className="icon-box icon-teal">🔄</div>
                <h4 style={{ color: "#8a3ba1" }}>Re-testing</h4>
                <p>QA fixes the bugs & re-runs analysis to verify the results.</p>
              </div>
              <div className="step-card">
                <div className="icon-box icon-darkblue">✔</div>
                <h4 style={{ color: "#f34e4e" }}>Final Status</h4>
                <p>Bugs are marked as Fixed / Pending / Reopened based on re-testing.</p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* SMART BOX */}
      <div className="smart-box">
        <div className="smart-left">
          <div className="info-icon">i</div>
          <div>
            <h4>Smart Assistance</h4>
            <p>If a bug cannot be resolved after multiple attempts, the platform guides you about the responsible role.</p>
            <p>so you know whether it's you task or needs another expert's attention.</p>
          </div>
        </div>
        <div className="smart-right">👨‍💻📊</div>
      </div>

    </Sidebar>
  );
}

export default Dashboard;
