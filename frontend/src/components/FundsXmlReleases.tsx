import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  listFundsXmlReleases,
  type FundsXmlRelease,
} from "../api/client";

interface FundsXmlReleasesProps {
  onSelect: (tagName: string, filename: string) => void;
  busy: boolean;
}

type ListState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; releases: FundsXmlRelease[] };

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}

export function FundsXmlReleases({ onSelect, busy }: FundsXmlReleasesProps) {
  const [state, setState] = useState<ListState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const response = await listFundsXmlReleases();
      setState({ kind: "ready", releases: response.releases });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleActivate = (tagName: string, filename: string) => {
    if (busy) return;
    onSelect(tagName, filename);
  };

  return (
    <div className="panel rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-3">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          XSD files published on the{" "}
          <a
            href="https://github.com/fundsxml/schema/releases"
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent hover:underline"
          >
            fundsxml/schema
          </a>{" "}
          GitHub repository. Click a row to load.
        </p>
        {state.kind === "ready" && (
          <button
            type="button"
            className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-200"
            onClick={() => void load()}
            disabled={busy}
          >
            Refresh
          </button>
        )}
      </div>

      {state.kind === "loading" && (
        <p className="text-sm text-slate-500 dark:text-slate-400 py-4">
          Loading releases…
        </p>
      )}

      {state.kind === "error" && (
        <div className="py-3">
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            Could not load releases: {state.message}
          </p>
          <button
            type="button"
            className="btn btn-primary mt-3"
            onClick={() => void load()}
          >
            Retry
          </button>
        </div>
      )}

      {state.kind === "ready" && state.releases.length === 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400 py-4">
          No XSD releases found.
        </p>
      )}

      {state.kind === "ready" && state.releases.length > 0 && (
        <div className="max-h-[60vh] overflow-y-auto">
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 bg-white dark:bg-slate-900">
              <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                <th className="py-1.5 pr-3 font-semibold">Version</th>
                <th className="py-1.5 pr-3 font-semibold">Published</th>
                <th className="py-1.5 pr-3 font-semibold">File</th>
                <th className="py-1.5 pr-3 font-semibold text-right">Size</th>
              </tr>
            </thead>
            <tbody>
              {state.releases.flatMap((release) =>
                release.assets.map((asset, assetIdx) => {
                  const isFirst = assetIdx === 0;
                  return (
                    <tr
                      key={`${release.tag_name}:${asset.filename}`}
                      className={
                        "border-b border-slate-100 dark:border-slate-900 " +
                        (busy
                          ? "opacity-60 cursor-wait "
                          : "hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer ")
                      }
                      role="button"
                      tabIndex={busy ? -1 : 0}
                      aria-disabled={busy}
                      onClick={() =>
                        handleActivate(release.tag_name, asset.filename)
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleActivate(release.tag_name, asset.filename);
                        }
                      }}
                    >
                      {isFirst ? (
                        <td
                          className="py-1.5 pr-3 font-mono align-top"
                          rowSpan={release.assets.length}
                        >
                          {release.tag_name}
                          {release.prerelease && (
                            <span className="ml-2 inline-block px-1.5 py-0.5 text-[10px] font-semibold uppercase rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                              pre-release
                            </span>
                          )}
                        </td>
                      ) : null}
                      {isFirst ? (
                        <td
                          className="py-1.5 pr-3 align-top text-slate-600 dark:text-slate-400"
                          rowSpan={release.assets.length}
                        >
                          {formatDate(release.published_at)}
                        </td>
                      ) : null}
                      <td className="py-1.5 pr-3 font-mono">{asset.filename}</td>
                      <td className="py-1.5 pr-3 text-right text-slate-600 dark:text-slate-400">
                        {formatBytes(asset.size)}
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
