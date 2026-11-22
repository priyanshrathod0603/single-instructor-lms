"use client";

import React, { useState, useId } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Tag,
  Search,
  RotateCcw,
  Plus,
  Eye,
  Edit2,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  Archive,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  BookOpen,
  Copy,
  Check,
  Percent,
  Coins,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import {
  DiscountType,
  OfferCreatePayload,
  OfferItem,
  OfferStatus,
  OfferUpdatePayload,
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
  { label: "Newest First", sort_by: "created_at", sort_order: "desc" },
  { label: "Oldest First", sort_by: "created_at", sort_order: "asc" },
  { label: "Code (A-Z)", sort_by: "code", sort_order: "asc" },
  { label: "Code (Z-A)", sort_by: "code", sort_order: "desc" },
  { label: "Name (A-Z)", sort_by: "name", sort_order: "asc" },
];

export default function OffersGovernancePage() {
  const queryClient = useQueryClient();

  // Search, Filters & Pagination
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [discountTypeFilter, setDiscountTypeFilter] = useState("ALL");
  const [sortIndex, setSortIndex] = useState(0);
  const [page, setPage] = useState(1);
  const perPage = 10;

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [inspectOffer, setInspectOffer] = useState<OfferItem | null>(null);
  const [editOffer, setEditOffer] = useState<OfferItem | null>(null);
  const [deleteOffer, setDeleteOffer] = useState<OfferItem | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // Form states for Create / Edit
  const [formName, setFormName] = useState("");
  const [formCode, setFormCode] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formDiscountType, setFormDiscountType] = useState<DiscountType>("PERCENTAGE");
  const [formDiscountValue, setFormDiscountValue] = useState<string>("");
  const [formCourseId, setFormCourseId] = useState<string>("");
  const [formValidFrom, setFormValidFrom] = useState<string>("");
  const [formValidTo, setFormValidTo] = useState<string>("");
  const [formUsageLimit, setFormUsageLimit] = useState<string>("");
  const [formStatus, setFormStatus] = useState<OfferStatus>("ACTIVE");
  const [formError, setFormError] = useState<string | null>(null);

  const currentSort = SORT_OPTIONS[sortIndex];

  // Fetch courses for dropdown selection
  const { data: coursesData } = useQuery({
    queryKey: ["control-governed-courses-selector"],
    queryFn: () => controlApi.listGovernedCourses({ per_page: 100 }),
    staleTime: 60000,
  });

  // Fetch KPI Aggregate Metrics
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ["control-offers-metrics"],
    queryFn: () => controlApi.listOffers({ per_page: 100 }),
    staleTime: 30000,
  });

  const totalOffers = metricsData?.total ?? 0;
  const activeOffers = metricsData?.items.filter((o) => o.status === "ACTIVE").length ?? 0;
  const inactiveOffers = metricsData?.items.filter((o) => o.status === "INACTIVE").length ?? 0;
  const archivedOffers = metricsData?.items.filter((o) => o.status === "ARCHIVED").length ?? 0;

  // Fetch Paginated Offers Table Data
  const { data: offersData, isLoading: offersLoading } = useQuery({
    queryKey: [
      "control-offers-list",
      searchTerm,
      statusFilter,
      discountTypeFilter,
      currentSort.sort_by,
      currentSort.sort_order,
      page,
    ],
    queryFn: () =>
      controlApi.listOffers({
        search: searchTerm.trim() || undefined,
        status: statusFilter === "ALL" ? undefined : statusFilter,
        discount_type: discountTypeFilter === "ALL" ? undefined : discountTypeFilter,
        sort_by: currentSort.sort_by,
        sort_order: currentSort.sort_order as "asc" | "desc",
        page,
        per_page: perPage,
      }),
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (payload: OfferCreatePayload) => controlApi.createOffer(payload),
    onSuccess: () => {
      toast.success("Offer created successfully");
      setIsCreateOpen(false);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["control-offers-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-offers-metrics"] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error?.message || err.message || "Failed to create offer";
      setFormError(msg);
      toast.error(msg);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OfferUpdatePayload }) =>
      controlApi.updateOffer(id, payload),
    onSuccess: () => {
      toast.success("Offer updated successfully");
      setEditOffer(null);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["control-offers-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-offers-metrics"] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error?.message || err.message || "Failed to update offer";
      setFormError(msg);
      toast.error(msg);
    },
  });

  const toggleStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: OfferStatus }) =>
      controlApi.changeOfferStatus(id, status),
    onSuccess: (_, variables) => {
      toast.success(`Offer marked as ${variables.status}`);
      queryClient.invalidateQueries({ queryKey: ["control-offers-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-offers-metrics"] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error?.message || err.message || "Status update failed";
      toast.error(msg);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => controlApi.deleteOffer(id),
    onSuccess: () => {
      toast.success("Offer permanently deleted");
      setDeleteOffer(null);
      queryClient.invalidateQueries({ queryKey: ["control-offers-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-offers-metrics"] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error?.message || err.message || "Failed to delete offer";
      toast.error(msg);
    },
  });

  const resetForm = () => {
    setFormName("");
    setFormCode("");
    setFormDescription("");
    setFormDiscountType("PERCENTAGE");
    setFormDiscountValue("");
    setFormCourseId("");
    setFormValidFrom("");
    setFormValidTo("");
    setFormUsageLimit("");
    setFormStatus("ACTIVE");
    setFormError(null);
  };

  const openCreateModal = () => {
    resetForm();
    const now = new Date();
    const future = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    setFormValidFrom(now.toISOString().slice(0, 16));
    setFormValidTo(future.toISOString().slice(0, 16));
    setIsCreateOpen(true);
  };

  const openEditModal = (offer: OfferItem) => {
    resetForm();
    setEditOffer(offer);
    setFormName(offer.name);
    setFormCode(offer.code);
    setFormDescription(offer.description || "");
    setFormDiscountType(offer.discount_type);
    if (offer.discount_type === "PERCENTAGE") {
      setFormDiscountValue(offer.discount_value.toString());
    } else {
      // Convert paise to rupees for input
      setFormDiscountValue((offer.discount_value / 100).toString());
    }
    setFormCourseId(offer.course_id || "");
    setFormValidFrom(new Date(offer.valid_from).toISOString().slice(0, 16));
    setFormValidTo(new Date(offer.valid_to).toISOString().slice(0, 16));
    setFormUsageLimit(offer.usage_limit ? offer.usage_limit.toString() : "");
    setFormStatus(offer.status);
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const val = parseFloat(formDiscountValue);
    if (isNaN(val) || val <= 0) {
      setFormError("Please enter a valid positive discount amount");
      return;
    }

    let discountValuePaiseOrPercent: number;
    if (formDiscountType === "PERCENTAGE") {
      if (val < 1 || val > 100) {
        setFormError("Percentage discount must be between 1 and 100 percent");
        return;
      }
      discountValuePaiseOrPercent = Math.round(val);
    } else {
      // Rupees to paise
      discountValuePaiseOrPercent = Math.round(val * 100);
    }

    if (!formValidFrom || !formValidTo) {
      setFormError("Both start date and expiry date are required");
      return;
    }

    if (new Date(formValidTo) <= new Date(formValidFrom)) {
      setFormError("Expiry date must be strictly after the start date");
      return;
    }

    const payload: OfferCreatePayload = {
      name: formName.trim(),
      code: formCode.trim().toUpperCase(),
      description: formDescription.trim() || null,
      discount_type: formDiscountType,
      discount_value: discountValuePaiseOrPercent,
      course_id: formCourseId || null,
      valid_from: new Date(formValidFrom).toISOString(),
      valid_to: new Date(formValidTo).toISOString(),
      usage_limit: formUsageLimit ? parseInt(formUsageLimit, 10) : null,
      status: formStatus,
    };

    createMutation.mutate(payload);
  };

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editOffer) return;
    setFormError(null);

    const val = parseFloat(formDiscountValue);
    if (isNaN(val) || val <= 0) {
      setFormError("Please enter a valid positive discount amount");
      return;
    }

    let discountValuePaiseOrPercent: number;
    if (formDiscountType === "PERCENTAGE") {
      if (val < 1 || val > 100) {
        setFormError("Percentage discount must be between 1 and 100 percent");
        return;
      }
      discountValuePaiseOrPercent = Math.round(val);
    } else {
      discountValuePaiseOrPercent = Math.round(val * 100);
    }

    if (new Date(formValidTo) <= new Date(formValidFrom)) {
      setFormError("Expiry date must be strictly after the start date");
      return;
    }

    const payload: OfferUpdatePayload = {
      name: formName.trim(),
      description: formDescription.trim() || null,
      discount_type: formDiscountType,
      discount_value: discountValuePaiseOrPercent,
      course_id: formCourseId || null,
      valid_from: new Date(formValidFrom).toISOString(),
      valid_to: new Date(formValidTo).toISOString(),
      usage_limit: formUsageLimit ? parseInt(formUsageLimit, 10) : null,
      status: formStatus,
    };

    updateMutation.mutate({ id: editOffer.id, payload });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(text);
    toast.success(`Copied code "${text}"`);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const isOfferExpired = (validTo: string) => {
    return new Date(validTo) < new Date();
  };

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Offers & Discounts Management
            </h1>
            <Badge variant="outline" className="bg-primary-teal/10 text-primary-teal border-primary-teal/20 text-xs">
              Super Admin Exclusive
            </Badge>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Create and govern promotional coupons, course discount campaigns, and platform-wide pricing rules.
          </p>
        </div>

        <Button
          onClick={openCreateModal}
          className="bg-primary-teal hover:bg-primary-teal/90 text-white font-medium flex items-center gap-2 shadow-sm min-h-[44px]"
        >
          <Plus className="h-4 w-4" />
          Create New Offer
        </Button>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Offers</p>
            <Tag className="h-5 w-5 text-primary-teal" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-2">
            {metricsLoading ? "..." : totalOffers}
          </p>
          <p className="text-xs text-slate-400 mt-1">Configured promo campaigns</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Active Offers</p>
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          </div>
          <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-2">
            {metricsLoading ? "..." : activeOffers}
          </p>
          <p className="text-xs text-slate-400 mt-1">Redeemable by eligible students</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Inactive Offers</p>
            <Clock className="h-5 w-5 text-amber-500" />
          </div>
          <p className="text-2xl font-bold text-amber-600 dark:text-amber-400 mt-2">
            {metricsLoading ? "..." : inactiveOffers}
          </p>
          <p className="text-xs text-slate-400 mt-1">Paused campaigns</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Archived Offers</p>
            <Archive className="h-5 w-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-600 dark:text-slate-400 mt-2">
            {metricsLoading ? "..." : archivedOffers}
          </p>
          <p className="text-xs text-slate-400 mt-1">Expired or sunset</p>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xs flex flex-col md:flex-row gap-3 items-center justify-between">
        <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto flex-1">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[240px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setPage(1);
              }}
              placeholder="Search by code, title, or description..."
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
            aria-label="Filter by offer status"
          >
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">Active Only</option>
            <option value="INACTIVE">Inactive Only</option>
            <option value="ARCHIVED">Archived Only</option>
          </select>

          {/* Discount Type Filter */}
          <select
            value={discountTypeFilter}
            onChange={(e) => {
              setDiscountTypeFilter(e.target.value);
              setPage(1);
            }}
            className="h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100"
            aria-label="Filter by discount type"
          >
            <option value="ALL">All Discount Types</option>
            <option value="PERCENTAGE">Percentage (%)</option>
            <option value="FIXED">Fixed Amount (₹)</option>
          </select>

          {/* Sort Selector */}
          <select
            value={sortIndex}
            onChange={(e) => {
              setSortIndex(Number(e.target.value));
              setPage(1);
            }}
            className="h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100"
            aria-label="Sort offers"
          >
            {SORT_OPTIONS.map((opt, i) => (
              <option key={opt.label} value={i}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Reset Filters */}
        <Button
          variant="outline"
          onClick={() => {
            setSearchTerm("");
            setStatusFilter("ALL");
            setDiscountTypeFilter("ALL");
            setSortIndex(0);
            setPage(1);
          }}
          className="text-slate-600 dark:text-slate-300 h-10 w-full sm:w-auto"
        >
          <RotateCcw className="h-4 w-4 mr-2" />
          Reset
        </Button>
      </div>

      {/* Offers Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
        {offersLoading ? (
          <div className="flex flex-col items-center justify-center p-12 text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal mb-3" />
            <p className="text-sm">Loading offers directory...</p>
          </div>
        ) : offersData?.items && offersData.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/50 text-xs uppercase tracking-wider text-slate-500 font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="py-3.5 px-4">Coupon Code & Name</th>
                  <th className="py-3.5 px-4">Discount</th>
                  <th className="py-3.5 px-4">Course Scope</th>
                  <th className="py-3.5 px-4">Validity</th>
                  <th className="py-3.5 px-4">Redemptions</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {offersData.items.map((offer) => {
                  const expired = isOfferExpired(offer.valid_to);

                  return (
                    <tr
                      key={offer.id}
                      className="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors"
                    >
                      {/* Code & Name */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-slate-900 dark:text-white bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded text-xs border border-slate-300 dark:border-slate-700">
                            {offer.code}
                          </span>
                          <button
                            onClick={() => copyToClipboard(offer.code)}
                            title="Copy code"
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1"
                          >
                            {copiedCode === offer.code ? (
                              <Check className="h-3.5 w-3.5 text-emerald-500" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                        <p className="font-medium text-slate-900 dark:text-white mt-1">{offer.name}</p>
                        {offer.description && (
                          <p className="text-xs text-slate-400 truncate max-w-xs">{offer.description}</p>
                        )}
                      </td>

                      {/* Discount Value */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <div className="flex items-center gap-1.5 font-semibold text-slate-900 dark:text-white">
                          {offer.discount_type === "PERCENTAGE" ? (
                            <>
                              <Percent className="h-4 w-4 text-primary-teal" />
                              <span>{offer.discount_value}% OFF</span>
                            </>
                          ) : (
                            <>
                              <Coins className="h-4 w-4 text-amber-500" />
                              <span>{formatCurrency(offer.discount_value)} OFF</span>
                            </>
                          )}
                        </div>
                      </td>

                      {/* Course Scope */}
                      <td className="py-3.5 px-4">
                        {offer.course ? (
                          <div className="flex items-center gap-1.5 text-xs text-slate-700 dark:text-slate-300">
                            <BookOpen className="h-3.5 w-3.5 text-primary-teal shrink-0" />
                            <span className="truncate max-w-[180px] font-medium" title={offer.course.title}>
                              {offer.course.title}
                            </span>
                          </div>
                        ) : (
                          <Badge variant="outline" className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 text-xs">
                            Platform-wide
                          </Badge>
                        )}
                      </td>

                      {/* Validity */}
                      <td className="py-3.5 px-4 text-xs whitespace-nowrap">
                        <div>
                          <span className="text-slate-400">From: </span>
                          <span>{new Date(offer.valid_from).toLocaleDateString()}</span>
                        </div>
                        <div>
                          <span className="text-slate-400">To: </span>
                          <span className={expired ? "text-rose-500 font-semibold" : ""}>
                            {new Date(offer.valid_to).toLocaleDateString()}
                          </span>
                        </div>
                        {expired && (
                          <Badge variant="outline" className="mt-1 text-[10px] bg-rose-50 text-rose-600 border-rose-200">
                            Expired
                          </Badge>
                        )}
                      </td>

                      {/* Redemptions */}
                      <td className="py-3.5 px-4 whitespace-nowrap text-xs">
                        <span className="font-semibold text-slate-900 dark:text-white">{offer.times_used}</span>
                        <span className="text-slate-400">
                          {offer.usage_limit ? ` / ${offer.usage_limit}` : " (Unlimited)"}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {offer.status === "ACTIVE" ? (
                          <Badge variant="outline" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800">
                            Active
                          </Badge>
                        ) : offer.status === "INACTIVE" ? (
                          <Badge variant="outline" className="bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-800">
                            Inactive
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-300">
                            Archived
                          </Badge>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setInspectOffer(offer)}
                            className="p-1.5 text-slate-500 hover:text-primary-teal hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md transition-colors"
                            title="Inspect Offer Details"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => openEditModal(offer)}
                            className="p-1.5 text-slate-500 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/30 rounded-md transition-colors"
                            title="Edit Offer"
                          >
                            <Edit2 className="h-4 w-4" />
                          </button>

                          {/* Quick Toggle Status */}
                          {offer.status === "ACTIVE" ? (
                            <button
                              onClick={() => toggleStatusMutation.mutate({ id: offer.id, status: "INACTIVE" })}
                              className="p-1.5 text-slate-500 hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors"
                              title="Deactivate Offer"
                            >
                              <XCircle className="h-4 w-4 text-amber-500" />
                            </button>
                          ) : (
                            <button
                              onClick={() => toggleStatusMutation.mutate({ id: offer.id, status: "ACTIVE" })}
                              className="p-1.5 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 rounded-md transition-colors"
                              title="Activate Offer"
                            >
                              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                            </button>
                          )}

                          <button
                            onClick={() => setDeleteOffer(offer)}
                            className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 rounded-md transition-colors"
                            title="Delete Offer"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center text-slate-500">
            <Tag className="h-10 w-10 text-slate-400 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">No Offers Found</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              No promotional offers match the selected filters. Clear the search or create a new campaign offer.
            </p>
            <Button onClick={openCreateModal} variant="outline" className="mt-4 text-xs">
              <Plus className="h-3.5 w-3.5 mr-1" />
              Create First Offer
            </Button>
          </div>
        )}

        {/* Pagination Bar */}
        {offersData && offersData.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 text-xs text-slate-500">
            <span>
              Showing {((page - 1) * perPage) + 1} to {Math.min(page * perPage, offersData.total)} of {offersData.total} offers
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
                Page {page} of {offersData.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(offersData.pages, p + 1))}
                disabled={page >= offersData.pages}
                className="h-8 px-2"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* CREATE OFFER MODAL */}
      <Modal open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <ModalContent className="max-w-xl">
          <ModalHeader>
            <ModalTitle>Create Promotional Offer</ModalTitle>
            <ModalDescription>
              Configure a promotional discount code with custom scope and validity dates.
            </ModalDescription>
          </ModalHeader>

          <form onSubmit={handleCreateSubmit} className="space-y-4 py-2">
            {formError && (
              <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 rounded-md border border-rose-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{formError}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Offer Name *
                </label>
                <Input
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Diwali Flash Sale"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Coupon Code *
                </label>
                <Input
                  required
                  value={formCode}
                  onChange={(e) => setFormCode(e.target.value.toUpperCase())}
                  placeholder="e.g. DIWALI50"
                  className="font-mono uppercase"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Campaign Description (Optional)
              </label>
              <Input
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="Internal notes or marketing context"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Discount Type *
                </label>
                <select
                  value={formDiscountType}
                  onChange={(e) => setFormDiscountType(e.target.value as DiscountType)}
                  className="w-full h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                >
                  <option value="PERCENTAGE">Percentage (%)</option>
                  <option value="FIXED">Fixed Amount (₹ INR)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Discount Value * {formDiscountType === "PERCENTAGE" ? "(1 - 100 %)" : "(in ₹ Rupees)"}
                </label>
                <Input
                  required
                  type="number"
                  min="1"
                  step={formDiscountType === "PERCENTAGE" ? "1" : "0.01"}
                  max={formDiscountType === "PERCENTAGE" ? "100" : undefined}
                  value={formDiscountValue}
                  onChange={(e) => setFormDiscountValue(e.target.value)}
                  placeholder={formDiscountType === "PERCENTAGE" ? "e.g. 20" : "e.g. 500"}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Applicable Course Scope
              </label>
              <select
                value={formCourseId}
                onChange={(e) => setFormCourseId(e.target.value)}
                className="w-full h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
              >
                <option value="">Platform-wide (All Published Courses)</option>
                {coursesData?.items?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Valid From (Start Date) *
                </label>
                <Input
                  required
                  type="datetime-local"
                  value={formValidFrom}
                  onChange={(e) => setFormValidFrom(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Valid To (Expiry Date) *
                </label>
                <Input
                  required
                  type="datetime-local"
                  value={formValidTo}
                  onChange={(e) => setFormValidTo(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Usage Limit (Optional)
                </label>
                <Input
                  type="number"
                  min="1"
                  value={formUsageLimit}
                  onChange={(e) => setFormUsageLimit(e.target.value)}
                  placeholder="Leave empty for unlimited"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Initial Status
                </label>
                <select
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value as OfferStatus)}
                  className="w-full h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="INACTIVE">INACTIVE</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </div>
            </div>

            <ModalFooter className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800">
              <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending}
                className="bg-primary-teal hover:bg-primary-teal/90 text-white"
              >
                {createMutation.isPending ? "Creating..." : "Create Offer"}
              </Button>
            </ModalFooter>
          </form>
        </ModalContent>
      </Modal>

      {/* EDIT OFFER MODAL */}
      <Modal open={!!editOffer} onOpenChange={(open) => !open && setEditOffer(null)}>
        <ModalContent className="max-w-xl">
          <ModalHeader>
            <ModalTitle>Edit Promotional Offer</ModalTitle>
            <ModalDescription>
              Update discount rules, scope, or lifecycle status for code {editOffer?.code}.
            </ModalDescription>
          </ModalHeader>

          <form onSubmit={handleEditSubmit} className="space-y-4 py-2">
            {formError && (
              <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 rounded-md border border-rose-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{formError}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Offer Name *
                </label>
                <Input
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Coupon Code (Immutable)
                </label>
                <Input
                  disabled
                  value={editOffer?.code || ""}
                  className="font-mono bg-slate-100 dark:bg-slate-800 cursor-not-allowed"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Description
              </label>
              <Input
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Discount Type *
                </label>
                <select
                  value={formDiscountType}
                  onChange={(e) => setFormDiscountType(e.target.value as DiscountType)}
                  className="w-full h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                >
                  <option value="PERCENTAGE">Percentage (%)</option>
                  <option value="FIXED">Fixed Amount (₹ INR)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Discount Value * {formDiscountType === "PERCENTAGE" ? "(1 - 100 %)" : "(in ₹ Rupees)"}
                </label>
                <Input
                  required
                  type="number"
                  min="1"
                  step={formDiscountType === "PERCENTAGE" ? "1" : "0.01"}
                  max={formDiscountType === "PERCENTAGE" ? "100" : undefined}
                  value={formDiscountValue}
                  onChange={(e) => setFormDiscountValue(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Applicable Course Scope
              </label>
              <select
                value={formCourseId}
                onChange={(e) => setFormCourseId(e.target.value)}
                className="w-full h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
              >
                <option value="">Platform-wide (All Published Courses)</option>
                {coursesData?.items?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Valid From *
                </label>
                <Input
                  required
                  type="datetime-local"
                  value={formValidFrom}
                  onChange={(e) => setFormValidFrom(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Valid To *
                </label>
                <Input
                  required
                  type="datetime-local"
                  value={formValidTo}
                  onChange={(e) => setFormValidTo(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Usage Limit
                </label>
                <Input
                  type="number"
                  min="1"
                  value={formUsageLimit}
                  onChange={(e) => setFormUsageLimit(e.target.value)}
                  placeholder="Leave empty for unlimited"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Status
                </label>
                <select
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value as OfferStatus)}
                  className="w-full h-10 px-3 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="INACTIVE">INACTIVE</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </div>
            </div>

            <ModalFooter className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800">
              <Button type="button" variant="outline" onClick={() => setEditOffer(null)}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={updateMutation.isPending}
                className="bg-primary-teal hover:bg-primary-teal/90 text-white"
              >
                {updateMutation.isPending ? "Updating..." : "Save Changes"}
              </Button>
            </ModalFooter>
          </form>
        </ModalContent>
      </Modal>

      {/* INSPECT OFFER DETAILS MODAL */}
      <Modal open={!!inspectOffer} onOpenChange={(open) => !open && setInspectOffer(null)}>
        <ModalContent className="max-w-lg">
          <ModalHeader>
            <ModalTitle>Offer Inspection</ModalTitle>
            <ModalDescription>Comprehensive metadata for campaign {inspectOffer?.code}</ModalDescription>
          </ModalHeader>

          {inspectOffer && (
            <div className="space-y-4 py-2 text-sm">
              <div className="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-lg space-y-2 border border-slate-200 dark:border-slate-700">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Coupon Code</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-slate-900 dark:text-white bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded text-xs">
                      {inspectOffer.code}
                    </span>
                    <button
                      onClick={() => copyToClipboard(inspectOffer.code)}
                      className="text-slate-400 hover:text-slate-600"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Offer Title</span>
                  <span className="font-medium text-slate-900 dark:text-white">{inspectOffer.name}</span>
                </div>

                {inspectOffer.description && (
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400 font-semibold uppercase">Description</span>
                    <p className="text-xs text-slate-600 dark:text-slate-300">{inspectOffer.description}</p>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                  <p className="text-xs text-slate-400">Discount Amount</p>
                  <p className="text-base font-bold text-slate-900 dark:text-white mt-1">
                    {inspectOffer.discount_type === "PERCENTAGE"
                      ? `${inspectOffer.discount_value}%`
                      : formatCurrency(inspectOffer.discount_value)}
                  </p>
                </div>

                <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                  <p className="text-xs text-slate-400">Lifecycle Status</p>
                  <Badge variant="outline" className="mt-1">
                    {inspectOffer.status}
                  </Badge>
                </div>

                <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                  <p className="text-xs text-slate-400">Times Redeemed</p>
                  <p className="text-base font-bold text-slate-900 dark:text-white mt-1">
                    {inspectOffer.times_used}
                    {inspectOffer.usage_limit ? ` / ${inspectOffer.usage_limit}` : " (Unlimited)"}
                  </p>
                </div>

                <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                  <p className="text-xs text-slate-400">Course Scope</p>
                  <p className="text-xs font-semibold text-slate-900 dark:text-white mt-1 truncate">
                    {inspectOffer.course ? inspectOffer.course.title : "Platform-wide"}
                  </p>
                </div>
              </div>

              <div className="space-y-1 text-xs text-slate-500 border-t border-slate-200 dark:border-slate-700 pt-3">
                <div>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Valid Start: </span>
                  {new Date(inspectOffer.valid_from).toLocaleString()}
                </div>
                <div>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Valid Expiry: </span>
                  {new Date(inspectOffer.valid_to).toLocaleString()}
                </div>
                {inspectOffer.creator && (
                  <div>
                    <span className="font-semibold text-slate-700 dark:text-slate-300">Created By: </span>
                    {inspectOffer.creator.full_name} ({inspectOffer.creator.email})
                  </div>
                )}
                <div>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Created At: </span>
                  {new Date(inspectOffer.created_at).toLocaleString()}
                </div>
              </div>

              <ModalFooter>
                <Button variant="outline" onClick={() => setInspectOffer(null)}>
                  Close
                </Button>
                <Button
                  onClick={() => {
                    const o = inspectOffer;
                    setInspectOffer(null);
                    openEditModal(o);
                  }}
                  className="bg-primary-teal hover:bg-primary-teal/90 text-white"
                >
                  Edit Offer
                </Button>
              </ModalFooter>
            </div>
          )}
        </ModalContent>
      </Modal>

      {/* DELETE CONFIRMATION DIALOG */}
      <Modal open={!!deleteOffer} onOpenChange={(open) => !open && setDeleteOffer(null)}>
        <ModalContent className="max-w-md">
          <ModalHeader>
            <ModalTitle className="text-rose-600 flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Delete Offer Permanently
            </ModalTitle>
            <ModalDescription>
              Are you sure you want to permanently delete coupon{" "}
              <strong className="font-mono text-slate-900 dark:text-white">{deleteOffer?.code}</strong>?
              This action cannot be undone. All future redemption attempts will be rejected.
            </ModalDescription>
          </ModalHeader>

          <ModalFooter className="mt-4">
            <Button variant="outline" onClick={() => setDeleteOffer(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => deleteOffer && deleteMutation.mutate(deleteOffer.id)}
              disabled={deleteMutation.isPending}
              className="bg-rose-600 hover:bg-rose-700 text-white"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete Permanently"}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
