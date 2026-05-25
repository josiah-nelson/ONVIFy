import createClient from "openapi-fetch";

import type { paths } from "@/api/generated/schema";

export const api = createClient<paths>({ baseUrl: "" });

export async function readApiResponse<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
  path: string
): Promise<T> {
  const { data, error, response } = await request;
  if (data !== undefined) {
    return data;
  }
  throw new Error(`${path} returned ${response.status}: ${apiErrorMessage(error)}`);
}

export async function ensureApiSuccess(
  request: Promise<{ error?: unknown; response: Response }>,
  path: string
): Promise<void> {
  const { error, response } = await request;
  if (response.ok) {
    return;
  }
  throw new Error(`${path} returned ${response.status}: ${apiErrorMessage(error)}`);
}

function apiErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return "Request failed";
}

export type GetResponse<Path extends keyof paths> = paths[Path] extends {
  get: {
    responses: {
      200: {
        content: {
          "application/json": infer ResponseBody;
        };
      };
    };
  };
}
  ? ResponseBody
  : never;
