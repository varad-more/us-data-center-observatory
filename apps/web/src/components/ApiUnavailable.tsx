/**
 * Shown when the API cannot be reached.
 *
 * A blank page would leave a developer guessing, so this states exactly what
 * failed and gives the commands that fix the two most likely causes: the API
 * not running, or the database not yet populated.
 */
import { API_BASE } from "@/lib/api";

export function ApiUnavailable({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="stack">
      <h1>The Helios API is not responding</h1>
      <div className="notice">
        <strong>Details.</strong> <code>{message}</code>
        <br />
        Configured API base URL: <code>{API_BASE}</code>
      </div>
      <div className="card">
        <h2 className="card-title">Getting the observatory running</h2>
        <p className="small muted">Start the whole stack:</p>
        <div className="snippet">docker compose up --build</div>
        <p className="small muted" style={{ marginTop: "0.75rem" }}>
          Or, if you are running the backend directly, apply migrations and load real
          public records:
        </p>
        <div className="snippet">
          {[
            "alembic upgrade head",
            "helios bootstrap",
            "uvicorn helios_api.main:app --reload",
          ].join("\n")}
        </div>
      </div>
    </div>
  );
}
