"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { toast } from "sonner";

import { login } from "@/lib/api-client";

export function LoginClient() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      await login(username, password);
      setPassword("");
      router.replace("/dashboard");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form className="w-full max-w-sm space-y-4 rounded-md border border-zinc-200 bg-white p-6" onSubmit={(event) => void onSubmit(event)}>
        <div>
          <p className="text-sm font-semibold text-accent">Polymarket Bot</p>
          <h1 className="mt-1 text-2xl font-bold text-ink">Login</h1>
        </div>
        <label className="block text-sm font-medium text-zinc-700">
          Username or email
          <input className="input mt-1 w-full" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label className="block text-sm font-medium text-zinc-700">
          Password
          <input className="input mt-1 w-full" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        </label>
        <button className="btn-primary w-full justify-center" disabled={loading} type="submit">
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
