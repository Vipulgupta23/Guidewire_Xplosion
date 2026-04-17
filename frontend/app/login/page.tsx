"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type Mode = "login" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const handleSubmit = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setError("Enter a valid email address");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }

    setLoading(true);
    setError("");
    setInfo("");

    try {
      if (mode === "login") {
        const res = await api<{
          access_token: string;
          worker: { id: string } | null;
          is_new: boolean;
        }>("/auth/login", {
          method: "POST",
          body: { email: normalizedEmail, password },
        });

        localStorage.setItem("access_token", res.access_token);
        if (res.worker) {
          localStorage.setItem("worker_id", res.worker.id);
          router.push("/dashboard");
        } else {
          localStorage.setItem("auth_email", normalizedEmail);
          router.push("/onboard");
        }
      } else {
        const res = await api<{
          access_token: string;
          worker: { id: string } | null;
          is_new: boolean;
          confirmation_required?: boolean;
        }>("/auth/signup", {
          method: "POST",
          body: { email: normalizedEmail, password },
        });

        if (res.confirmation_required) {
          setInfo("Account created! Please check your email to confirm, then log in.");
          setMode("login");
        } else {
          localStorage.setItem("access_token", res.access_token);
          if (res.worker) {
            localStorage.setItem("worker_id", res.worker.id);
            router.push("/dashboard");
          } else {
            localStorage.setItem("auth_email", normalizedEmail);
            router.push("/onboard");
          }
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    }

    setLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSubmit();
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      {/* Logo */}
      <div className="mb-10 text-center fade-in-up">
        <div className="w-20 h-20 bg-gradient-to-br from-amber-400 to-amber-600 rounded-2xl flex items-center justify-center mx-auto mb-4 glow-amber shadow-lg">
          <span className="text-3xl">💰</span>
        </div>
        <h1 className="text-3xl font-bold text-white">Incometrix AI</h1>
        <p className="text-slate-400 mt-1 text-sm">Predict. Protect. Pay.</p>
      </div>

      {/* Card */}
      <div className="glass-card w-full max-w-sm p-6" style={{ animationDelay: "0.1s" }}>
        <h2 className="text-lg font-semibold text-white mb-1">
          {mode === "login" ? "Welcome Back! 👋" : "Create Account 🚀"}
        </h2>
        <p className="text-slate-400 text-sm mb-6">
          {mode === "login"
            ? "Sign in with your email and password"
            : "Register a new account to get started"}
        </p>

        {/* Email */}
        <div className="mb-4">
          <input
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={handleKeyDown}
            className="input-field"
            autoFocus
            disabled={loading}
            id="email-input"
          />
        </div>

        {/* Password */}
        <div className="mb-4 relative">
          <input
            type={showPassword ? "text" : "password"}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={handleKeyDown}
            className="input-field pr-12"
            disabled={loading}
            id="password-input"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors text-sm"
            tabIndex={-1}
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
        {info && <p className="text-amber-300 text-sm mb-4">{info}</p>}

        <button
          onClick={handleSubmit}
          disabled={loading || !email.trim() || !password}
          className="btn-primary w-full flex items-center justify-center gap-2"
          id="auth-submit-btn"
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
          ) : mode === "login" ? (
            "Sign In"
          ) : (
            "Create Account"
          )}
        </button>

        <div className="mt-4 text-center">
          {mode === "login" ? (
            <p className="text-slate-400 text-sm">
              Don&apos;t have an account?{" "}
              <button
                onClick={() => {
                  setMode("signup");
                  setError("");
                  setInfo("");
                }}
                className="text-amber-400 hover:text-amber-300 font-medium transition-colors"
              >
                Sign up
              </button>
            </p>
          ) : (
            <p className="text-slate-400 text-sm">
              Already have an account?{" "}
              <button
                onClick={() => {
                  setMode("login");
                  setError("");
                  setInfo("");
                }}
                className="text-amber-400 hover:text-amber-300 font-medium transition-colors"
              >
                Sign in
              </button>
            </p>
          )}
        </div>

        <p className="text-slate-500 text-xs mt-4 text-center">
          By continuing, you agree to our Terms of Service
        </p>
      </div>
    </div>
  );
}
