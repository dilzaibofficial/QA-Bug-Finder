import Sidebar from "./Sidebar";

function CardTLU() {
  return (
    <Sidebar>
      <div style={{ padding: "20px" }}>
        <h2>Total Logs Uploaded</h2>
        <p>🔹 Card 1: Total Files
Count
→ jitni files tumne ab tak upload ki hain (total)
Active Files (Processing) ⭐
→ wo files jo abhi analyze ho rahi hain
👉 Example:
Total files: 4
Active: 1 (matlab 1 file abhi AI analyze kar raha hai)</p>
      </div>
    </Sidebar>
  );
}

export default CardTLU;

