import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * AddSourceModal tests â€” PLAN-F-028 TASK-008
 *
 * Tests cover:
 *   - Invalid credentials_ref rejected with validation message.
 *   - Invalid JSON in config field rejected with validation message.
 *   - display_name > 120 chars rejected.
 *   - Successful form submission calls POST and closes modal.
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// â”€â”€ Mocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderModal(isOpen = true, onClose = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const { AddSourceModal } = require("./AddSourceModal");
  return render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(AddSourceModal, { isOpen, onClose }),
    ),
  );
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText(/Display Name/i), {
    target: { name: "display_name", value: "My Source" },
  });
  fireEvent.change(screen.getByLabelText(/Credentials Ref/i), {
    target: { name: "credentials_ref", value: "env:MY_API_KEY" },
  });
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe("AddSourceModal", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.resetAllMocks();
  });

  it("rejects invalid credentials_ref format", () => {
    renderModal();

    fireEvent.change(screen.getByLabelText(/Display Name/i), {
      target: { name: "display_name", value: "Test" },
    });
    fireEvent.change(screen.getByLabelText(/Credentials Ref/i), {
      target: { name: "credentials_ref", value: "raw_api_key_123" },
    });

    fireEvent.click(screen.getByTestId("submit-btn"));

    expect(screen.getByText(/Must match/)).toBeTruthy();
  });

  it("rejects invalid JSON in config", () => {
    renderModal();

    fillValidForm();
    fireEvent.change(screen.getByLabelText(/Config/i), {
      target: { name: "config", value: "not json {{{" },
    });

    fireEvent.click(screen.getByTestId("submit-btn"));

    expect(screen.getByText(/valid JSON/)).toBeTruthy();
  });

  it("rejects display_name longer than 120 characters", () => {
    renderModal();

    fireEvent.change(screen.getByLabelText(/Display Name/i), {
      target: { name: "display_name", value: "A".repeat(121) },
    });
    fireEvent.change(screen.getByLabelText(/Credentials Ref/i), {
      target: { name: "credentials_ref", value: "env:MY_KEY" },
    });

    fireEvent.click(screen.getByTestId("submit-btn"));

    expect(screen.getByText(/120 characters/)).toBeTruthy();
  });

  it("submits valid form and closes modal on success", async () => {
    const onClose = vi.fn();
    (global as any).fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        data: {
          source_id: "new-src-001",
          display_name: "My Source",
          interface_type: "PriceProvider",
          enabled: false,
          config: {},
          cost_tier: "free",
          priority: 0,
          health: null,
        },
        error: null,
      }),
    });

    renderModal(true, onClose);

    fillValidForm();
    fireEvent.click(screen.getByTestId("submit-btn"));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });
});
