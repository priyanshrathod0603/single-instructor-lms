import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PaymentOverviewPage from "@/app/(control)/control/payments/page";
import { controlApi } from "@/lib/api/control";
import { PaymentMetrics, TransactionListResponse } from "@/types/commerce";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockMetrics: PaymentMetrics = {
  total_transactions_count: 15,
  successful_payments_count: 12,
  failed_payments_count: 3,
  pending_orders_count: 4,
  refunded_orders_count: 2,
  gross_revenue_paise: 6000000, // ₹60,000
  successful_collected_paise: 6000000,
  refunded_amount_paise: 1000000, // ₹10,000
  net_collected_paise: 5000000, // ₹50,000
  currency: "INR",
  generated_at: "2026-11-16T12:00:00Z",
};

const mockTxList: TransactionListResponse = {
  items: [
    {
      id: "tx-1",
      gateway: "RAZORPAY",
      razorpay_payment_id: "pay_test_123456",
      status: "SUCCESS",
      amount_inr: 500000, // ₹5,000
      currency: "INR",
      processed_at: "2026-11-16T10:30:00Z",
      order: {
        id: "order-1",
        order_no: "ORD-202611-0001",
        status: "PAID",
        amount_inr: 500000,
        currency: "INR",
      },
      student: {
        id: "student-1",
        email: "student@example.com",
        full_name: "Rahul Verma",
      },
      course: {
        id: "course-1",
        title: "FastAPI Masterclass",
        slug: "fastapi-masterclass",
      },
      refunds: [],
    },
    {
      id: "tx-2",
      gateway: "RAZORPAY",
      razorpay_payment_id: "pay_test_789012",
      status: "SUCCESS",
      amount_inr: 300000, // ₹3,000
      currency: "INR",
      processed_at: "2026-11-15T14:20:00Z",
      order: {
        id: "order-2",
        order_no: "ORD-202611-0002",
        status: "REFUNDED",
        amount_inr: 300000,
        currency: "INR",
      },
      student: {
        id: "student-2",
        email: "priya@example.com",
        full_name: "Priya Sharma",
      },
      course: {
        id: "course-2",
        title: "React 19 Deep Dive",
        slug: "react-19-deep-dive",
      },
      refunds: [
        {
          id: "ref-1",
          amount_inr: 300000,
          reason: "Course not relevant",
          status: "PROCESSED",
          razorpay_refund_id: "rfnd_test_001",
          processed_at: "2026-11-15T18:00:00Z",
        },
      ],
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
      <PaymentOverviewPage />
    </QueryClientProvider>
  );
}

describe("Payment Overview & Financial Surveillance Page (SA-05.2)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "getPaymentOverview").mockResolvedValue(mockMetrics);
    vi.spyOn(controlApi, "listTransactions").mockResolvedValue(mockTxList);
  });

  it("renders page header and financial KPI cards with formatted currencies", async () => {
    renderComponent();

    expect(
      screen.getByText("Payment Overview & Financial Surveillance")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Gross Revenue")).toBeInTheDocument();
      expect(screen.getByText("Net Collections")).toBeInTheDocument();
      expect(screen.getByText("Refunded")).toBeInTheDocument();
      expect(screen.getByText("Successful")).toBeInTheDocument();
      expect(screen.getByText("Pending")).toBeInTheDocument();
      expect(screen.getByText("Failed")).toBeInTheDocument();
    });
  });

  it("renders real-time transaction directory table", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("pay_test_123456")).toBeInTheDocument();
      expect(screen.getByText("ORD-202611-0001")).toBeInTheDocument();
      expect(screen.getByText("Rahul Verma")).toBeInTheDocument();
      expect(screen.getByText("FastAPI Masterclass")).toBeInTheDocument();

      expect(screen.getByText("pay_test_789012")).toBeInTheDocument();
      expect(screen.getByText("ORD-202611-0002")).toBeInTheDocument();
      expect(screen.getByText("Priya Sharma")).toBeInTheDocument();
      expect(screen.getByText("React 19 Deep Dive")).toBeInTheDocument();
    });
  });

  it("opens inspection modal on clicking Inspect button", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("pay_test_123456")).toBeInTheDocument();
    });

    const inspectBtns = screen.getAllByRole("button", { name: /inspect/i });
    fireEvent.click(inspectBtns[1]); // inspect tx-2 with refund

    await waitFor(() => {
      expect(screen.getByText("Transaction Surveillance Detail")).toBeInTheDocument();
      expect(screen.getByText("Complete gateway capture record and associated order/refund details.")).toBeInTheDocument();
      expect(screen.getByText("rfnd_test_001")).toBeInTheDocument();
      expect(screen.getByText("Reason: Course not relevant")).toBeInTheDocument();
    });
  });
});
