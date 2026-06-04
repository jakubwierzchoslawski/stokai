"""
api.middleware.disclaimer_middleware — DisclaimerMiddleware for StokAI.

REQ-N-012 AC-003: Intercepts all JSON responses from the FastAPI application.
For any JSON object (at any nesting depth) that contains a 'sample_size' key
with an integer value strictly below the configured threshold, injects:
  "disclaimer": "<DISCLAIMER_TEXT>"
at the same level as 'sample_size'.

Only Content-Type: application/json responses are processed; all other
response types pass through unchanged.

Performance note: The middleware buffers the full response body before
re-streaming. To reduce overhead for large non-recommendation responses,
a path-prefix guard is applied: the middleware only buffers when the request
path matches one of DISCLAIMER_MIDDLEWARE_PATH_PREFIXES. All other paths
pass through immediately.

Email path disclaimer bypass risk (documented per plan):
  This middleware intercepts HTTP responses only. If the email dispatch path
  constructs alert content by reading ai_recommendation.rationale directly
  from the database (bypassing the FastAPI response layer), the disclaimer
  will not be injected automatically. The email alert template in src/alerts/
  must include an explicit:
    if recommendation.sample_size < threshold: inject disclaimer
  check. See PLAN-N-012 Risks and Notes for details.
"""
from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DISCLAIMER_FIELD = "disclaimer"


class DisclaimerMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware that injects disclaimer text into JSON
    responses where sample_size < threshold.

    Args:
        app: The ASGI application.
        threshold: Strict-less-than threshold for sample_size (default 5).
        disclaimer_text: The disclaimer string to inject.
        path_prefixes: Optional list of path prefixes to restrict processing
            to recommendation-bearing endpoints. Pass an empty list to apply
            to all JSON endpoints (test/dev only — has performance impact).
    """

    def __init__(
        self,
        app: Any,
        threshold: int,
        disclaimer_text: str,
        path_prefixes: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._threshold = threshold
        self._disclaimer_text = disclaimer_text
        # Default path prefixes guard recommendation-bearing endpoints.
        self._path_prefixes: list[str] = path_prefixes if path_prefixes is not None else [
            "/recommendation",
            "/alert",
            "/brief",
            "/analysis",
            "/compliance",
        ]

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """
        Intercept the response. Only modify application/json responses that
        match the configured path prefixes.
        """
        response = await call_next(request)

        # Path-prefix guard: skip buffering for paths that cannot contain
        # recommendations (performance optimisation).
        if self._path_prefixes:
            path = request.url.path
            if not any(path.startswith(prefix) for prefix in self._path_prefixes):
                return response

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response

        # Accumulate response body bytes.
        body_bytes = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body_bytes += chunk

        try:
            data = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Cannot parse — return original bytes unchanged.
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=content_type,
            )

        modified = self._inject_disclaimer(data, self._threshold, self._disclaimer_text)
        new_body = json.dumps(modified).encode("utf-8")

        # Rebuild response headers, updating Content-Length if present.
        headers = dict(response.headers)
        if "content-length" in headers:
            headers["content-length"] = str(len(new_body))

        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type=content_type,
        )

    def _inject_disclaimer(self, data: Any, threshold: int, text: str) -> Any:
        """
        Recursively walk JSON data and inject disclaimer where sample_size < threshold.

        Rules:
          - dict with 'sample_size' < threshold AND no existing 'disclaimer': add it.
          - dict without 'sample_size': recurse into values.
          - list: recurse into each element.
          - All other types: return unchanged.
        """
        if isinstance(data, dict):
            sample_size = data.get("sample_size")
            if (
                isinstance(sample_size, int)
                and sample_size < threshold
                and DISCLAIMER_FIELD not in data
            ):
                data = {**data, DISCLAIMER_FIELD: text}
            # Recurse into all values (including the newly added disclaimer key's
            # siblings to handle nested structures).
            return {key: self._inject_disclaimer(value, threshold, text) for key, value in data.items()}
        if isinstance(data, list):
            return [self._inject_disclaimer(item, threshold, text) for item in data]
        return data
