"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CreditCard,
  Search,
  RotateCcw,
  Eye,
  CheckCircle2,
  XCircle,
  Clock,
  RotateCw,
  TrendingUp,
  ArrowDownLeft,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  Calendar,
  ShieldCheck,
  User,
  BookOpen,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import {
  TransactionItem,
} from "@/types/commerce";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
} from "@/components/ui/Modal";
import { formatCurrency } from "@/lib/utils";

const SORT_OPTIONS = [
  { label: "Newest Processed", sort_by: "processed_at", sort_order: "desc" },
  { label: "Oldest Processed", sort_by: "processed_at", sort_order: "asc" },
  { label: "Amount: High to Low", sort_by: "amount_inr", sort_order: "desc" },
  { label: "Amount: Low to High", sort_by: "amount_inr", sort_order: "asc" },
];

export default function PaymentOverviewPage() {
  // Search, Filters & Pagination
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [sortIndex, setSortIndex] = useState(0);
  const [page, setPage] = useState(1);
  const perPage = 10;

  // Inspection modal
  const [inspectTx, setInspectTx] = useState<TransactionItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const currentSort = SORT_OPTIONS[sortIndex];

  // 1. Fetch Commercial Overview Metrics
  const {
    data: metrics,
    isLoading: metricsLoading,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ["control-payment-overview-metrics"],
    queryFn: () => controlApi.getPaymentOverview(),
    staleTime: 30000,
  });

  // 2. Fetch Transactions List
  const {
    data: txData,
    isLoading: txLoading,
    refetch: refetchTx,
  } = useQuery({
    queryKey: [
      "control-payment-transactions",
      searchTerm,
      statusFilter,
      startDate,
      endDate,
      currentSort.sort_by,
      currentSort.sort_order,
      page,
    ],
    queryFn: () =>
      controlApi.listTransactions({
        search: searchTerm.trim() || undefined,
        status: statusFilter === "ALL" ? undefined : statusFilter,
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
        sort_by: currentSort.sort_by,
        sort_order: currentSort.sort_order as "asc" | "desc",
        page,
        per_page: perPage,
      }),
  });

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    toast.success(`Copied "${text}"`);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleResetFilters = () => {
    setSearchTerm("");
    setStatusFilter("ALL");
    setStartDate("");
    setEndDate("");
    setSortIndex(0);
    setPage(1);
  };

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Payment Overview & Financial Surveillance
            </h1>
            <Badge variant="outline" className="bg-primary-teal/10 text-primary-teal border-primary-teal/20 text-xs">
              Super Admin Exclusive
            </Badge>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Real-time commercial transaction surveillance, refund monitoring, and financial reconciliation.
          </p>
        </div>

        <Button
          variant="outline"
          onClick={() => {
            refetchMetrics();
            refetchTx();
            toast.success("Financial data refreshed");
          }}
          className="flex items-center gap-2 min-h-[44px]"
        >
          <RotateCw className="h-4 w-4" />
          Refresh Surveillance
        </Button>
      </div>

      {/* Financial KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {/* Gross Revenue */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Gross Revenue</p>
            <TrendingUp className="h-4 w-4 text-emerald-500" />
          </div>
          <p className="text-xl font-bold text-slate-900 dark:text-white mt-2">
            {metricsLoading ? "..." : formatCurrency(metrics?.gross_revenue_paise ?? 0)}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Total collected</p>
        </div>

        {/* Net Collections */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Net Collections</p>
            <ShieldCheck className="h-4 w-4 text-primary-teal" />
          </div>
          <p className="text-xl font-bold text-primary-teal mt-2">
            {metricsLoading ? "..." : formatCurrency(metrics?.net_collected_paise ?? 0)}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Gross minus refunds</p>
        </div>

        {/* Total Processed Refunds */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Refunded</p>
            <ArrowDownLeft className="h-4 w-4 text-rose-500" />
          </div>
          <p className="text-xl font-bold text-rose-600 dark:text-rose-400 mt-2">
            {metricsLoading ? "..." : formatCurrency(metrics?.refunded_amount_paise ?? 0)}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">
            {metrics?.refunded_orders_count ?? 0} refunded order(s)
          </p>
        </div>

        {/* Successful Payments */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Successful</p>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          </div>
          <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-2">
            {metricsLoading ? "..." : metrics?.successful_payments_count ?? 0}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Captured payments</p>
        </div>

        {/* Pending Orders */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pending</p>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          <p className="text-xl font-bold text-amber-600 dark:text-amber-400 mt-2">
            {metricsLoading ? "..." : metrics?.pending_orders_count ?? 0}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Awaiting checkout</p>
        </div>

        {/* Failed Transactions */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Failed</p>
            <XCircle className="h-4 w-4 text-slate-400" />
          </div>
          <p className="text-xl font-bold text-slate-700 dark:text-slate-300 mt-2">
            {metricsLoading ? "..." : metrics?.failed_payments_count ?? 0}
          </p>
          <p className="text-[11px] text-slate-400 mt-1">Gateway rejections</p>
        </div>
      </div>

      {/* Filters & Surveillance Controls */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs flex flex-col gap-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {/* Search Input */}
          <div className="relative lg:col-span-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setPage(1);
              }}
              placeholder="Search by Payment ID, Order No, Student, Course..."
              className="pl-9 h-10 w-full"
            />
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100"
            aria-label="Filter by transaction status"
          >
            <option value="ALL">All Statuses</option>
            <option value="SUCCESS">Success Only</option>
            <option value="FAILED">Failed Only</option>
          </select>

          {/* Start Date */}
          <div className="relative">
            <Input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
              className="h-10 w-full text-xs"
              title="Start Date Filter"
              aria-label="Start date filter"
            />
          </div>

          {/* End Date */}
          <div className="relative">
            <Input
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
              className="h-10 w-full text-xs"
              title="End Date Filter"
              aria-label="End date filter"
            />
          </div>
        </div>

        <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>Sort by:</span>
            <select
              value={sortIndex}
              onChange={(e) => {
                setSortIndex(Number(e.target.value));
                setPage(1);
              }}
              className="h-8 px-2 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs text-slate-900 dark:text-slate-100"
              aria-label="Sort transactions"
            >
              {SORT_OPTIONS.map((opt, i) => (
                <option key={opt.label} value={i}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleResetFilters}
            className="text-slate-600 dark:text-slate-300 h-8"
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            Reset Filters
          </Button>
        </div>
      </div>

      {/* Transactions Directory Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
        {txLoading ? (
          <div className="flex flex-col items-center justify-center p-12 text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal mb-3" />
            <p className="text-sm">Loading transactions directory...</p>
          </div>
        ) : txData?.items && txData.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/50 text-xs uppercase tracking-wider text-slate-500 font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="py-3.5 px-4">Payment ID & Gateway</th>
                  <th className="py-3.5 px-4">Order Reference</th>
                  <th className="py-3.5 px-4">Student</th>
                  <th className="py-3.5 px-4">Course</th>
                  <th className="py-3.5 px-4">Amount</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4">Processed Date</th>
                  <th className="py-3.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {txData.items.map((tx) => (
                  <tr
                    key={tx.id}
                    className="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    {/* Payment ID & Gateway */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs font-semibold text-slate-900 dark:text-white">
                          {tx.razorpay_payment_id}
                        </span>
                        <button
                          onClick={() => copyToClipboard(tx.razorpay_payment_id)}
                          title="Copy Payment ID"
                          className="text-slate-400 hover:text-slate-600"
                        >
                          {copiedId === tx.razorpay_payment_id ? (
                            <Check className="h-3.5 w-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                      <Badge variant="outline" className="text-[10px] mt-1 bg-slate-100 dark:bg-slate-800">
                        {tx.gateway}
                      </Badge>
                    </td>

                    {/* Order Reference */}
                    <td className="py-3.5 px-4">
                      {tx.order ? (
                        <div>
                          <p className="font-mono text-xs font-semibold text-slate-900 dark:text-white">
                            {tx.order.order_no}
                          </p>
                          <Badge
                            variant="outline"
                            className={`text-[10px] mt-0.5 ${
                              tx.order.status === "PAID"
                                ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                                : tx.order.status === "REFUNDED"
                                ? "text-rose-700 bg-rose-50 border-rose-200"
                                : "text-amber-700 bg-amber-50 border-amber-200"
                            }`}
                          >
                            {tx.order.status}
                          </Badge>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">N/A</span>
                      )}
                    </td>

                    {/* Student */}
                    <td className="py-3.5 px-4">
                      {tx.student ? (
                        <div>
                          <p className="font-medium text-slate-900 dark:text-white text-xs">
                            {tx.student.full_name}
                          </p>
                          <p className="text-[11px] text-slate-400 truncate max-w-[150px]">
                            {tx.student.email}
                          </p>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">Unknown Student</span>
                      )}
                    </td>

                    {/* Course */}
                    <td className="py-3.5 px-4">
                      {tx.course ? (
                        <p className="text-xs font-medium text-slate-900 dark:text-white truncate max-w-[160px]" title={tx.course.title}>
                          {tx.course.title}
                        </p>
                      ) : (
                        <span className="text-xs text-slate-400">N/A</span>
                      )}
                    </td>

                    {/* Amount */}
                    <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-white whitespace-nowrap">
                      {formatCurrency(tx.amount_inr)}
                    </td>

                    {/* Status */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {tx.status === "SUCCESS" ? (
                        <Badge variant="outline" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800">
                          SUCCESS
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 border-rose-200 dark:border-rose-800">
                          {tx.status}
                        </Badge>
                      )}
                    </td>

                    {/* Processed Date */}
                    <td className="py-3.5 px-4 text-xs whitespace-nowrap text-slate-500">
                      {new Date(tx.processed_at).toLocaleString()}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setInspectTx(tx)}
                        className="h-8 px-2 text-xs"
                      >
                        <Eye className="h-3.5 w-3.5 mr-1" />
                        Inspect
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center text-slate-500">
            <CreditCard className="h-10 w-10 text-slate-400 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">No Transactions Recorded</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              No transactions match the selected filters or no student course purchases have occurred yet.
            </p>
          </div>
        )}

        {/* Pagination */}
        {txData && txData.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 text-xs text-slate-500">
            <span>
              Showing {((page - 1) * perPage) + 1} to {Math.min(page * perPage, txData.total)} of {txData.total} transactions
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 px-2"
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>
              <span className="font-medium text-slate-700 dark:text-slate-300">
                Page {page} of {txData.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(txData.pages, p + 1))}
                disabled={page >= txData.pages}
                className="h-8 px-2"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* TRANSACTION INSPECTION MODAL */}
      <Modal open={!!inspectTx} onOpenChange={(open) => !open && setInspectTx(null)}>
        <ModalContent className="max-w-xl">
          <ModalHeader>
            <ModalTitle>Transaction Surveillance Detail</ModalTitle>
            <ModalDescription>
              Complete gateway capture record and associated order/refund details.
            </ModalDescription>
          </ModalHeader>

          {inspectTx && (
            <div className="space-y-4 py-2 text-sm">
              {/* Payment Summary Box */}
              <div className="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-lg space-y-2.5 border border-slate-200 dark:border-slate-700">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Gateway Payment ID</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-slate-900 dark:text-white bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded text-xs">
                      {inspectTx.razorpay_payment_id}
                    </span>
                    <button
                      onClick={() => copyToClipboard(inspectTx.razorpay_payment_id)}
                      className="text-slate-400 hover:text-slate-600"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Payment Gateway</span>
                  <span className="font-medium text-slate-900 dark:text-white">{inspectTx.gateway}</span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Capture Status</span>
                  <Badge variant="outline" className={inspectTx.status === "SUCCESS" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}>
                    {inspectTx.status}
                  </Badge>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Captured Amount</span>
                  <span className="text-base font-bold text-slate-900 dark:text-white">
                    {formatCurrency(inspectTx.amount_inr)}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Processed Timestamp</span>
                  <span className="text-xs text-slate-600 dark:text-slate-300">
                    {new Date(inspectTx.processed_at).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Order & Student Details */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 mb-1">
                    <User className="h-3.5 w-3.5 text-primary-teal" />
                    Student Details
                  </div>
                  {inspectTx.student ? (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white text-xs">{inspectTx.student.full_name}</p>
                      <p className="text-xs text-slate-400">{inspectTx.student.email}</p>
                      <p className="font-mono text-[10px] text-slate-400 mt-1 truncate">ID: {inspectTx.student.id}</p>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">No student metadata</p>
                  )}
                </div>

                <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 mb-1">
                    <BookOpen className="h-3.5 w-3.5 text-primary-teal" />
                    Enrolled Course
                  </div>
                  {inspectTx.course ? (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white text-xs">{inspectTx.course.title}</p>
                      <p className="font-mono text-[11px] text-slate-400 mt-0.5">slug: {inspectTx.course.slug}</p>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">No course attached</p>
                  )}
                </div>
              </div>

              {/* Associated Refund Records */}
              <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                    <ArrowDownLeft className="h-3.5 w-3.5 text-rose-500" />
                    Refund History ({inspectTx.refunds?.length ?? 0})
                  </div>
                </div>

                {inspectTx.refunds && inspectTx.refunds.length > 0 ? (
                  <div className="space-y-2 mt-2">
                    {inspectTx.refunds.map((ref) => (
                      <div
                        key={ref.id}
                        className="p-2.5 bg-slate-50 dark:bg-slate-850 rounded border border-slate-200 dark:border-slate-700 text-xs flex justify-between items-start"
                      >
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-slate-900 dark:text-white">
                              {formatCurrency(ref.amount_inr)}
                            </span>
                            <Badge variant="outline" className="text-[10px] bg-rose-50 text-rose-700">
                              {ref.status}
                            </Badge>
                          </div>
                          <p className="text-slate-500 mt-1">Reason: {ref.reason}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            Processed: {new Date(ref.processed_at).toLocaleString()}
                          </p>
                        </div>
                        {ref.razorpay_refund_id && (
                          <span className="font-mono text-[10px] text-slate-400">
                            {ref.razorpay_refund_id}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">No refunds requested or processed for this order.</p>
                )}
              </div>

              <ModalFooter>
                <Button variant="outline" onClick={() => setInspectTx(null)}>
                  Close
                </Button>
              </ModalFooter>
            </div>
          )}
        </ModalContent>
      </Modal>
    </div>
  );
}
