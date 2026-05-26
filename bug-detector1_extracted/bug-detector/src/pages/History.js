import React, { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import "./history.css";
import {
  FiMessageSquare, FiStar, FiTrash2, FiSearch, FiCalendar, FiEye, FiFileText,
} from "react-icons/fi";
import { getHistory, getHistoryStats, deleteHistory, toggleStar } from "../api";

function History() {
  const [search, setSearch]   = useState("");
  const [status, setStatus]   = useState("All Statuses");
  const [type, setType]       = useState("All Types");
  const [date, setDate]       = useState("");
  const [data, setData]       = useState([]);
  const [hstats, setHstats]   = useState({ total_files: 0, starred_files: 0, deleted_files: 0, notes_comments: 0 });
  const [loading, setLoading] = useState(true);

  const userId = localStorage.getItem("user_id") || "demo_user";

  const fetchData = () => {
    setLoading(true);
    const filters = {};
    if (status !== "All Statuses") filters.status = status;
    if (type   !== "All Types")    filters.type   = type;
    if (search)                    filters.search = search;

    Promise.all([
      getHistory(userId, filters),
      getHistoryStats(userId),
    ]).then(([hist, stats]) => {
      if (!hist.error)   setData(hist.history || []);
      if (!stats.error)  setHstats(stats);
    }).finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [status, type]); // eslint-disable-line

  // Client-side date filter (server doesn't support it)
  const filtered = data.filter((item) =>
    (!search || item.filename?.toLowerCase().includes(search.toLowerCase())) &&
    (!date   || item.analyzed_on?.includes(date))
  );

  const handleDelete = async (id) => {
    await deleteHistory(id);
    setData((prev) => prev.filter((r) => r._id !== id));
  };

  const handleStar = async (id) => {
    const res = await toggleStar(id);
    setData((prev) => prev.map((r) => r._id === id ? { ...r, starred: res.starred } : r));
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleString() : "—";
  const extOf   = (name = "") => (name.split(".").pop() || "").toUpperCase();

  return (
    <Sidebar>
      <div className="history">

        <div className="history-header">
          <h2>Analysis History</h2>
          <p>View all your previously analyzed files and their results.</p>
        </div>

        {/* STATS CARDS */}
        <div className="history-cards" style={{ flexWrap: "nowrap", overflowX: "auto" }}>
          <div className="h-card-a">
            <div className="card-head">
              <p>Notes & Comments</p>
              <div className="h-icon blue"><FiMessageSquare /></div>
            </div>
            <h3>{hstats.notes_comments}</h3>
            <div className="divider"></div>
            <div className="card-footer"><span>View details</span><span className="arrow">→</span></div>
          </div>

          <div className="h-card-b">
            <div className="card-head">
              <p>Starred Files</p>
              <div className="h-icon green"><FiStar /></div>
            </div>
            <h3>{hstats.starred_files}</h3>
            <div className="divider"></div>
            <div className="card-footer"><span>View details</span><span className="arrow">→</span></div>
          </div>

          <div className="h-card-c">
            <div className="card-head">
              <p>Total Analyzed Files</p>
              <div className="h-icon red"><FiTrash2 /></div>
            </div>
            <h3>{hstats.total_files}</h3>
            <div className="divider"></div>
            <div className="card-footer"><span>View details</span><span className="arrow">→</span></div>
          </div>
        </div>

        {/* FILTERS */}
        <div className="history-filters">
          <div className="search-box">
            <FiSearch />
            <input placeholder="Search by file name..." value={search}
              onChange={(e) => { setSearch(e.target.value); }} />
          </div>

          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option>All Statuses</option>
            <option>completed</option>
            <option>processing</option>
            <option>failed</option>
          </select>

          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option>All Types</option>
            <option>ZIP</option><option>JAVA</option><option>PY</option>
            <option>JS</option><option>LOG</option><option>TXT</option>
          </select>

          <div className="date-box">
            <FiCalendar />
            <input type="text" placeholder="Filter by date..." value={date}
              onChange={(e) => setDate(e.target.value)} />
          </div>

          <button className="clear-btn" onClick={() => {
            setSearch(""); setStatus("All Statuses"); setType("All Types"); setDate("");
          }}>
            ⟳ Clear Filters
          </button>
        </div>

        {/* TABLE */}
        <div className="table-outer">
          <div className="table-wrapper">
            <table className="history-table">
              <thead>
                <tr>
                  <th>File Name</th><th>File Type</th><th>Analyzed On</th>
                  <th>Total Bugs</th><th>Critical Bugs</th><th>Status</th>
                  <th>Progress</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="8" style={{ textAlign: "center", padding: "20px" }}>Loading...</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan="8" style={{ textAlign: "center", padding: "20px" }}>
                    {data.length === 0 ? "No history yet. Upload a file to get started." : "No results match your filters."}
                  </td></tr>
                ) : filtered.map((item) => {
                  const ext      = item.file_type || extOf(item.filename);
                  const progress = item.status === "completed" ? 100 : item.status === "processing" ? 50 : 0;
                  return (
                    <tr key={item._id}>
                      <td>
                        <strong>{item.filename}</strong>
                        <p style={{ fontSize: "12px", color: "#888" }}>{item._id}</p>
                      </td>
                      <td><span className={`badge ${ext.toLowerCase()}`}>{ext}</span></td>
                      <td>{fmtDate(item.analyzed_on)}</td>
                      <td>{item.total_bugs ?? "—"}</td>
                      <td className="critical">{item.critical_bugs ?? "—"}</td>
                      <td>
                        <span className={`status ${item.status?.replace(" ", "-").toLowerCase()}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>
                        <div className="progress-bar">
                          <div style={{ width: `${progress}%` }}></div>
                        </div>
                        <span className="percent">{progress}%</span>
                      </td>
                      <td className="actions">
                        <FiEye title="View" />
                        <FiFileText title="Report" />
                        <FiStar
                          title={item.starred ? "Unstar" : "Star"}
                          style={{ color: item.starred ? "#f59e0b" : undefined, cursor: "pointer" }}
                          onClick={() => handleStar(item._id)}
                        />
                        <FiTrash2
                          className="delete"
                          title="Delete"
                          style={{ cursor: "pointer" }}
                          onClick={() => handleDelete(item._id)}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </Sidebar>
  );
}

export default History;
