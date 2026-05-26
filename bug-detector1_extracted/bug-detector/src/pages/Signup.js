import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { signup } from "../api";
import "./signup.css";

function Signup() {
  const navigate = useNavigate();

  const [showPass, setShowPass] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSignup = async () => {
    if (!name || !email || !password) { setError("Please fill all fields"); return; }
    setLoading(true); setError("");
    try {
      const res = await signup(name, email, password);
      if (res.error) {
        setError(res.error);
      } else {
        localStorage.setItem("user_id", res.id);
        localStorage.setItem("user_name", res.name);
        localStorage.setItem("user_email", res.email);
        navigate("/dashboard");
      }
    } catch {
      setError("Server error. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signup-wrapper">

      <form className="signup-box" autoComplete="off">

        <div className="signup-left">
          <h1>Bug Detection AI</h1>
          <p>Join the platform and start detecting bugs using AI system.</p>
        </div>

        <div className="signup-right">

          <h2>Create Account</h2>

          {error && <div className="error-box" style={{ color: "red", marginBottom: 10 }}>{error}</div>}

          <input
            type="text"
            placeholder="Enter your name"
            value={name}
            autoComplete="off"
            onChange={(e) => setName(e.target.value)}
          />

          <input
            type="email"
            placeholder="Enter your email"
            value={email}
            autoComplete="off"
            onChange={(e) => setEmail(e.target.value)}
          />

          <div className="password-box">
            <input
              type={showPass ? "text" : "password"}
              placeholder="Enter your password"
              value={password}
              autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)}
            />
            <span onClick={() => setShowPass(!showPass)}>
              {showPass ? <FaEyeSlash /> : <FaEye />}
            </span>
          </div>

          <button type="button" onClick={handleSignup} disabled={loading}>
            {loading ? "Creating..." : "Create Account"}
          </button>

          <p className="social-text">
            Or continue with <span>Google</span> or <span>Gmail</span>
          </p>

          <p className="login-text">
            Already have an account?{" "}
            <span onClick={() => navigate("/")}>Login</span>
          </p>

        </div>

      </form>

    </div>
  );
}

export default Signup;
