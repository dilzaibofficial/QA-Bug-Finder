import { BrowserRouter, Routes, Route } from "react-router-dom";

import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Dashboard from "./pages/Dashboard";
import Upload from "./pages/Upload";
import Reports from "./pages/Reports";
import History from "./pages/History";
import Settings from "./pages/Settings";
import ForgotPassword from "./pages/forgotpassword";
import CardTLU from "./pages/cardTLU";
import CardBD from "./pages/cardBD";
import CardCB from "./pages/cardCB";
import CardBSS from "./pages/cardBSS";

function App() {
  return (
    <BrowserRouter>
      <Routes>

        <Route path="/" element={<Login />} />
        <Route path="/signup" element={<Signup />} />

        {/* 👇 NEW ROUTE */}
        <Route path="/forgot" element={<ForgotPassword />} />

        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/history" element={<History />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/tlu" element={<CardTLU />} />
        <Route path="/bd" element={<CardBD />} />
        <Route path="/cb" element={<CardCB />} />
        <Route path="/bss" element={<CardBSS />} />

      </Routes>
    </BrowserRouter>
  );
}
export default App;