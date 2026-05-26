import Sidebar from "./Sidebar";

function CardCB() {
  return (
    <Sidebar>
      <div style={{ padding: "20px" }}>
        <h2>Critical Bugs</h2>
        <p>🔹 Card 3: Critical Bugs
Total
→ total critical bugs
Open
→ abhi tak fix nahi hue
Resolved
→ jo fix ho chuke hain

👉 Example:

Total: 6
Open: 4
Resolved: 2</p>
      </div>
    </Sidebar>
  );
}

export default CardCB;