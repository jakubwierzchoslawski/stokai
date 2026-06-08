#!/usr/bin/env node
/**
 * check-phase1-backend.mjs
 * Audit Phase 1 backend routes expected by the frontend.
 *
 * Usage: node scripts/check-phase1-backend.mjs [--base-url http://localhost:8000]
 *
 * Exits 0 if all checks pass, 1 if any fail.
 */

const BASE_URL = (() => {
  const idx = process.argv.indexOf("--base-url");
  return idx !== -1 ? process.argv[idx + 1] : "http://localhost:8000";
})();

const ENDPOINTS = [
  // Auth
  { method: "POST", path: "/api/v1/auth/login",    expectStatus: [200, 400, 422] },
  { method: "POST", path: "/api/v1/auth/register",  expectStatus: [200, 400, 422] },
  { method: "POST", path: "/api/v1/auth/logout",    expectStatus: [200, 401] },
  { method: "GET",  path: "/api/v1/auth/me",        expectStatus: [200, 401] },
  { method: "POST", path: "/api/v1/auth/refresh",   expectStatus: [200, 401] },

  // Health
  { method: "GET",  path: "/health",                expectStatus: [200] },

  // Briefs
  { method: "GET",  path: "/api/v1/briefs",         expectStatus: [200, 401] },

  // Intelligence Map / Events
  { method: "GET",  path: "/api/v1/events",         expectStatus: [200, 401] },

  // Screener
  { method: "GET",  path: "/api/v1/screener",       expectStatus: [200, 401] },

  // Q&A
  { method: "POST", path: "/api/v1/qa/sessions",    expectStatus: [200, 201, 401] },

  // Onboarding
  { method: "GET",  path: "/api/v1/onboarding/state", expectStatus: [200, 401] },

  // Admin — HIL
  { method: "GET",  path: "/api/v1/admin/hil/queue",   expectStatus: [200, 401, 403] },

  // Admin — Sources
  { method: "GET",  path: "/api/v1/admin/sources",     expectStatus: [200, 401, 403] },

  // Admin — AI Audit
  { method: "GET",  path: "/api/v1/admin/ai-audit/decisions", expectStatus: [200, 401, 403] },

  // Admin — System
  { method: "GET",  path: "/api/v1/admin/system/jobs",  expectStatus: [200, 401, 403] },
];

let passed = 0;
let failed = 0;

async function checkEndpoint({ method, path, expectStatus }) {
  const url = `${BASE_URL}${path}`;
  try {
    const res = await fetch(url, { method });
    if (expectStatus.includes(res.status)) {
      console.log(`  ✓ ${method} ${path} → ${res.status}`);
      passed++;
    } else {
      console.error(`  ✗ ${method} ${path} → ${res.status} (expected: ${expectStatus.join(",")})`);
      failed++;
    }
  } catch (err) {
    console.error(`  ✗ ${method} ${path} → CONNECTION FAILED: ${err.message}`);
    failed++;
  }
}

console.log(`\nPhase 1 Backend Audit — ${BASE_URL}\n`);

for (const ep of ENDPOINTS) {
  await checkEndpoint(ep);
}

console.log(`\n${passed}/${passed + failed} endpoints OK\n`);
process.exit(failed > 0 ? 1 : 0);
