import createClient from "openapi-fetch";

import type { paths } from "@/api/generated/schema";

export const api = createClient<paths>({ baseUrl: "" });

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
