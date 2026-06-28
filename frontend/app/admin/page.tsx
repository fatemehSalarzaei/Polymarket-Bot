import Link from "next/link";

export default function AdminPage() {
  return (
    <main className="space-y-4 p-6">
      <section>
        <p className="text-sm font-semibold text-accent">Admin</p>
        <h1 className="text-2xl font-bold text-ink">User and data management</h1>
      </section>
      <div className="flex gap-3">
        <Link className="btn-primary" href="/admin/users">
          Users
        </Link>
        <Link className="btn-secondary" href="/admin/tables">
          Tables
        </Link>
      </div>
    </main>
  );
}
