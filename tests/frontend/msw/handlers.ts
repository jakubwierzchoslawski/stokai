import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/v1/ping", () =>
    HttpResponse.json({ data: { pong: true }, meta: { request_id: "r1" } }),
  ),
];
