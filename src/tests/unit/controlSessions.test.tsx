import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SecuritySessionsPage from "@/app/(control)/control/sessions/page";
import { controlApi } from "@/lib/api/control";
import {
  DetailedSecurityMetricsData,
  SessionDetailResponse,
  SessionListResponse,
} from "@/types/control";

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

const mockMetrics: DetailedSecurityMetricsData = {
  active_sessions_total: 12,
  active_sessions_by_role: { STUDENT: 10, ADMIN: 1, SUPER_ADMIN: 1 },
  sessions_revoked_24h: 3,
  sessions_displaced_24h: 2,
  sessions_expired_24h: 1,
  failed_logins_24h: 5,
  rate_limit_breaches_24h: 0,
  suspended_accounts_total: 1,
  generated_at: "2026-11-16T12:00:00Z",
};

const mockSessionsList: SessionListResponse = {
  items: [
    {
      id: "sess-active-1",
      user_id: "u-alice",
      status: "ACTIVE",
      ip_address: "192.168.1.100",
      user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36",
      last_active_at: "2026-11-16T12:30:00Z",
      expires_at: "2026-11-23T12:30:00Z",
      created_at: "2026-11-16T10:00:00Z",
      user: {
        id: "u-alice",
        email: "alice@example.com",
        full_name: "Alice Walker",
        roles: ["STUDENT"],
        is_active: true,
      },
    },
    {
      id: "sess-revoked-2",
      user_id: "u-bob",
      status: "REVOKED",
      ip_address: "10.0.0.50",
      user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/122.0",
      last_active_at: "2026-11-16T11:00:00Z",
      expires_at: "2026-11-23T11:00:00Z",
      created_at: "2026-11-16T09:00:00Z",
      revoked_at: "2026-11-16T11:05:00Z",
      revoked_by: "u-superadmin",
      revocation_reason: "LOGIN_DISPLACEMENT",
      user: {
        id: "u-bob",
        email: "bob@example.com",
        full_name: "Bob Admin",
        roles: ["ADMIN"],
        is_active: true,
      },
    },
  ],
  total: 2,
  page: 1,
  per_page: 15,
  pages: 1,
};

