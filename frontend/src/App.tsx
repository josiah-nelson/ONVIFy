import { Activity, Camera, CircleAlert, Database, RefreshCw, Server } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, type GetResponse, readApiResponse } from "@/api/client";
import { Button } from "@/components/ui/button";

type Health = GetResponse<"/api/system/health">;
type CameraRow = GetResponse<"/api/cameras/">[number];
type DetectionEvent = GetResponse<"/api/detection/events">[number];

type DashboardState = {
  health: Health | null;
  cameras: CameraRow[];
  events: DetectionEvent[];
  error: string | null;
  loading: boolean;
};

const initialState: DashboardState = {
  health: null,
  cameras: [],
  events: [],
  error: null,
  loading: true
};

const REFRESH_INTERVAL_MS = 30_000;

function statusClass(status: string): string {
  if (status === "ok" || status === "online" || status === "healthy") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (status === "degraded" || status === "connecting") {
    return "bg-amber-100 text-amber-800";
  }
  return "bg-rose-100 text-rose-800";
}

function rejectionMessage(result: PromiseRejectedResult): string {
  return result.reason instanceof Error ? result.reason.message : "Request failed";
}

function cameraStreamType(camera: CameraRow): string {
  return camera.source_streams[0]?.stream_type ?? "unknown";
}

export default function App(): ReactElement {
  const refreshInFlight = useRef(false);
  const [state, setState] = useState<DashboardState>(initialState);

  const refresh = useCallback(async (): Promise<void> => {
    if (refreshInFlight.current) {
      return;
    }
    refreshInFlight.current = true;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const [healthResult, camerasResult, eventsResult] = await Promise.allSettled([
        readApiResponse(api.GET("/api/system/health"), "/api/system/health"),
        readApiResponse(api.GET("/api/cameras/"), "/api/cameras/"),
        readApiResponse(
          api.GET("/api/detection/events", { params: { query: { limit: 5 } } }),
          "/api/detection/events"
        )
      ]);
      const failed = [healthResult, camerasResult, eventsResult].filter(
        (result): result is PromiseRejectedResult => result.status === "rejected"
      );
      setState((current) => ({
        health: healthResult.status === "fulfilled" ? healthResult.value : current.health,
        cameras: camerasResult.status === "fulfilled" ? camerasResult.value : current.cameras,
        events: eventsResult.status === "fulfilled" ? eventsResult.value : current.events,
        error: failed.length > 0 ? failed.map(rejectionMessage).join(" | ") : null,
        loading: false
      }));
    } finally {
      refreshInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [refresh]);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">ONVIFy</h1>
            <p className="text-sm text-muted-foreground">Virtual camera operations</p>
          </div>
          <Button onClick={() => void refresh()} disabled={state.loading}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </header>

        {state.error ? (
          <section className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
            <CircleAlert className="h-4 w-4 shrink-0" />
            <span>{state.error}</span>
          </section>
        ) : null}

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Metric icon={Server} label="System" value={state.health?.status ?? "loading"} status={state.health?.status} />
          <Metric
            icon={Database}
            label="Database"
            value={state.health ? (state.health.database.connected ? "connected" : "offline") : "loading"}
            status={state.health ? (state.health.database.connected ? "healthy" : "unavailable") : undefined}
          />
          <Metric icon={Camera} label="Cameras" value={`${state.health?.cameras_online ?? 0}/${state.health?.cameras_total ?? 0}`} />
          <Metric icon={Activity} label="Consumers" value={String(state.health?.stream_consumers_active ?? 0)} />
          <Metric
            icon={Activity}
            label="Inference"
            value={state.health?.inference.health ?? "unknown"}
            status={state.health?.inference.health}
          />
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
          <div className="overflow-hidden rounded-md border border-border">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Cameras</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[38rem] text-sm">
                <thead className="bg-muted text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Name</th>
                    <th className="px-4 py-2 font-medium">Stream</th>
                    <th className="px-4 py-2 font-medium">AI</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {state.cameras.length > 0 ? (
                    state.cameras.map((camera) => (
                      <tr key={camera.id} className="border-t border-border">
                        <td className="px-4 py-3 font-medium">{camera.name}</td>
                        <td className="px-4 py-3 uppercase">{cameraStreamType(camera)}</td>
                        <td className="px-4 py-3">{camera.ai_enabled ? "Enabled" : "Off"}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-md px-2 py-1 text-xs font-medium ${statusClass(camera.status)}`}>{camera.status}</span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-4 py-6 text-muted-foreground" colSpan={4}>
                        No cameras configured.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="rounded-md border border-border">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Recent detections</h2>
            </div>
            <div className="divide-y divide-border">
              {state.events.length > 0 ? (
                state.events.map((event) => {
                  const first = event.detections[0];
                  const eventTime = event.timestamp ? new Date(event.timestamp).toLocaleString() : "Unknown time";
                  return (
                    <div key={event.id ?? `${event.camera_id}-${event.timestamp ?? "pending"}`} className="px-4 py-3 text-sm">
                      <div className="font-medium">{first?.object_class ?? "unknown"}</div>
                      <div className="text-muted-foreground">
                        {eventTime} · {event.backend}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="px-4 py-6 text-sm text-muted-foreground">No detection events yet.</div>
              )}
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

type MetricProps = {
  icon: typeof Server;
  label: string;
  status?: string;
  value: string;
};

function Metric({ icon: Icon, label, status, value }: MetricProps): ReactElement {
  const valueClass = status ? statusClass(status) : "bg-muted text-muted-foreground";

  return (
    <div className="rounded-md border border-border bg-white px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className="h-4 w-4 text-cyan-700" />
        <span>{label}</span>
      </div>
      <div className={`inline-flex rounded-md px-2 py-1 text-sm font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}
