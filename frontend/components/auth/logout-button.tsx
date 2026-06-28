"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { logout } from "@/lib/api-client";

export function LogoutButton() {
  const router = useRouter();

  async function onLogout() {
    try {
      await logout();
      router.replace("/login");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Logout failed");
    }
  }

  return (
    <button className="mt-6 w-full rounded-md px-3 py-2 text-left text-sm font-medium text-zinc-700 hover:bg-zinc-100" onClick={() => void onLogout()}>
      Logout
    </button>
  );
}
