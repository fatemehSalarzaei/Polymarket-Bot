import type { AuditLog } from "@/types/log";

export function LogsTable({ logs }: { logs: AuditLog[] }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-5">
      <h3 className="text-lg font-semibold">Audit Logs</h3>
      <div className="mt-4 overflow-auto rounded-md border border-zinc-200">
        <table className="w-full min-w-[860px] table-fixed text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Entity</th>
              <th className="px-3 py-2">After</th>
            </tr>
          </thead>
          <tbody>
            {logs.length ? (
              logs.map((log) => (
                <tr key={log.id} className="border-t border-zinc-100">
                  <td className="px-3 py-2">{new Date(log.created_at).toLocaleString()}</td>
                  <td className="px-3 py-2">{log.actor}</td>
                  <td className="px-3 py-2 font-semibold">{log.action}</td>
                  <td className="px-3 py-2">{log.entity_type}{log.entity_id ? ` #${log.entity_id}` : ""}</td>
                  <td className="truncate px-3 py-2 text-muted">{log.after ? JSON.stringify(log.after) : "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-5 text-muted" colSpan={5}>
                  No audit logs recorded
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

