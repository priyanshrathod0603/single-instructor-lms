import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usersApi } from "@/lib/api/users";
import { controlApi } from "@/lib/api/control";
import UserDirectoryPage from "@/app/(control)/control/users/page";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "user-123" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/control/users",
}));

describe("Super Admin User Management & Create User Page Tests", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  function renderWithQueryClient(ui: React.ReactElement) {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  }

  const mockUsers = [
    {
      id: "u1",
      email: "student@example.com",
      full_name: "Alice Student",
      phone: "+919876543210",
      avatar_url: null,
      is_verified: true,
      is_active: true,
      roles: ["STUDENT"],
      created_at: "2026-11-10T12:00:00Z",
    },
    {
      id: "u2",
      email: "staff@example.com",
      full_name: "Bob Staff",
      phone: "+14155552671",
      avatar_url: null,
      is_verified: true,
      is_active: true,
      roles: ["STAFF"],
      created_at: "2026-11-09T12:00:00Z",
    },
  ];

  const mockOverview = {
    user_metrics: {
      total_students: 45,
      total_admins: 3,
      total_staff: 5,
      total_super_admins: 1,
      active_users: 50,
    },
    course_metrics: { total_courses: 5, published_courses: 3, draft_courses: 1, archived_courses: 1 },
    enrollment_metrics: { total_enrollments: 120, active_enrollments: 110 },
    financial_metrics: {
      verified_revenue_paise: 5000000,
      verified_revenue_inr: 50000.0,
      successful_transactions: 10,
      refunded_amount_paise: 0,
      refunded_amount_inr: 0,
      net_revenue_paise: 5000000,
      net_revenue_inr: 50000.0,
      currency: "INR",
    },
    security_metrics: {
      total_audit_events: 250,
      security_events_count: 2,
      active_staff_count: 5,
      security_model: "RBAC",
    },
    registration_trends: [],
    enrollment_trends: [],
    recent_activity: [],
    generated_at: "2026-11-17T12:00:00Z",
  };

  it("renders User Management title, description, and Add New User button", async () => {
    vi.spyOn(usersApi, "listUsers").mockResolvedValue({
      items: mockUsers,
      total: 2,
      page: 1,
      per_page: 15,
      total_pages: 1,
    });
    vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverview);

    renderWithQueryClient(<UserDirectoryPage />);

    expect(screen.getByRole("heading", { name: "User Management" })).toBeInTheDocument();
    expect(screen.getByText("Create, manage and control platform user accounts.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add new user/i })).toBeInTheDocument();
  });

  it("renders summary metric cards: Total Users, Super Admin, Admin, Staff, Student", async () => {
    vi.spyOn(usersApi, "listUsers").mockResolvedValue({
      items: mockUsers,
      total: 2,
      page: 1,
      per_page: 15,
      total_pages: 1,
    });
    vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverview);

    renderWithQueryClient(<UserDirectoryPage />);

    await waitFor(() => {
      expect(screen.getByText("54")).toBeInTheDocument();
    });

    expect(screen.getByText("Total Users")).toBeInTheDocument();
    expect(screen.getByText("Super Admin")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getAllByText("Staff").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Student")).toBeInTheDocument();
  });

  it("renders table with required columns: Name, Email, Phone, Role, Status, Created At, Actions", async () => {
    vi.spyOn(usersApi, "listUsers").mockResolvedValue({
      items: mockUsers,
      total: 2,
      page: 1,
      per_page: 15,
      total_pages: 1,
    });
    vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverview);

    renderWithQueryClient(<UserDirectoryPage />);

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    });

    expect(screen.getByRole("columnheader", { name: "Email" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Phone" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Role" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Created At" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();

    expect(screen.getByText("Alice Student")).toBeInTheDocument();
    expect(screen.getByText("student@example.com")).toBeInTheDocument();
    expect(screen.getByText("+919876543210")).toBeInTheDocument();
    expect(screen.getByText("Bob Staff")).toBeInTheDocument();
    expect(screen.getByText("+14155552671")).toBeInTheDocument();
  });

  it("opens Create New User modal when clicking 'Add New User'", async () => {
    vi.spyOn(usersApi, "listUsers").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 15,
      total_pages: 0,
    });
    vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverview);

    renderWithQueryClient(<UserDirectoryPage />);

    const addButton = screen.getByRole("button", { name: /add new user/i });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Create New User" })).toBeInTheDocument();
      expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/phone number/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^password \*/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^confirm password \*/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/select role/i)).toBeInTheDocument();
    });
  });

  it("validates mandatory fields and password mismatch in Create User form", async () => {
    vi.spyOn(usersApi, "listUsers").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 15,
      total_pages: 0,
    });
    vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverview);

    renderWithQueryClient(<UserDirectoryPage />);

    fireEvent.click(screen.getByRole("button", { name: /add new user/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Create New User" })).toBeInTheDocument();
    });

    // Enter mismatching passwords
    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Test User" } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText(/phone number/i), { target: { value: "+919876543210" } });
    fireEvent.change(screen.getByLabelText(/^password \*/i), { target: { value: "StrongPass123!" } });
    fireEvent.change(screen.getByLabelText(/^confirm password \*/i), { target: { value: "DifferentPass123!" } });

    fireEvent.click(screen.getByRole("button", { name: /^create user$/i }));

    await waitFor(() => {
      expect(screen.getByText("Confirm Password must match Password")).toBeInTheDocument();
    });
  });

  it("submits valid form to usersApi.createUser and displays success feedback", async () => {
    vi.spyOn(usersApi, "listUsers").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 15,
      total_pages: 0,
    });
    vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverview);

    const createSpy = vi.spyOn(usersApi, "createUser").mockResolvedValue({
      id: "u-new",
      email: "newadmin@example.com",
      full_name: "New Administrator",
      phone: "+919876543210",
      avatar_url: null,
      is_verified: true,
      is_active: true,
      roles: ["ADMIN"],
      permissions: [],
      created_at: "2026-11-17T12:00:00Z",
      updated_at: "2026-11-17T12:00:00Z",
    });

    renderWithQueryClient(<UserDirectoryPage />);

    fireEvent.click(screen.getByRole("button", { name: /add new user/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Create New User" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "New Administrator" } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "newadmin@example.com" } });
    fireEvent.change(screen.getByLabelText(/phone number/i), { target: { value: "+919876543210" } });
    fireEvent.change(screen.getByLabelText(/^password \*/i), { target: { value: "AdminSecret123!" } });
    fireEvent.change(screen.getByLabelText(/^confirm password \*/i), { target: { value: "AdminSecret123!" } });
    fireEvent.change(screen.getByLabelText(/select role/i), { target: { value: "ADMIN" } });

    fireEvent.click(screen.getByRole("button", { name: /^create user$/i }));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({
        full_name: "New Administrator",
        email: "newadmin@example.com",
        phone: "+919876543210",
        password: "AdminSecret123!",
        role: "ADMIN",
      });
      expect(screen.getByText(/successfully created user new administrator/i)).toBeInTheDocument();
    });
  });
});
