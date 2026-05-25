import {
  Activity,
  Camera,
  CircleAlert,
  Database,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Server,
  Trash2,
  X
} from "lucide-react";
import type { FormEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ensureApiSuccess, type GetResponse, readApiResponse } from "@/api/client";
import type { components } from "@/api/generated/schema";
import { Button } from "@/components/ui/button";

type Health = GetResponse<"/api/system/health">;
type CameraRow = GetResponse<"/api/cameras/">[number];
type DetectionEvent = GetResponse<"/api/detection/events">[number];
type CreateCameraRequest = components["schemas"]["CreateCameraRequest"];
type StreamType = components["schemas"]["StreamType"];
type UpdateCameraRequest = components["schemas"]["UpdateCameraRequest"];
type FormStreamType = StreamType | "unknown";

type DashboardState = {
  health: Health | null;
  cameras: CameraRow[];
  events: DetectionEvent[];
  error: string | null;
  loading: boolean;
};

type CameraFormState = {
  ai_enabled: boolean;
  ai_model: string;
  name: string;
  source_url: string;
  stream_type: FormStreamType;
};

type CameraFormStatus = {
  error: string | null;
  message: string | null;
  saving: boolean;
};

type DeleteStatus = {
  error: string | null;
  message: string | null;
  removingCameraId: string | null;
};

const initialState: DashboardState = {
  health: null,
  cameras: [],
  events: [],
  error: null,
  loading: true
};

const emptyCameraForm: CameraFormState = {
  ai_enabled: false,
  ai_model: "",
  name: "",
  source_url: "",
  stream_type: "rtsp"
};

const initialFormStatus: CameraFormStatus = {
  error: null,
  message: null,
  saving: false
};

