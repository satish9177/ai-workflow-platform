import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import type { LoginResponse } from "../types/api";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await api.post<LoginResponse>("/api/v1/auth/login", { email, password });
      localStorage.setItem("token", response.data.access_token);
      navigate("/runs");
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <form className="card w-full max-w-md space-y-4" onSubmit={submit}>
        <div>
          <p className="text-sm uppercase tracking-wide text-slate-500">Internal Dashboard</p>
          <h1 className="mt-1 text-2xl font-semibold">Sign in</h1>
        </div>
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <label className="block space-y-1">
          <span className="text-sm font-medium">Email</span>
          <input className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Password</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <button className="btn-primary w-full" disabled={loading} type="submit">
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
