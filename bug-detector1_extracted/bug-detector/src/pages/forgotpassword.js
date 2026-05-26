import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./forgotpassword.css";

function ForgotPassword() {
  const navigate = useNavigate();

  const [step, setStep] = useState(1);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");

  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [timer, setTimer] = useState(60);

  // ✅ HARD CODED (demo)
  const correctEmail = "admin@gmail.com";
  const correctPhone = "03001234567";
  const correctOTP = "123456";

  // TIMER
  useEffect(() => {
    if (step === 2 && timer > 0) {
      const t = setTimeout(() => setTimer(timer - 1), 1000);
      return () => clearTimeout(t);
    }
  }, [timer, step]);

  // SEND CODE
  const handleSend = () => {
    if (input === correctEmail || input === correctPhone) {
      setError("");
      setStep(2);
      setTimer(60);
    } else {
      setError("Please enter a valid email or phone number");
    }
  };

  // OTP INPUT
  const handleChange = (value, index) => {
    if (!/^\d?$/.test(value)) return;

    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);

    if (value && index < 5) {
      document.getElementById(`otp-${index + 1}`)?.focus();
    }

    setError(""); // remove error on typing
  };

  // VERIFY
  const verifyOtp = () => {
    if (otp.join("") === correctOTP) {
      setError("");
      setStep(3);
    } else {
      setError("Invalid verification code");
    }
  };

  // RESEND
  const resendCode = () => {
    setTimer(60);
    setOtp(["", "", "", "", "", ""]);
    setError("");
  };

  return (
    <div className="forgot-wrapper">

      {/* 🔹 BACK BUTTON TOP LEFT */}
      <div className="back-top" onClick={() => navigate("/")}>
        ← Back to Login
      </div>

      <div className="forgot-card">

        <h2>Reset Password</h2>

        {error && <div className="error-box">{error}</div>}

        {/* STEP 1 */}
        {step === 1 && (
          <>
            <p className="subtitle">Enter your email or phone</p>

            <input
              type="text"
              placeholder="Email or Phone"
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setError(""); // remove error when typing
              }}
            />

            <button onClick={handleSend}>Send Code</button>
          </>
        )}

        {/* STEP 2 */}
        {step === 2 && (
          <>
            <p className="subtitle">Enter 6-digit verification code</p>

            <div className="otp-box">
              {otp.map((digit, i) => (
                <input
                  key={i}
                  id={`otp-${i}`}
                  type="text"
                  maxLength="1"
                  value={digit}
                  onChange={(e) => handleChange(e.target.value, i)}
                />
              ))}
            </div>

            <button onClick={verifyOtp}>
              {timer > 0 ? "Verify Code" : "Resend Code"}
            </button>

            <div className="helper-text">
              {timer > 0 ? (
                <span>Resend code in {timer}s</span>
              ) : (
                <span className="resend" onClick={resendCode}>
                  Didn’t receive code? Click to resend
                </span>
              )}
            </div>
          </>
        )}

        {/* STEP 3 */}
        {step === 3 && (
          <>
            <div className="success">✔ Password Reset Successful</div>
            <button onClick={() => navigate("/")}>
              Go to Login
            </button>
          </>
        )}

      </div>
    </div>
  );
}

export default ForgotPassword;