const initialDeleteStatus: DeleteStatus = {
  error: null,
  message: null,
  removingCameraId: null
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
  return errorMessage(result.reason);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function cameraStreamType(camera: CameraRow): StreamType | "unknown" {
  return camera.source_streams[0]?.stream_type ?? "unknown";
}

function cameraSourceUrl(camera: CameraRow): string {
  return camera.source_streams[0]?.url ?? "";
}

function cameraToForm(camera: CameraRow): CameraFormState {
  const streamType = cameraStreamType(camera);
  return {
    ai_enabled: camera.ai_enabled,
    ai_model: camera.ai_model ?? "",
    name: camera.name,
    source_url: cameraSourceUrl(camera),
    stream_type: streamType
  };
}

function nullableText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export default function App(): ReactElement {
  const refreshInFlight = useRef(false);
  const refreshGeneration = useRef(0);
  const [state, setState] = useState<DashboardState>(initialState);
  const [cameraForm, setCameraForm] = useState<CameraFormState>(emptyCameraForm);
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null);
  const [formStatus, setFormStatus] = useState<CameraFormStatus>(initialFormStatus);
  const [deleteStatus, setDeleteStatus] = useState<DeleteStatus>(initialDeleteStatus);

  const refresh = useCallback(async (force = false): Promise<void> => {
    if (refreshInFlight.current && !force) {
      return;
    }
    if (!force) {
      refreshInFlight.current = true;
    }
    const requestGeneration = refreshGeneration.current;
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
      if (requestGeneration !== refreshGeneration.current) {
        return;
      }
      setState((current) => ({
        health: healthResult.status === "fulfilled" ? healthResult.value : current.health,
        cameras: camerasResult.status === "fulfilled" ? camerasResult.value : current.cameras,
        events: eventsResult.status === "fulfilled" ? eventsResult.value : current.events,
        error: failed.length > 0 ? failed.map(rejectionMessage).join(" | ") : null,
        loading: false
      }));
    } finally {
      if (!force) {
        refreshInFlight.current = false;
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const resetCameraForm = useCallback((): void => {
    setEditingCameraId(null);
    setCameraForm({ ...emptyCameraForm });
    setFormStatus((current) => ({ ...current, error: null, message: null }));
    setDeleteStatus({ ...initialDeleteStatus });
  }, []);

  const editCamera = (camera: CameraRow): void => {
    if (!camera.id) {
      return;
    }
    setEditingCameraId(camera.id);
    setCameraForm(cameraToForm(camera));
    setFormStatus((current) => ({ ...current, error: null, message: null }));
    setDeleteStatus({ ...initialDeleteStatus });
  };

  const submitCameraForm = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const name = cameraForm.name.trim();
    const sourceUrl = cameraForm.source_url.trim();
    if (!name || (!editingCameraId && !sourceUrl)) {
      setFormStatus((current) => ({
        ...current,
        error: editingCameraId ? "Name is required." : "Name and source URL are required.",
        message: null
      }));
      return;
    }

    setFormStatus((current) => ({ ...current, error: null, message: null, saving: true }));
    try {
      if (editingCameraId) {
        const body: UpdateCameraRequest = {
          ai_enabled: cameraForm.ai_enabled,
          ai_model: nullableText(cameraForm.ai_model),
          name
        };
        const updated = await readApiResponse(
          api.PATCH("/api/cameras/{camera_id}", {
            body,
            params: { path: { camera_id: editingCameraId } }
          }),
          "PATCH /api/cameras/{camera_id}"
        );
        refreshGeneration.current += 1;
        setCameraForm(cameraToForm(updated));
        setState((current) => ({
          ...current,
          cameras: current.cameras.map((camera) => (camera.id === updated.id ? updated : camera))
        }));
        setFormStatus((current) => ({ ...current, error: null, message: "Camera updated." }));
      } else {
        const body: CreateCameraRequest = {
          ai_enabled: cameraForm.ai_enabled,
          ai_model: nullableText(cameraForm.ai_model),
          name,
          source_url: sourceUrl,
          stream_type: cameraForm.stream_type === "unknown" ? "rtsp" : cameraForm.stream_type
        };
        const created = await readApiResponse(api.POST("/api/cameras/", { body }), "POST /api/cameras/");
        refreshGeneration.current += 1;
        setCameraForm({ ...emptyCameraForm });
        setState((current) => ({ ...current, cameras: [...current.cameras, created] }));
        setFormStatus((current) => ({ ...current, error: null, message: "Camera added." }));
      }
      void refresh(true);
    } catch (error) {
      setFormStatus((current) => ({ ...current, error: errorMessage(error), message: null }));
    } finally {
      setFormStatus((current) => ({ ...current, saving: false }));
    }
  };

  const deleteCamera = async (camera: CameraRow): Promise<void> => {
    if (!camera.id || !window.confirm(`Delete ${camera.name}?`)) {
      return;
    }
    setDeleteStatus({ error: null, message: null, removingCameraId: camera.id });
    try {
      await ensureApiSuccess(
        api.DELETE("/api/cameras/{camera_id}", { params: { path: { camera_id: camera.id } } }),
        "DELETE /api/cameras/{camera_id}"
      );
      refreshGeneration.current += 1;
      setState((current) => ({ ...current, cameras: current.cameras.filter((item) => item.id !== camera.id) }));
      if (editingCameraId === camera.id) {
        resetCameraForm();
      }
      setDeleteStatus({ error: null, message: "Camera deleted.", removingCameraId: null });
      void refresh(true);
    } catch (error) {
      setDeleteStatus({ error: errorMessage(error), message: null, removingCameraId: null });
    } finally {
      setDeleteStatus((current) => ({ ...current, removingCameraId: null }));
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">ONVIFy</h1>
            <p className="text-sm text-muted-foreground">Virtual camera operations</p>
          </div>
          <Button onClick={() => void refresh(true)} disabled={state.loading}>
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
          <div className="overflow-hidden rounded-md border border-border bg-white">
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Cameras</h2>
              <Button variant="outline" onClick={resetCameraForm} disabled={formStatus.saving || Boolean(deleteStatus.removingCameraId)}>
                <Plus className="h-4 w-4" />
                Add
              </Button>
            </div>
            {deleteStatus.error ? (
              <div className="flex items-center gap-2 border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">
                <CircleAlert className="h-4 w-4 shrink-0" />
                <span>{deleteStatus.error}</span>
              </div>
            ) : null}
            {deleteStatus.message ? (
              <div className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800">
                {deleteStatus.message}
              </div>
            ) : null}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-sm">
                <thead className="bg-muted text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Name</th>
                    <th className="px-4 py-2 font-medium">Source</th>
                    <th className="px-4 py-2 font-medium">AI</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {state.cameras.length > 0 ? (
                    state.cameras.map((camera) => (
                      <tr key={camera.id} className="border-t border-border">
                        <td className="px-4 py-3 font-medium">{camera.name}</td>
                        <td className="px-4 py-3">
                          <div className="flex min-w-0 max-w-[18rem] items-center gap-2">
                            <span className="shrink-0 rounded-md bg-muted px-2 py-1 text-xs font-medium uppercase">
                              {cameraStreamType(camera)}
                            </span>
                            <span className="min-w-0 truncate" title={cameraSourceUrl(camera)}>
                              {cameraSourceUrl(camera) || "No source"}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">{camera.ai_enabled ? "Enabled" : "Off"}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-md px-2 py-1 text-xs font-medium ${statusClass(camera.status)}`}>{camera.status}</span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="outline"
                              className="h-8 px-2"
                              onClick={() => editCamera(camera)}
                              disabled={!camera.id || formStatus.saving || Boolean(deleteStatus.removingCameraId)}
                              title="Edit camera"
                            >
                              <Pencil className="h-4 w-4" />
                              <span className="sr-only sm:not-sr-only">Edit</span>
                            </Button>
                            <Button
                              variant="outline"
                              className="h-8 px-2 text-rose-700 hover:bg-rose-50"
                              onClick={() => void deleteCamera(camera)}
                              disabled={!camera.id || formStatus.saving || Boolean(deleteStatus.removingCameraId)}
                              title="Delete camera"
                            >
                              <Trash2 className="h-4 w-4" />
                              <span className="sr-only sm:not-sr-only">Delete</span>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-4 py-6 text-muted-foreground" colSpan={5}>
                        No cameras configured.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="rounded-md border border-border bg-white">
            <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">{editingCameraId ? "Edit camera" : "Add camera"}</h2>
              {editingCameraId ? (
                <Button
                  variant="outline"
                  className="h-8 px-2"
                  onClick={resetCameraForm}
                  disabled={formStatus.saving || Boolean(deleteStatus.removingCameraId)}
                >
                  <X className="h-4 w-4" />
                  Cancel
                </Button>
              ) : null}
            </div>
            <form className="flex flex-col gap-4 p-4" onSubmit={(event) => void submitCameraForm(event)}>
              {formStatus.error ? (
                <div className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
                  <CircleAlert className="h-4 w-4 shrink-0" />
                  <span>{formStatus.error}</span>
                </div>
              ) : null}
              {formStatus.message ? (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  {formStatus.message}
                </div>
              ) : null}

              <label className="grid gap-1 text-sm font-medium">
                Name
                <input
                  className="h-10 rounded-md border border-border bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-cyan-500"
                  value={cameraForm.name}
                  onChange={(event) => setCameraForm((current) => ({ ...current, name: event.target.value }))}
                  required
                />
              </label>

              <label className="grid gap-1 text-sm font-medium">
                Source URL
                <input
                  className="h-10 rounded-md border border-border bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-cyan-500 disabled:bg-muted"
                  value={cameraForm.source_url}
                  onChange={(event) => setCameraForm((current) => ({ ...current, source_url: event.target.value }))}
                  disabled={Boolean(editingCameraId)}
                  required={!editingCameraId}
                />
              </label>

              <label className="grid gap-1 text-sm font-medium">
                Stream type
                <select
                  className="h-10 rounded-md border border-border bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-cyan-500 disabled:bg-muted"
                  value={cameraForm.stream_type}
                  onChange={(event) => setCameraForm((current) => ({ ...current, stream_type: event.target.value as FormStreamType }))}
                  disabled={Boolean(editingCameraId)}
                >
                  {cameraForm.stream_type === "unknown" ? (
                    <option value="unknown" disabled>
                      Unknown
                    </option>
                  ) : null}
                  <option value="rtsp">RTSP</option>
                  <option value="mjpeg">MJPEG</option>
                </select>
              </label>

              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  className="h-4 w-4 rounded border-border text-primary focus:ring-cyan-500"
                  type="checkbox"
                  checked={cameraForm.ai_enabled}
                  onChange={(event) => setCameraForm((current) => ({ ...current, ai_enabled: event.target.checked }))}
                />
                AI enabled
              </label>

              <label className="grid gap-1 text-sm font-medium">
                AI model
                <input
                  className="h-10 rounded-md border border-border bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-cyan-500"
                  value={cameraForm.ai_model}
                  onChange={(event) => setCameraForm((current) => ({ ...current, ai_model: event.target.value }))}
                />
              </label>

              <Button type="submit" disabled={formStatus.saving || Boolean(deleteStatus.removingCameraId)}>
                {editingCameraId ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                {editingCameraId ? "Save changes" : "Create camera"}
              </Button>
            </form>
          </aside>
        </section>

        <section className="rounded-md border border-border bg-white">
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