const mockDetailResponse: SessionDetailResponse = {
  ...mockSessionsList.items[0],
  correlated_events: [
    {
      id: "audit-evt-1",
      actor_type: "STUDENT",
      actor_id: "u-alice",
      action: "AUTH_LOGIN",
      resource_type: "auth_session",
      resource_id: "sess-active-1",
      ip_address: "192.168.1.100",
      user_agent: "Mozilla/5.0 Chrome",
      metadata: { session_id: "sess-active-1" },
      created_at: "2026-11-16T10:00:00Z",
    },
  ],
};

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("SA-03: Security Governance & Session Surveillance UI Console", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "getSecurityMetrics").mockResolvedValue(mockMetrics);
    vi.spyOn(controlApi, "listSessions").mockResolvedValue(mockSessionsList);
    vi.spyOn(controlApi, "getSession").mockResolvedValue(mockDetailResponse);
    vi.spyOn(controlApi, "revokeSession").mockResolvedValue({
      ...mockDetailResponse,
      status: "REVOKED",
      revocation_reason: "Manual admin revocation",
    });
    vi.spyOn(controlApi, "revokeUserSessions").mockResolvedValue({
      user_id: "u-alice",
      revoked_sessions_count: 1,
      message: "Revoked 1 session(s)",
    });
    vi.spyOn(controlApi, "revokeOtherSessions").mockResolvedValue({
      revoked_sessions_count: 5,
      caller_session_id: "sess-caller",
      caller_session_preserved: true,
      message: "Emergency platform containment executed.",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders page header, security metrics cards, and session surveillance rows", async () => {
    renderWithClient(<SecuritySessionsPage />);

    // Header
    expect(screen.getByText("Security Governance & Session Surveillance")).toBeInTheDocument();
    expect(screen.getByText("Emergency Revocation")).toBeInTheDocument();

    // Metrics Cards
    await waitFor(() => {
      expect(screen.getByText("12")).toBeInTheDocument(); // active_sessions_total
      expect(screen.getByText("3")).toBeInTheDocument(); // sessions_revoked_24h
      expect(screen.getByText("2")).toBeInTheDocument(); // sessions_displaced_24h
    });

    // Session Table Rows
    await waitFor(() => {
      expect(screen.getByText("Alice Walker")).toBeInTheDocument();
      expect(screen.getByText("alice@example.com")).toBeInTheDocument();
      expect(screen.getByText("Bob Admin")).toBeInTheDocument();
      expect(screen.getByText("bob@example.com")).toBeInTheDocument();
    });

    // Status Badges
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();
    expect(screen.getByText("LOGIN_DISPLACEMENT")).toBeInTheDocument();
  });

  it("masks client IP address by default and toggles unmasked view on eyeball click", async () => {
    renderWithClient(<SecuritySessionsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Walker")).toBeInTheDocument();
    });

    // Alice's IP is 192.168.1.100 -> masked as 192.168.***.***
    expect(screen.getByText("192.168.***.***")).toBeInTheDocument();
    expect(screen.queryByText("192.168.1.100")).not.toBeInTheDocument();

    // Click the eyeball button for Alice's row
    const revealButtons = screen.getAllByTitle("Reveal full IP");
    expect(revealButtons.length).toBeGreaterThan(0);
    fireEvent.click(revealButtons[0]);

    // Now unmasked IP should be visible
    await waitFor(() => {
      expect(screen.getByText("192.168.1.100")).toBeInTheDocument();
    });

    // Eyeball toggle now says "Mask IP"
    const maskButton = screen.getByTitle("Mask IP");
    fireEvent.click(maskButton);

    await waitFor(() => {
      expect(screen.getByText("192.168.***.***")).toBeInTheDocument();
    });
  });

  it("handles targeted single-session revocation with min 5 characters validation", async () => {
    renderWithClient(<SecuritySessionsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Walker")).toBeInTheDocument();
    });

    // Click Revoke on Alice's active session
    const revokeButton = screen.getByRole("button", { name: "Revoke" });
    fireEvent.click(revokeButton);

    // Modal should open
    expect(screen.getByText("Revoke Authentication Session")).toBeInTheDocument();
    expect(screen.getByText("sess-active-1")).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: "Confirm Revocation" });
    // Should be disabled because justification is empty
    expect(confirmBtn).toBeDisabled();

    // Type fewer than 5 characters
    const reasonInput = screen.getByPlaceholderText(/Suspicious concurrent access/);
    fireEvent.change(reasonInput, { target: { value: "bad" } });
    expect(confirmBtn).toBeDisabled();
    expect(screen.getByText("Justification must be at least 5 characters long.")).toBeInTheDocument();

    // Type valid reason
    fireEvent.change(reasonInput, {
      target: { value: "Suspicious concurrent login detected" },
    });
    expect(confirmBtn).not.toBeDisabled();

    // Submit revocation
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(controlApi.revokeSession).toHaveBeenCalledWith("sess-active-1", {
        reason: "Suspicious concurrent login detected",
      });
    });
  });

  it("handles user-wide revocation modal with justification validation", async () => {
    renderWithClient(<SecuritySessionsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Walker")).toBeInTheDocument();
    });

    // Click UserX button on Alice's row
    const userRevokeButtons = screen.getAllByTitle("Revoke all active sessions for this user");
    fireEvent.click(userRevokeButtons[0]);

    // Modal opens
    expect(screen.getByText("Revoke All Sessions for User")).toBeInTheDocument();
    expect(screen.getByText(/Target user/)).toBeInTheDocument();

    const submitBtn = screen.getByRole("button", { name: "Revoke All Sessions" });
    expect(submitBtn).toBeDisabled();

    const input = screen.getByPlaceholderText(/suspected credential compromise/);
    fireEvent.change(input, { target: { value: "Account compromised by attacker" } });
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(controlApi.revokeUserSessions).toHaveBeenCalledWith("u-alice", {
        reason: "Account compromised by attacker",
      });
    });
  });

  it("handles emergency platform containment dialog requiring confirmation checkbox and justification", async () => {
    renderWithClient(<SecuritySessionsPage />);

    // Click Emergency Revocation header button
    const emergencyBtn = screen.getByRole("button", { name: /Emergency Revocation/ });
    fireEvent.click(emergencyBtn);

    // Modal opens
    expect(screen.getByText("Emergency Platform Containment")).toBeInTheDocument();
    expect(screen.getByText(/Caller Session Preservation/)).toBeInTheDocument();

    const submitBtn = screen.getByRole("button", { name: "Execute Platform Containment" });
    expect(submitBtn).toBeDisabled();

    // Fill in justification
    const input = screen.getByPlaceholderText(/Critical platform credential leakage/);
    fireEvent.change(input, {
      target: { value: "Platform-wide emergency incident containment active" },
    });
    // Still disabled without checkbox
    expect(submitBtn).toBeDisabled();

    // Check confirmation checkbox
    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect(submitBtn).not.toBeDisabled();

    // Submit
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(controlApi.revokeOtherSessions).toHaveBeenCalledWith({
        reason: "Platform-wide emergency incident containment active",
      });
    });
  });

  it("opens session inspection modal and displays metadata and correlated audit events", async () => {
    renderWithClient(<SecuritySessionsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Walker")).toBeInTheDocument();
    });

    // Click Inspect on Alice's row
    const inspectButtons = screen.getAllByRole("button", { name: "Inspect" });
    fireEvent.click(inspectButtons[0]);

    // Modal opens
    await waitFor(() => {
      expect(screen.getByText("Session Surveillance Inspection")).toBeInTheDocument();
      expect(screen.getByText("AUTH_LOGIN")).toBeInTheDocument();
    });
    expect(controlApi.getSession).toHaveBeenCalledWith("sess-active-1");
  });
});
