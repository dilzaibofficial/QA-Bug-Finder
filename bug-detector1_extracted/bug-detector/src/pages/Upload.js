import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import { FaCloudUploadAlt, FaRobot } from "react-icons/fa";
import { uploadFile, getUploadStatus } from "../api";
import "./upload.css";

function Upload() {
  const navigate = useNavigate();
  const fileRef = useRef();

  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");

  const claudeMode = localStorage.getItem("claude_mode") === "true";
  const allowed = [".log", ".txt", ".zip", ".java", ".py", ".js", ".ts", ".cpp", ".c", ".cs"];

  const pickFile = (f) => {
    if (!f) return;
    const ext = "." + f.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) {
      setMessage("Unsupported file type. Allowed: " + allowed.join(", "));
      setStatus("error");
      return;
    }
    setFile(f);
    setStatus("idle");
    setMessage("");
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files[0]);
  };

  const handleUpload = async () => {
    if (!file) { setMessage("Please select a file first."); setStatus("error"); return; }
    const userId = localStorage.getItem("user_id") || "demo_user";

    setStatus("uploading");
    setMessage("Uploading file...");

    try {
      const res = await uploadFile(file, userId, claudeMode);
      if (res.error) { setStatus("error"); setMessage(res.error); return; }

      setStatus("processing");
      setMessage(
        claudeMode
          ? "ML model analyzing... then Claude AI will enhance each bug. This may take longer."
          : "AI is analyzing your file. Please wait..."
      );

      const poll = setInterval(async () => {
        try {
          const s = await getUploadStatus(res.analysis_id);
          if (s.status === "completed") {
            clearInterval(poll);
            setStatus("done");
            setMessage(
              `Analysis complete! Found ${s.total_bugs || 0} bug(s).` +
              (claudeMode ? " Claude AI enhanced results are ready." : "")
            );
          } else if (s.status === "failed") {
            clearInterval(poll);
            setStatus("error");
            setMessage("Analysis failed. Please try again.");
          }
        } catch { clearInterval(poll); }
      }, 2000);

      setTimeout(() => clearInterval(poll), 300000); // 5 min timeout for Claude mode
    } catch {
      setStatus("error");
      setMessage("Server error. Make sure the backend is running.");
    }
  };

  return (
    <Sidebar>
      <div className="upload-container">

        {/* Claude mode banner */}
        {claudeMode && (
          <div style={{
            display: "flex", alignItems: "center", gap: "10px",
            background: "#f3e8ff", border: "1px solid #ddd6fe",
            borderRadius: "10px", padding: "10px 16px", marginBottom: "16px",
            fontSize: "13px", color: "#7c3aed"
          }}>
            <FaRobot size={16} />
            <span>
              <b>Claude AI Mode is ON</b> — each bug will be enhanced with Claude's deep analysis
              and corrected code. Upload may take longer. <a href="/settings" style={{ color: "#7c3aed" }}>Change in Settings →</a>
            </span>
          </div>
        )}

        <div
          className={`upload-box${dragging ? " dragging" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current.click()}
          style={{ cursor: "pointer" }}
        >
          <FaCloudUploadAlt className="cloud-icon" />
          {file ? (
            <>
              <h3>{file.name}</h3>
              <p>{(file.size / 1024).toFixed(1)} KB — click or drop to change</p>
            </>
          ) : (
            <>
              <h3>Drag & Drop Log File Here or Browse</h3>
              <p>Supported formats: .log, .txt, .zip, .java, .py, .js, .ts, .cpp, .c, .cs</p>
            </>
          )}
          <input
            ref={fileRef}
            type="file"
            accept={allowed.join(",")}
            style={{ display: "none" }}
            onChange={(e) => pickFile(e.target.files[0])}
          />
        </div>

        {message && (
          <div style={{
            textAlign: "center", padding: "10px", marginTop: "10px", borderRadius: "8px",
            background: status === "error" ? "#fee2e2" : status === "done" ? "#dcfce7" :
                        claudeMode ? "#f3e8ff" : "#dbeafe",
            color: status === "error" ? "#dc2626" : status === "done" ? "#16a34a" :
                   claudeMode ? "#7c3aed" : "#1d4ed8",
          }}>
            {status === "processing" && (
              <span style={{ marginRight: "8px" }}>
                {claudeMode ? "🤖" : "⏳"}
              </span>
            )}
            {message}
          </div>
        )}

        <div className="upload-btn-wrapper" style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
          <button
            onClick={handleUpload}
            disabled={status === "uploading" || status === "processing"}
            style={{
              opacity: (status === "uploading" || status === "processing") ? 0.6 : 1,
              background: claudeMode ? "#7c3aed" : undefined,
            }}
          >
            {status === "uploading" ? "Uploading..." :
             status === "processing" ? (claudeMode ? "ML + Claude analyzing..." : "Analyzing...") :
             claudeMode ? "🤖 Upload & Analyze with Claude" : "Upload & Analyze"}
          </button>
          {status === "done" && (
            <button onClick={() => navigate("/reports")} style={{ background: "#16a34a" }}>
              View Report →
            </button>
          )}
        </div>

      </div>
    </Sidebar>
  );
}

export default Upload;
