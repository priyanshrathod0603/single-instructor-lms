import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PlatformSettingsPage from "@/app/(control)/control/settings/page";
import { controlApi } from "@/lib/api/control";
import { PublicPlatformInfo } from "@/types/commerce";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockSettings: PublicPlatformInfo = {
  platform_name: "Apex LMS",
  brand_name: "Apex Academy",
  brand_description: "Premier Engineering Academy",
  support_email: "support@apex.local",
  support_phone: "+91 99999 88888",
  logo_url: "https://apex.local/logo.png",
  frontend_url: "http://localhost:3000",
  cdn_stream_base_url: "https://video.apex.local",
  version: "v2.0.0",
  environment: "development",
  currency: "INR",
  email_provider: "CONSOLE",
  storage_provider: "LOCAL",
  updated_at: "2026-11-16T10:00:00Z",
};

function renderComponent() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <PlatformSettingsPage />
    </QueryClientProvider>
  );
}

describe("Platform Information & Settings Page (SA-05.3)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "getPlatformSettings").mockResolvedValue(mockSettings);
    vi.spyOn(controlApi, "updatePlatformSettings").mockResolvedValue(mockSettings);
  });

  it("renders platform settings header, master secret isolation notice, and values", async () => {
    renderComponent();

    expect(
      screen.getByText("Platform Information & Settings")
    ).toBeInTheDocument();

    // Master secret isolation guarantee notice
    expect(
      screen.getByText("Strict Master Secret Isolation")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Apex LMS")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Apex Academy")).toBeInTheDocument();
      expect(screen.getByDisplayValue("support@apex.local")).toBeInTheDocument();
      expect(screen.getByDisplayValue("+91 99999 88888")).toBeInTheDocument();
      expect(screen.getByDisplayValue("https://apex.local/logo.png")).toBeInTheDocument();

      // Read only runtime environment items
      expect(screen.getByText("v2.0.0")).toBeInTheDocument();
      expect(screen.getByText("DEVELOPMENT")).toBeInTheDocument();
      expect(screen.getByText("http://localhost:3000")).toBeInTheDocument();
      expect(screen.getByText("https://video.apex.local")).toBeInTheDocument();
    });
  });

  it("submits updated branding settings via API mutation", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Apex LMS")).toBeInTheDocument();
    });

    const platformInput = screen.getByDisplayValue("Apex LMS");
    fireEvent.change(platformInput, { target: { value: "Apex Elite LMS" } });

    const saveBtn = screen.getByRole("button", { name: /save platform settings/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(controlApi.updatePlatformSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          platform_name: "Apex Elite LMS",
          brand_name: "Apex Academy",
        })
      );
    });
  });
});
