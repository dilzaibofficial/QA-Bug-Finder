import Sidebar from "./Sidebar";

function CardBD() {
  return (
    <Sidebar>
      <div style={{ padding: "20px" }}>
        <h2>Bugs Detected</h2>
        <p>🔹 Card 2: Total Bugs
Total Count
→ sab files ke bugs ka total

👉 Example:

4 files → total bugs = 20
UI Bugs
→ design/layout wale issues
Logical Bugs
→ code logic galat
Crash Bugs
→ app band ho jati hai
Performance Bugs
→ slow ya heavy system

👉 Iska purpose:
QA ko pata chale kis type ke bugs zyada hain</p>
      </div>
    </Sidebar>
  );
}

export default CardBD;