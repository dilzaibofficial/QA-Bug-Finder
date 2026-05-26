import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { login } from "../api";
import "./login.css";

function Login() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) { setError("Please enter email and password"); return; }
    setLoading(true); setError("");
    try {
      const res = await login(email, password);
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
    <div className="login-container">

      <div className="left">
        <h1>AI Powered<br/>Bug Detection Platform</h1>
        <hr className="faded-line" />
        <p>Detect bugs faster using AI & Machine Learning</p>
      </div>

      <div className="right">
        <h2>Login to Your Account</h2>

        {error && <div className="error-box">{error}</div>}

        <div className="input-box">
          <label>Email</label>
          <input
            type="email"
            className={error ? "error-input" : ""}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
        </div>

        <div className="input-box">
          <label>Password</label>
          <div className="password-box">
            <input
              type={showPass ? "text" : "password"}
              className={error ? "error-input" : ""}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
            <span onClick={() => setShowPass(!showPass)}>
              {showPass ? <FaEyeSlash /> : <FaEye />}
            </span>
          </div>
        </div>

        <button onClick={handleLogin} disabled={loading}>
          {loading ? "Logging in..." : "Login"}
        </button>

        <p className="forgot" onClick={() => navigate("/forgot")}>
          Forgot Password?
        </p>

        <p className="signup-text">
          Don't have an account?{" "}
          <span onClick={() => navigate("/signup")}>Sign up</span>
        </p>

      </div>

    </div>
  );
}

export default Login;
