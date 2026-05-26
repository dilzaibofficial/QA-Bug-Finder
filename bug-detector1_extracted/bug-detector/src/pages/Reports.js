import { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import "./reports.css";
import { FaBug, FaExclamationTriangle, FaDownload } from "react-icons/fa";
import { getReports, updateBugStatus } from "../api";

function Reports() {
  const [search, setSearch]     = useState("");
  const [severity, setSeverity] = useState("All Severities");
  const [status, setStatus]     = useState("All Statuses");
  const [bugs, setBugs]         = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [fixModal, setFixModal] = useState(null);
  const [groupByFile, setGroupByFile] = useState(false);

  const userId = localStorage.getItem("user_id") || "demo_user";

  const fetchBugs = () => {
    setLoading(true);
    const filters = {};
    if (severity !== "All Severities") filters.severity = severity;
    if (status   !== "All Statuses")   filters.status   = status;
    getReports(userId, filters)
      .then((res) => {
        if (!res.error) { setBugs(res.bugs || []); setAnalysis(res.analysis); }
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchBugs(); }, [severity, status]); // eslint-disable-line

  const filtered = bugs.filter((b) =>
    b.type?.toLowerCase().includes(search.toLowerCase()) ||
    b.file?.toLowerCase().includes(search.toLowerCase()) ||
    b.bug_id?.toLowerCase().includes(search.toLowerCase())
  );

  // Detect if this is a ZIP analysis (multiple distinct files)
  const uniqueFiles = [...new Set(bugs.map((b) => b.file).filter(Boolean))];
  const isZipAnalysis = uniqueFiles.length > 1;

  const handleStatusChange = async (bugId, newStatus) => {
    await updateBugStatus(bugId, newStatus);
    setBugs((prev) => prev.map((b) => b._id === bugId ? { ...b, status: newStatus } : b));
  };

  const severityClass = (s) =>
    s === "Critical" ? "red" : s === "High" ? "orange" : s === "Medium" ? "blue" : "green";

  const statusClass = (s) =>
    s === "Open" ? "yellow" : s === "In Progress" ? "blue" : s === "Reopened" ? "red" :
    s === "Fixed" ? "green" : s === "Close" ? "orange" : "grey";

  const totalBugs    = analysis?.total_bugs    ?? bugs.length;
  const criticalBugs = analysis?.critical_bugs ?? bugs.filter((b) => b.severity === "Critical").length;
  const fixedCount   = bugs.filter((b) => b.status === "Fixed").length;
  const fixedPct     = totalBugs ? Math.round((fixedCount / totalBugs) * 100) : 0;
  const circumference = 2 * Math.PI * 18;

  // ── PDF Download ─────────────────────────────────────────────────────────────
  const downloadPDF = async () => {
    const { default: jsPDF } = await import("jspdf");
    const { default: autoTable } = await import("jspdf-autotable");

    const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    const hasClaudeData = filtered.some((b) => b.claude_enhanced);

    const sevColor = (s) =>
      s === "Critical" ? [220,38,38] : s === "High" ? [234,88,12] :
      s === "Medium"   ? [22,103,168] : [22,163,74];

    const addFooters = () => {
      const total = doc.internal.getNumberOfPages();
      for (let p = 1; p <= total; p++) {
        doc.setPage(p);
        doc.setFontSize(7); doc.setTextColor(150);
        doc.text(
          `Page ${p} of ${total}  •  AI Bug Detector Report${hasClaudeData ? "  •  Claude AI Enhanced" : ""}`,
          pageW / 2, pageH - 5, { align: "center" }
        );
      }
    };

    // ── Header bar ───────────────────────────────────────────────────────────
    doc.setFillColor(22, 103, 168);
    doc.rect(0, 0, pageW, 18, "F");
    if (hasClaudeData) {
      doc.setFillColor(124, 58, 237);
      doc.rect(pageW - 60, 0, 60, 18, "F");
    }
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(14); doc.setFont("helvetica", "bold");
    doc.text("AI Bug Detector — Bug Report", 14, 12);
    doc.setFontSize(8); doc.setFont("helvetica", "normal");
    if (hasClaudeData) {
      doc.text("Claude AI Enhanced", pageW - 56, 8);
      doc.setFontSize(7);
      doc.text("ML + Claude analysis", pageW - 56, 14);
    }
    doc.setFontSize(8);
    doc.text(`Generated: ${new Date().toLocaleString()}`, hasClaudeData ? pageW - 65 : pageW - 14, 12,
      { align: "right" });

    // ── Meta info ────────────────────────────────────────────────────────────
    doc.setTextColor(30, 30, 30); doc.setFontSize(9);
    let y = 24;
    doc.text(`File: ${analysis?.filename || "—"}`, 14, y);
    doc.text(`Analysis ID: ${analysis?.analysis_id || "—"}`, 100, y);
    doc.text(`Total: ${totalBugs}  Critical: ${criticalBugs}  Fixed: ${fixedCount} (${fixedPct}%)`, 210, y);
    y += 4;
    doc.text(`Status: ${analysis?.status || "—"}    Started: ${analysis?.start_time ? new Date(analysis.start_time).toLocaleString() : "—"}`, 14, y);
    y += 6;

    // ── Severity summary boxes ────────────────────────────────────────────────
    const severityCounts = { Critical: 0, High: 0, Medium: 0, Low: 0 };
    filtered.forEach((b) => { if (b.severity in severityCounts) severityCounts[b.severity]++; });
    let bx = 14;
    Object.entries(severityCounts).forEach(([sev, cnt]) => {
      const c = sevColor(sev);
      doc.setFillColor(...c);
      doc.roundedRect(bx, y, 42, 11, 2, 2, "F");
      doc.setTextColor(255, 255, 255); doc.setFontSize(8); doc.setFont("helvetica", "bold");
      doc.text(`${sev}: ${cnt}`, bx + 4, y + 7.5);
      bx += 46;
    });
    y += 17;
    doc.setTextColor(30, 30, 30); doc.setFont("helvetica", "normal");

    // ── Helper: draw one ML+Claude table for a list of bugs ──────────────────
    const drawBugTable = (bugList, startY, showFile = true) => {
      // ML columns always shown
      const mlHead = showFile
        ? ["Bug ID", "Type", "Sev", "File", "Line", "Description", "ML Reason", "ML Fix", "Status"]
        : ["Bug ID", "Type", "Sev", "Line", "Description", "ML Reason", "ML Fix", "Status"];

      const mlBody = bugList.map((b) => showFile
        ? [b.bug_id||"", b.type||"", b.severity||"", b.file||"", b.line_number||"",
           b.description||"", b.ai_reason||"", b.suggested_fix||"", b.status||""]
        : [b.bug_id||"", b.type||"", b.severity||"", b.line_number||"",
           b.description||"", b.ai_reason||"", b.suggested_fix||"", b.status||""]
      );

      const sevIdx = 2;
      autoTable(doc, {
        startY,
        head: [mlHead],
        body: mlBody,
        styles: { fontSize: 7, cellPadding: 2, overflow: "linebreak" },
        headStyles: { fillColor: [22, 103, 168], textColor: 255, fontStyle: "bold", fontSize: 7 },
        columnStyles: showFile
          ? { 0:{cellWidth:16}, 1:{cellWidth:16}, 2:{cellWidth:16}, 3:{cellWidth:26},
              4:{cellWidth:9},  5:{cellWidth:36}, 6:{cellWidth:44}, 7:{cellWidth:48}, 8:{cellWidth:18} }
          : { 0:{cellWidth:16}, 1:{cellWidth:16}, 2:{cellWidth:16}, 3:{cellWidth:9},
              4:{cellWidth:38}, 5:{cellWidth:48}, 6:{cellWidth:54}, 7:{cellWidth:18} },
        didParseCell: (data) => {
          if (data.row.section === "body" && data.column.index === sevIdx) {
            data.cell.styles.fillColor = sevColor(data.cell.raw);
            data.cell.styles.textColor = [255,255,255];
            data.cell.styles.fontStyle = "bold";
          }
        },
        margin: { left: 14, right: 14 },
      });
      let ty = doc.lastAutoTable.finalY + 4;

      // Claude section — only bugs that have claude_enhanced
      const claudeBugs = bugList.filter((b) => b.claude_enhanced);
      if (claudeBugs.length) {
        // Claude section banner
        doc.setFillColor(124, 58, 237);
        doc.roundedRect(14, ty, pageW - 28, 7, 1.5, 1.5, "F");
        doc.setTextColor(255, 255, 255); doc.setFontSize(8); doc.setFont("helvetica", "bold");
        doc.text(`🤖  Claude AI Enhanced Analysis  (${claudeBugs.length} bug${claudeBugs.length > 1 ? "s" : ""})`, 18, ty + 5);
        ty += 9;
        doc.setTextColor(30,30,30); doc.setFont("helvetica", "normal");

        autoTable(doc, {
          startY: ty,
          head: [["Bug ID", "Sev", "Claude Explanation", "Claude Technical Reasoning", "Corrected Code", "Why This Fix Works"]],
          body: claudeBugs.map((b) => [
            b.bug_id||"", b.severity||"",
            b.claude_description||"",
            b.claude_reason||"",
            b.claude_corrected_code||"",
            b.claude_fix_explanation||"",
          ]),
          styles: { fontSize: 7, cellPadding: 2, overflow: "linebreak" },
          headStyles: { fillColor: [124, 58, 237], textColor: 255, fontStyle: "bold", fontSize: 7 },
          columnStyles: {
            0: { cellWidth: 16 }, 1: { cellWidth: 14 },
            2: { cellWidth: 52 }, 3: { cellWidth: 55 },
            4: { cellWidth: 55 }, 5: { cellWidth: 48 },
          },
          didParseCell: (data) => {
            if (data.row.section === "body" && data.column.index === 1) {
              data.cell.styles.fillColor = sevColor(data.cell.raw);
              data.cell.styles.textColor = [255,255,255];
              data.cell.styles.fontStyle = "bold";
            }
            if (data.row.section === "body" && data.column.index === 4) {
              data.cell.styles.fontFamily = "courier";
              data.cell.styles.fontSize = 6.5;
              data.cell.styles.fillColor = [30, 30, 46];
              data.cell.styles.textColor = [196, 181, 253];
            }
          },
          margin: { left: 14, right: 14 },
        });
        ty = doc.lastAutoTable.finalY + 8;
      }

      return ty;
    };

    // ── Render: ZIP grouped or single ────────────────────────────────────────
    if (isZipAnalysis) {
      uniqueFiles.forEach((fname) => {
        const fileBugs = filtered.filter((b) => b.file === fname);
        if (!fileBugs.length) return;

        doc.setFillColor(240, 249, 255);
        doc.rect(14, y - 1, pageW - 28, 7, "F");
        doc.setFontSize(9); doc.setFont("helvetica", "bold");
        doc.setTextColor(22, 103, 168);
        doc.text(`  ${fname}   (${fileBugs.length} bug${fileBugs.length > 1 ? "s" : ""})`, 16, y + 4);
        doc.setTextColor(30, 30, 30); doc.setFont("helvetica", "normal");
        y += 9;
        y = drawBugTable(fileBugs, y, false);
      });
    } else {
      y = drawBugTable(filtered, y, true);
    }

    addFooters();
    doc.save(`bug-report-${analysis?.filename || "analysis"}-${new Date().toISOString().slice(0,10)}.pdf`);
  };

  // ── Bug table rows ────────────────────────────────────────────────────────────
  const renderRows = (bugList) =>
    bugList.length === 0 ? (
      <tr><td colSpan="11" style={{ textAlign: "center", padding: "20px" }}>
        {bugs.length === 0 ? "No analysis found. Upload a file first." : "No bugs match filters."}
      </td></tr>
    ) : bugList.map((bug) => (
      <tr key={bug._id}>
        <td>
          <span title={`AI Confidence: ${((bug.defect_probability || 0) * 100).toFixed(0)}%`}
            style={{ cursor: "help", fontWeight: "bold" }}>
            {bug.bug_id}
          </span>
        </td>
        <td className={bug.type === "UI" ? "blue-text" : bug.type === "Crash" ? "red-text" : "green-text"}>
          {bug.type}
        </td>
        <td><span className={`badge small ${severityClass(bug.severity)}`}>{bug.severity}</span></td>
        <td title={bug.file} style={{ maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {bug.file}
        </td>
        <td style={{ textAlign: "center" }}>{bug.line_number}</td>
        <td style={{ maxWidth: "160px" }}>{bug.description}</td>
        <td style={{ maxWidth: "180px", color: "#555", fontSize: "13px" }}>{bug.ai_reason}</td>
        <td>
          <button className="fix-btn" onClick={() => setFixModal(bug)}>View Fix</button>
        </td>
        <td>{bug.assigned_to}</td>
        <td>
          <select
            value={bug.status}
            className={`badge small ${statusClass(bug.status)}`}
            onChange={(e) => handleStatusChange(bug._id, e.target.value)}
            style={{ border: "none", cursor: "pointer", fontWeight: "bold" }}
          >
            <option>Open</option><option>In Progress</option>
            <option>Fixed</option><option>Reopened</option><option>Close</option>
          </select>
        </td>
        <td style={{ textAlign: "center", fontSize: "12px", color: "#888" }}>
          <span title="Defect probability">{((bug.defect_probability || 0) * 100).toFixed(0)}%</span>
          <br />
          <span title="Type confidence" style={{ color: "#aaa" }}>
            {((bug.type_confidence || 0) * 100).toFixed(0)}% conf
          </span>
        </td>
      </tr>
    ));

  return (
    <Sidebar>
      <div className="bug-report">

        <div className="top-row">
          <div className="top-box">
            <div className="active-file-box">
              <span className="dot"></span>
              <b>Active File</b>
            </div>
            <div className="active-text">This is the most recent / active file report.</div>
          </div>
          <div className="actions" style={{ display: "flex", gap: "8px" }}>
            <button className="btn light" onClick={fetchBugs}>⟳ Re-run Analysis</button>
            <button className="btn light" onClick={downloadPDF}
              style={{ display: "flex", alignItems: "center", gap: "6px", background: "#1667a8", color: "#fff" }}>
              <FaDownload size={13} /> Download PDF
            </button>
          </div>
        </div>

        {/* FILE INFO */}
        <div className="file-box">
          <div className="file-left">
            <img src="https://cdn-icons-png.flaticon.com/512/337/337946.png" alt="file" className="file-img" />
            <div>
              <h3>{analysis?.filename || "No file analyzed yet"}</h3>
              <p>Analysis ID: {analysis?.analysis_id || "—"}</p>
              <p>Started: {analysis?.start_time ? new Date(analysis.start_time).toLocaleString() : "—"}</p>
              <p>Status: {analysis?.status || "—"}</p>
            </div>
          </div>

          <div className="stats">
            <div className="stat">
              <p>Total Bugs</p>
              <h2>{totalBugs}</h2>
              <span className="stat-icon blue"><FaBug /></span>
            </div>
            <div className="stat red">
              <p>Critical Bugs</p>
              <h2>{criticalBugs}</h2>
              <span className="stat-icon red"><FaExclamationTriangle /></span>
            </div>
            <div className="stat green">
              <p>Overall Status</p>
              <h3>{fixedPct === 100 ? "Completed" : fixedPct > 0 ? "In Progress" : "Pending"}</h3>
              <div className="progress-ring">
                <svg width="45" height="45" viewBox="0 0 45 45">
                  <circle cx="22.5" cy="22.5" r="18" stroke="#e5e7eb" strokeWidth="4" fill="none"/>
                  <circle cx="22.5" cy="22.5" r="18" stroke="#16a34a" strokeWidth="4" fill="none"
                    strokeDasharray={circumference}
                    strokeDashoffset={circumference - (circumference * fixedPct) / 100}
                    strokeLinecap="round"/>
                </svg>
                <span>{fixedPct}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* FILTERS */}
        <div className="filters-box">
          <span>Bug Type</span>
          <div className="input-wrapper">
            <input type="text" placeholder="Search bugs..." className="filter-input"
              value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>

          <span>Severity</span>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option>All Severities</option>
            <option>Low</option><option>Medium</option><option>High</option><option>Critical</option>
          </select>

          <span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option>All Statuses</option>
            <option>Open</option><option>Reopened</option><option>Fixed</option>
            <option>In Progress</option><option>Close</option>
          </select>

          {isZipAnalysis && (
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
              <input type="checkbox" checked={groupByFile}
                onChange={(e) => setGroupByFile(e.target.checked)} />
              Group by file
            </label>
          )}

          <button className="clear-btn" onClick={() => { setSearch(""); setSeverity("All Severities"); setStatus("All Statuses"); }}>
            ⟳ Clear Filters
          </button>
        </div>

        {/* TABLE */}
        <div className="table-box-scroll">
          <div className="tabox">
            {loading ? (
              <p style={{ padding: "20px", textAlign: "center" }}>Loading bugs...</p>
            ) : isZipAnalysis && groupByFile ? (
              /* ZIP grouped by file */
              uniqueFiles.map((fname) => {
                const fileBugs = filtered.filter((b) => b.file === fname);
                if (!fileBugs.length) return null;
                return (
                  <div key={fname} style={{ marginBottom: "20px" }}>
                    <div style={{
                      background: "#eff6ff", borderLeft: "4px solid #1667a8",
                      padding: "8px 14px", borderRadius: "6px 6px 0 0",
                      fontWeight: "600", fontSize: "13px", color: "#1667a8",
                      display: "flex", justifyContent: "space-between", alignItems: "center"
                    }}>
                      <span>📄 {fname}</span>
                      <span style={{ fontSize: "12px", color: "#64748b", fontWeight: "normal" }}>
                        {fileBugs.length} bug{fileBugs.length > 1 ? "s" : ""}
                        &nbsp;·&nbsp;
                        {fileBugs.filter((b) => b.severity === "Critical").length} critical
                      </span>
                    </div>
                    <table style={{ borderRadius: "0 0 6px 6px", overflow: "hidden" }}>
                      <thead>
                        <tr>
                          <th>Bug ID</th><th>Type</th><th>Severity</th><th>File</th>
                          <th>Line #</th><th>Description</th><th>AI Reason</th>
                          <th>Suggested Fix</th><th>Assigned To</th><th>Status</th><th>Confidence</th>
                        </tr>
                      </thead>
                      <tbody>{renderRows(fileBugs)}</tbody>
                    </table>
                  </div>
                );
              })
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Bug ID</th><th>Type</th><th>Severity</th><th>File</th>
                    <th>Line #</th><th>Description</th><th>AI Reason</th>
                    <th>Suggested Fix</th><th>Assigned To</th><th>Status</th><th>Confidence</th>
                  </tr>
                </thead>
                <tbody>{renderRows(filtered)}</tbody>
              </table>
            )}
          </div>
        </div>

      </div>

      {/* FIX MODAL */}
      {fixModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000
        }} onClick={() => setFixModal(null)}>
          <div style={{
            background: "#fff", borderRadius: "14px", padding: "0",
            maxWidth: "640px", width: "94%", boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
            overflow: "hidden", maxHeight: "90vh", overflowY: "auto"
          }} onClick={(e) => e.stopPropagation()}>

            {/* Header */}
            <div style={{
              background: fixModal.severity === "Critical" ? "#dc2626" :
                          fixModal.severity === "High"     ? "#ea580c" :
                          fixModal.severity === "Medium"   ? "#1667a8" : "#16a34a",
              color: "#fff", padding: "16px 24px", display: "flex",
              justifyContent: "space-between", alignItems: "center",
              position: "sticky", top: 0, zIndex: 1
            }}>
              <div>
                <div style={{ fontSize: "12px", opacity: 0.85, marginBottom: "2px" }}>
                  {fixModal.bug_id} &nbsp;•&nbsp; {fixModal.type} Bug &nbsp;•&nbsp; {fixModal.severity}
                </div>
                <div style={{ fontWeight: "bold", fontSize: "16px" }}>Bug Detail & Suggested Fix</div>
              </div>
              <span onClick={() => setFixModal(null)}
                style={{ cursor: "pointer", fontSize: "20px", opacity: 0.8 }}>✕</span>
            </div>

            {/* Body */}
            <div style={{ padding: "22px 24px" }}>

              {/* Location */}
              <div style={{
                background: "#f8fafc", border: "1px solid #e2e8f0",
                borderRadius: "8px", padding: "12px 16px", marginBottom: "16px",
                display: "flex", gap: "24px", flexWrap: "wrap"
              }}>
                <div>
                  <div style={{ fontSize: "11px", color: "#888", marginBottom: "2px" }}>FILE</div>
                  <div style={{ fontWeight: "600", color: "#1e293b", fontSize: "13px" }}>📄 {fixModal.file}</div>
                </div>
                <div>
                  <div style={{ fontSize: "11px", color: "#888", marginBottom: "2px" }}>LINE NUMBER</div>
                  <div style={{ fontWeight: "600", color: "#1667a8", fontSize: "13px" }}>→ Line {fixModal.line_number}</div>
                </div>
                <div>
                  <div style={{ fontSize: "11px", color: "#888", marginBottom: "2px" }}>ASSIGNED TO</div>
                  <div style={{ fontWeight: "600", color: "#1e293b", fontSize: "13px" }}>👤 {fixModal.assigned_to}</div>
                </div>
                <div>
                  <div style={{ fontSize: "11px", color: "#888", marginBottom: "2px" }}>AI CONFIDENCE</div>
                  <div style={{ fontWeight: "600", color: "#16a34a", fontSize: "13px" }}>
                    {((fixModal.defect_probability || 0) * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Description */}
              <div style={{ marginBottom: "14px" }}>
                <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b",
                  textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "6px" }}>
                  🔍 What is the Bug?
                </div>
                <div style={{ background: "#fef9c3", borderLeft: "4px solid #eab308",
                  padding: "10px 14px", borderRadius: "6px", fontSize: "14px", color: "#1e293b" }}>
                  {fixModal.description}
                </div>
              </div>

              {/* Buggy Code Line */}
              {fixModal.code_snippet && (
                <div style={{ marginBottom: "14px" }}>
                  <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b",
                    textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "6px" }}>
                    🐛 Buggy Line (Line {fixModal.line_number})
                  </div>
                  <div style={{
                    background: "#1e1e2e", borderLeft: "4px solid #dc2626",
                    borderRadius: "6px", padding: "12px 16px", overflowX: "auto"
                  }}>
                    <div style={{ fontSize: "11px", color: "#888", marginBottom: "6px", fontFamily: "monospace" }}>
                      {fixModal.file} : line {fixModal.line_number}
                    </div>
                    <pre style={{
                      margin: 0, color: "#f87171", fontFamily: "'Courier New', Courier, monospace",
                      fontSize: "13px", whiteSpace: "pre-wrap", wordBreak: "break-all"
                    }}>{fixModal.code_snippet}</pre>
                  </div>
                </div>
              )}

              {/* AI Reason */}
              <div style={{ marginBottom: "14px" }}>
                <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b",
                  textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "6px" }}>
                  🤖 Why did AI flag this?
                </div>
                <div style={{ background: "#fef2f2", borderLeft: "4px solid #dc2626",
                  padding: "10px 14px", borderRadius: "6px", fontSize: "14px", color: "#1e293b", lineHeight: "1.6" }}>
                  {fixModal.ai_reason}
                </div>
              </div>

              {/* Suggested Fix */}
              <div style={{ marginBottom: fixModal.code_snippet ? "14px" : "20px" }}>
                <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b",
                  textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "6px" }}>
                  ✅ How to Fix It
                </div>
                <div style={{ background: "#f0fdf4", borderLeft: "4px solid #16a34a",
                  padding: "10px 14px", borderRadius: "6px", fontSize: "14px", color: "#1e293b", lineHeight: "1.6" }}>
                  {fixModal.suggested_fix}
                </div>
              </div>

              {/* What correct code should look like (ML fallback) */}
              {fixModal.code_snippet && !fixModal.claude_enhanced && (
                <div style={{ marginBottom: "20px" }}>
                  <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b",
                    textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "6px" }}>
                    💡 What Correct Code Should Look Like
                  </div>
                  <div style={{
                    background: "#1e1e2e", borderLeft: "4px solid #16a34a",
                    borderRadius: "6px", padding: "12px 16px", overflowX: "auto"
                  }}>
                    <div style={{ fontSize: "11px", color: "#888", marginBottom: "6px", fontFamily: "monospace" }}>
                      Suggested refactored version
                    </div>
                    <pre style={{
                      margin: 0, color: "#86efac", fontFamily: "'Courier New', Courier, monospace",
                      fontSize: "13px", whiteSpace: "pre-wrap", wordBreak: "break-all"
                    }}>{generateCorrectCode(fixModal)}</pre>
                  </div>
                </div>
              )}

              {/* ── Claude AI Enhanced Section ─────────────────────────── */}
              {fixModal.claude_enhanced && (
                <div style={{ marginBottom: "20px" }}>
                  {/* Claude section header */}
                  <div style={{
                    display: "flex", alignItems: "center", gap: "8px",
                    background: "linear-gradient(90deg,#7c3aed,#6d28d9)",
                    borderRadius: "8px", padding: "10px 16px", marginBottom: "14px"
                  }}>
                    <span style={{ fontSize: "18px" }}>🤖</span>
                    <div>
                      <div style={{ color: "#fff", fontWeight: "700", fontSize: "14px" }}>Claude AI Enhanced Analysis</div>
                      <div style={{ color: "#ddd6fe", fontSize: "11px" }}>Powered by Claude claude-haiku-4-5 — deeper insights & corrected code</div>
                    </div>
                  </div>

                  {/* Claude Description */}
                  {fixModal.claude_description && (
                    <div style={{ marginBottom: "12px" }}>
                      <div style={{ fontSize: "11px", fontWeight: "700", color: "#7c3aed",
                        textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "5px" }}>
                        🔍 Claude's Bug Explanation
                      </div>
                      <div style={{ background: "#faf5ff", borderLeft: "4px solid #7c3aed",
                        padding: "10px 14px", borderRadius: "6px", fontSize: "14px", color: "#1e293b", lineHeight: "1.6" }}>
                        {fixModal.claude_description}
                      </div>
                    </div>
                  )}

                  {/* Claude Reason */}
                  {fixModal.claude_reason && (
                    <div style={{ marginBottom: "12px" }}>
                      <div style={{ fontSize: "11px", fontWeight: "700", color: "#7c3aed",
                        textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "5px" }}>
                        🤖 Claude's Technical Reasoning
                      </div>
                      <div style={{ background: "#f3e8ff", borderLeft: "4px solid #a855f7",
                        padding: "10px 14px", borderRadius: "6px", fontSize: "14px", color: "#1e293b", lineHeight: "1.6" }}>
                        {fixModal.claude_reason}
                      </div>
                    </div>
                  )}

                  {/* Claude Corrected Code */}
                  {fixModal.claude_corrected_code && (
                    <div style={{ marginBottom: "12px" }}>
                      <div style={{ fontSize: "11px", fontWeight: "700", color: "#7c3aed",
                        textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "5px" }}>
                        ✅ Claude's Corrected Code
                      </div>
                      <div style={{
                        background: "#1e1e2e", borderLeft: "4px solid #7c3aed",
                        borderRadius: "6px", padding: "12px 16px", overflowX: "auto"
                      }}>
                        <div style={{ fontSize: "11px", color: "#a78bfa", marginBottom: "6px", fontFamily: "monospace" }}>
                          Claude-generated fix
                        </div>
                        <pre style={{
                          margin: 0, color: "#c4b5fd", fontFamily: "'Courier New', Courier, monospace",
                          fontSize: "13px", whiteSpace: "pre-wrap", wordBreak: "break-all"
                        }}>{fixModal.claude_corrected_code}</pre>
                      </div>
                    </div>
                  )}

                  {/* Claude Fix Explanation */}
                  {fixModal.claude_fix_explanation && (
                    <div style={{ marginBottom: "4px" }}>
                      <div style={{ fontSize: "11px", fontWeight: "700", color: "#7c3aed",
                        textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "5px" }}>
                        💡 Why This Fix Works
                      </div>
                      <div style={{ background: "#ede9fe", borderLeft: "4px solid #8b5cf6",
                        padding: "10px 14px", borderRadius: "6px", fontSize: "14px", color: "#1e293b", lineHeight: "1.6" }}>
                        {fixModal.claude_fix_explanation}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <button onClick={() => setFixModal(null)} style={{
                width: "100%", padding: "10px", background: "#1667a8", color: "#fff",
                border: "none", borderRadius: "8px", cursor: "pointer",
                fontSize: "14px", fontWeight: "600"
              }}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </Sidebar>
  );
}

function generateCorrectCode(bug) {
  const line = bug.code_snippet || "";
  const type = (bug.type || "").toLowerCase();
  const sev  = (bug.severity || "").toLowerCase();

  // Try to generate a meaningful suggestion based on bug type
  if (type === "crash") {
    if (line.includes("null") || line.includes("None")) {
      return `// Add null-check before this line:\nif (obj != null) {\n    ${line.trim()}\n}`;
    }
    return `try {\n    ${line.trim()}\n} catch (Exception e) {\n    // Handle or log the exception\n    logger.error("Error: " + e.getMessage());\n}`;
  }

  if (type === "performance") {
    if (line.includes("class ") || line.includes("def ") || line.includes("function")) {
      return `// Refactor: split into smaller, single-responsibility units\n// Instead of one large class/function, extract:\n//   - Core logic → separate module\n//   - Utilities  → helper class\n//   - Data access → repository layer\n\n${line.trim()}  // ← break this up`;
    }
    return `// Optimize: reduce coupling and complexity\n// Original:\n// ${line.trim()}\n\n// Refactored approach: extract logic into smaller methods`;
  }

  if (type === "logical") {
    return `// Refactor: reduce cyclomatic complexity\n// Original:\n// ${line.trim()}\n\n// Suggested: extract branches into named helper methods\n// e.g.:\n// if (isValidCondition()) { handleValidCase(); }\n// else { handleFallback(); }`;
  }

  if (type === "ui") {
    return `// Ensure proper state management and rendering:\n// ${line.trim()}\n\n// Check: state updates, event handlers, and component lifecycle`;
  }

  // Generic fallback
  return `// Review and refactor the flagged line:\n// ${line.trim()}\n\n// Apply the suggested fix described above.`;
}

export default Reports;
