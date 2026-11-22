import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OffersGovernancePage from "@/app/(control)/control/offers/page";
import { controlApi } from "@/lib/api/control";
import { OfferListResponse } from "@/types/commerce";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockOffersList: OfferListResponse = {
  items: [
    {
      id: "offer-1",
      name: "Diwali Flash Sale",
      code: "DIWALI50",
      description: "50% off sitewide",
      discount_type: "PERCENTAGE",
      discount_value: 50,
      course_id: null,
      course: null,
      valid_from: "2026-11-01T00:00:00Z",
      valid_to: "2026-12-01T00:00:00Z",
      usage_limit: 100,
      times_used: 24,
      status: "ACTIVE",
      created_by_id: "user-sa-1",
      creator: {
        id: "user-sa-1",
        email: "superadmin@lms.local",
        full_name: "Super Admin",
      },
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
    {
      id: "offer-2",
      name: "Python Kickstart",
      code: "PYTHON500",
      description: "Flat ₹500 off on Python bootcamp",
      discount_type: "FIXED",
      discount_value: 50000, // 500 INR in paise
      course_id: "course-1",
      course: {
        id: "course-1",
        title: "Full-Stack Python Bootcamp",
        slug: "full-stack-python",
      },
      valid_from: "2026-11-10T00:00:00Z",
      valid_to: "2026-12-10T00:00:00Z",
      usage_limit: null,
      times_used: 5,
      status: "INACTIVE",
      created_by_id: "user-sa-1",
      creator: {
        id: "user-sa-1",
        email: "superadmin@lms.local",
        full_name: "Super Admin",
      },
      created_at: "2026-11-10T00:00:00Z",
      updated_at: "2026-11-10T00:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  per_page: 10,
  pages: 1,
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
      <OffersGovernancePage />
    </QueryClientProvider>
  );
}

describe("Offers & Discounts Governance Page (SA-05.1)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "listOffers").mockResolvedValue(mockOffersList);
    vi.spyOn(controlApi, "listGovernedCourses").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 100,
      pages: 1,
    });
  });

  it("renders page header, title, and KPI cards", async () => {
    renderComponent();

    expect(
      screen.getByText("Offers & Discounts Management")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Total Offers")).toBeInTheDocument();
      expect(screen.getByText("Active Offers")).toBeInTheDocument();
      expect(screen.getByText("Inactive Offers")).toBeInTheDocument();
      expect(screen.getByText("Archived Offers")).toBeInTheDocument();
    });
  });

  it("renders offers directory table with discount badges and codes", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("DIWALI50")).toBeInTheDocument();
      expect(screen.getByText("Diwali Flash Sale")).toBeInTheDocument();
      expect(screen.getByText("50% OFF")).toBeInTheDocument();

      expect(screen.getByText("PYTHON500")).toBeInTheDocument();
      expect(screen.getByText("Python Kickstart")).toBeInTheDocument();
      expect(screen.getByText("Full-Stack Python Bootcamp")).toBeInTheDocument();
    });

    // Check status badges
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("opens create offer modal when Create New Offer button is clicked", async () => {
    renderComponent();

    const createBtn = screen.getByRole("button", { name: /create new offer/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText("Create Promotional Offer")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("e.g. DIWALI50")).toBeInTheDocument();
    });
  });

  it("opens inspection modal on clicking inspect button", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("DIWALI50")).toBeInTheDocument();
    });

    const inspectBtns = screen.getAllByTitle("Inspect Offer Details");
    fireEvent.click(inspectBtns[0]);

    await waitFor(() => {
      expect(screen.getByText("Offer Inspection")).toBeInTheDocument();
      expect(screen.getByText("Comprehensive metadata for campaign DIWALI50")).toBeInTheDocument();
      expect(screen.getByText("Super Admin (superadmin@lms.local)")).toBeInTheDocument();
    });
  });

  it("opens edit modal on clicking edit action button", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("DIWALI50")).toBeInTheDocument();
    });

    const editBtns = screen.getAllByTitle("Edit Offer");
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      expect(screen.getByText("Edit Promotional Offer")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Diwali Flash Sale")).toBeInTheDocument();
    });
  });

  it("opens delete confirmation dialog on clicking delete button", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("DIWALI50")).toBeInTheDocument();
    });

    const deleteBtns = screen.getAllByTitle("Delete Offer");
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(screen.getByText("Delete Offer Permanently")).toBeInTheDocument();
      expect(screen.getByText(/Are you sure you want to permanently delete coupon/i)).toBeInTheDocument();
    });
  });
});
