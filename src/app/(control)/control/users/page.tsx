"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  Users,
  Search,
  Filter,
  ShieldCheck,
  ShieldAlert,
  UserCheck,
  UserX,
  UserPlus,
  AlertTriangle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Shield,
  CheckCircle2,
  XCircle,
  ArrowUpDown,
  Lock,
  UserCog,
  GraduationCap,
  Eye,
  EyeOff,
} from "lucide-react";
import { usersApi, UserListParams } from "@/lib/api/users";
import { controlApi } from "@/lib/api/control";
import { UserDirectoryItem } from "@/types/user";
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
import { PasswordStrengthMeter } from "@/components/auth/PasswordStrengthMeter";

const ROLE_TABS = [
  { label: "All Users", value: "" },
  { label: "Students", value: "STUDENT" },
  { label: "Staff", value: "STAFF" },
  { label: "Admins", value: "ADMIN" },
  { label: "Super Admins", value: "SUPER_ADMIN" },
];

const SORT_OPTIONS = [
  { label: "Newest First", sort_by: "created_at", sort_order: "desc" },
  { label: "Oldest First", sort_by: "created_at", sort_order: "asc" },
  { label: "Name (A-Z)", sort_by: "full_name", sort_order: "asc" },
  { label: "Name (Z-A)", sort_by: "full_name", sort_order: "desc" },
  { label: "Email (A-Z)", sort_by: "email", sort_order: "asc" },
];

const createUserSchema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(1, "Full name cannot be empty")
      .max(128, "Full name cannot exceed 128 characters"),
    email: z
      .string()
      .trim()
      .min(1, "Email address is required")
      .email("Please enter a valid email address")
      .max(255, "Email cannot exceed 255 characters"),
    phone: z
      .string()
      .trim()
      .min(1, "Phone number is required")
      .regex(
        /^\+?[0-9\s\-().]{7,20}$/,
        "Please enter a valid phone number (minimum 7 digits, digits and + - ( ) only)"
      )
      .max(32, "Phone number cannot exceed 32 characters"),
    password: z
      .string()
      .min(12, "Password must be at least 12 characters long")
      .max(128, "Password cannot exceed 128 characters")
      .regex(/[A-Z]/, "Password must contain at least one uppercase letter [A-Z]")
      .regex(/[a-z]/, "Password must contain at least one lowercase letter [a-z]")
      .regex(/[0-9]/, "Password must contain at least one numerical digit [0-9]")
      .regex(
        /[!@#$%^&*(),.?":{}|<>\-=_+[\]\\\/;~`']/,
        "Password must contain at least one special symbol"
      ),
    confirm_password: z.string().min(1, "Confirm password is required"),
    role: z.enum(["SUPER_ADMIN", "ADMIN", "STAFF", "STUDENT"], {
      errorMap: () => ({ message: "Role selection is mandatory" }),
    }),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Confirm Password must match Password",
    path: ["confirm_password"],
  });

type CreateUserFormData = z.infer<typeof createUserSchema>;

export default function UserDirectoryPage() {
  const queryClient = useQueryClient();

  // Search & Filter State
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [verificationFilter, setVerificationFilter] = useState<string>("ALL");
  const [sortIndex, setSortIndex] = useState(0);
  const [page, setPage] = useState(1);
  const perPage = 15;

  // Create User Modal State
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Selected user for existing role/status modal actions
  const [roleModalUser, setRoleModalUser] = useState<UserDirectoryItem | null>(null);
  const [targetRoleId, setTargetRoleId] = useState("STUDENT");
  const [roleAction, setRoleAction] = useState<"ASSIGN" | "REVOKE">("ASSIGN");
  const [roleError, setRoleError] = useState<string | null>(null);

  const [statusModalUser, setStatusModalUser] = useState<UserDirectoryItem | null>(null);
  const [statusReason, setStatusReason] = useState("");
  const [statusError, setStatusError] = useState<string | null>(null);

  const [feedbackMessage, setFeedbackMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // React Hook Form for Create User
  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateUserFormData>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      full_name: "",
      email: "",
      phone: "",
      password: "",
      confirm_password: "",
      role: "STUDENT",
    },
  });

  const watchPassword = watch("password");

  // Real-time Overview Query for Summary KPI Metrics
  const { data: overview, isLoading: isOverviewLoading } = useQuery({
    queryKey: ["control-overview"],
    queryFn: () => controlApi.getOverview(),
  });

  // Compute query parameters
  const currentSort = SORT_OPTIONS[sortIndex];
  const queryParams: UserListParams = {
    page,
    per_page: perPage,
    role: selectedRole || undefined,
    search: searchTerm.trim() || undefined,
    is_active: statusFilter === "ACTIVE" ? true : statusFilter === "SUSPENDED" ? false : undefined,
    is_verified: verificationFilter === "VERIFIED" ? true : verificationFilter === "UNVERIFIED" ? false : undefined,
    sort_by: currentSort.sort_by,
    sort_order: currentSort.sort_order,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["control-users-directory", queryParams],
    queryFn: () => usersApi.listUsers(queryParams),
  });

  // Create User Mutation
  const createUserMutation = useMutation({
    mutationFn: (formData: CreateUserFormData) => {
      return usersApi.createUser({
        full_name: formData.full_name.trim(),
        email: formData.email.trim(),
        phone: formData.phone.trim(),
        password: formData.password,
        role: formData.role,
      });
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-overview"] });
      reset();
      setCreateModalOpen(false);
      setCreateError(null);
      setFeedbackMessage({
        type: "success",
        text: `Successfully created user ${created.full_name} (${created.email}) with role '${created.roles.join(", ")}'.`,
      });
      setTimeout(() => setFeedbackMessage(null), 6000);
    },
    onError: (err: any) => {
      setCreateError(err?.message || "Failed to create user. Please review field values.");
    },
  });

  const onSubmitCreate = (formData: CreateUserFormData) => {
    setCreateError(null);
    createUserMutation.mutate(formData);
  };

  // Role Mutation
  const roleMutation = useMutation({
    mutationFn: () => {
      if (!roleModalUser) throw new Error("No user selected");
      return usersApi.manageRole(roleModalUser.id, {
        role_id: targetRoleId,
        action: roleAction,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-overview"] });
      setRoleModalUser(null);
      setRoleError(null);
      setFeedbackMessage({
        type: "success",
        text: `Successfully ${roleAction === "ASSIGN" ? "assigned" : "revoked"} role '${targetRoleId}' for ${updated.full_name}.`,
      });
      setTimeout(() => setFeedbackMessage(null), 5000);
    },
    onError: (err: any) => {
      setRoleError(err?.message || "Failed to update user role.");
    },
  });

  // Status Mutation
  const statusMutation = useMutation({
    mutationFn: () => {
      if (!statusModalUser) throw new Error("No user selected");
      return usersApi.updateStatus(statusModalUser.id, {
        is_active: !statusModalUser.is_active,
        reason: statusReason.trim() || undefined,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-overview"] });
      setStatusModalUser(null);
      setStatusReason("");
      setStatusError(null);
      setFeedbackMessage({
        type: "success",
        text: `Account for ${updated.full_name} is now ${updated.is_active ? "Active" : "Suspended"}.`,
      });
      setTimeout(() => setFeedbackMessage(null), 5000);
    },
    onError: (err: any) => {
      setStatusError(err?.message || "Failed to update account status.");
    },
  });

  const handleRoleTabClick = (role: string) => {
    setSelectedRole(role);
    setPage(1);
  };

  const getRoleBadgeVariant = (role: string): "error" | "warning" | "peach" | "outline" => {
    switch (role) {
      case "SUPER_ADMIN":
        return "error";
      case "ADMIN":
        return "warning";
      case "STAFF":
        return "peach";
      case "STUDENT":
      default:
        return "outline";
    }
  };

  // Compute User Counts from real backend data
  const totalUsers = overview?.user_metrics
    ? overview.user_metrics.total_super_admins +
      overview.user_metrics.total_admins +
      overview.user_metrics.total_staff +
      overview.user_metrics.total_students
    : data?.total ?? 0;
  const superAdminCount = overview?.user_metrics?.total_super_admins ?? 0;
  const adminCount = overview?.user_metrics?.total_admins ?? 0;
  const staffCount = overview?.user_metrics?.total_staff ?? 0;
  const studentCount = overview?.user_metrics?.total_students ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Users className="h-6 w-6 text-primary-teal" />
            User Management
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Create, manage and control platform user accounts.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setCreateError(null);
              reset();
              setCreateModalOpen(true);
            }}
            className="flex items-center gap-1.5 shadow-sm"
          >
            <UserPlus className="h-4 w-4" />
            Add New User
          </Button>
          <Link href="/control/admins">
            <Button variant="outline" size="sm">
              <ShieldCheck className="h-4 w-4 mr-1.5 text-amber-600" />
              Administrator Hub
            </Button>
          </Link>
          <Link href="/control/staff">
            <Button variant="outline" size="sm">
              <UserCheck className="h-4 w-4 mr-1.5 text-slate-600" />
              Invite Staff
            </Button>
          </Link>
        </div>
      </div>

      {/* Global Feedback Banner */}
      {feedbackMessage && (
        <div
          role="alert"
          className={`flex items-center gap-2 rounded-lg p-4 text-sm border ${
            feedbackMessage.type === "success"
              ? "bg-teal-50 text-teal-800 border-teal-200"
              : "bg-red-50 text-red-800 border-red-200"
          }`}
        >
          {feedbackMessage.type === "success" ? (
            <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-red-600 shrink-0" />
          )}
          <span>{feedbackMessage.text}</span>
        </div>
      )}

      {/* User Summary Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        {/* Total Users */}
        <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Users</span>
            <div className="h-8 w-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700">
              <Users className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold font-heading text-slate-900">
              {isOverviewLoading && !overview ? <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> : totalUsers}
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Platform total accounts</p>
          </div>
        </div>

        {/* Super Admins */}
        <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Super Admin</span>
            <div className="h-8 w-8 rounded-lg bg-rose-50 flex items-center justify-center text-rose-600">
              <ShieldAlert className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold font-heading text-slate-900">
              {isOverviewLoading && !overview ? <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> : superAdminCount}
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Platform owners</p>
          </div>
        </div>

        {/* Admins */}
        <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Admin</span>
            <div className="h-8 w-8 rounded-lg bg-amber-50 flex items-center justify-center text-amber-600">
              <ShieldCheck className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold font-heading text-slate-900">
              {isOverviewLoading && !overview ? <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> : adminCount}
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Operations managers</p>
          </div>
        </div>

        {/* Staff */}
        <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Staff</span>
            <div className="h-8 w-8 rounded-lg bg-purple-50 flex items-center justify-center text-purple-600">
              <UserCog className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold font-heading text-slate-900">
              {isOverviewLoading && !overview ? <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> : staffCount}
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Teaching & grading</p>
          </div>
        </div>

        {/* Students */}
        <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Student</span>
            <div className="h-8 w-8 rounded-lg bg-teal-50 flex items-center justify-center text-primary-teal">
              <GraduationCap className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold font-heading text-slate-900">
              {isOverviewLoading && !overview ? <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> : studentCount}
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Enrolled learners</p>
          </div>
        </div>
      </div>

      {/* Role Filter Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {ROLE_TABS.map((tab) => {
          const isActive = selectedRole === tab.value;
          return (
            <button
              key={tab.value}
              onClick={() => handleRoleTabClick(tab.value)}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-full transition-all ${
                isActive
                  ? "bg-slate-900 text-white shadow-sm"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Search, Filter & Sort Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm">
        {/* Search Bar */}
        <div className="relative">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <Input
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            placeholder="Search by name or email…"
            className="pl-9 text-xs"
          />
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="filter-status" className="text-xs font-medium text-slate-500 whitespace-nowrap">
            Status:
          </label>
          <select
            id="filter-status"
            aria-label="Filter users by account status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
          >
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">Active Only</option>
            <option value="SUSPENDED">Suspended Only</option>
          </select>
        </div>

        {/* Verification Filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="filter-verification" className="text-xs font-medium text-slate-500 whitespace-nowrap">
            Verified:
          </label>
          <select
            id="filter-verification"
            aria-label="Filter users by email verification"
            value={verificationFilter}
            onChange={(e) => {
              setVerificationFilter(e.target.value);
              setPage(1);
            }}
            className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
          >
            <option value="ALL">All Accounts</option>
            <option value="VERIFIED">Verified Only</option>
            <option value="UNVERIFIED">Unverified Only</option>
          </select>
        </div>

        {/* Sorting Dropdown */}
        <div className="flex items-center gap-2">
          <ArrowUpDown className="h-4 w-4 text-slate-400 shrink-0" />
          <select
            id="sort-users"
            aria-label="Sort users by column and order"
            value={sortIndex}
            onChange={(e) => {
              setSortIndex(Number(e.target.value));
              setPage(1);
            }}
            className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
          >
            {SORT_OPTIONS.map((opt, idx) => (
              <option key={opt.label} value={idx}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Directory Table with requested columns: Name, Email, Phone, Role, Status, Created At, Actions */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !data?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <Users className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No users match your criteria</p>
            <p className="text-xs text-slate-500">Try adjusting your filters, role tab, or search query.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Name</th>
                  <th scope="col" className="px-6 py-4">Email</th>
                  <th scope="col" className="px-6 py-4">Phone</th>
                  <th scope="col" className="px-6 py-4">Role</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Created At</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((user) => {
                  const isSuperAdmin = user.roles.includes("SUPER_ADMIN");
                  return (
                    <tr key={user.id} className="hover:bg-slate-50/80 transition-colors">
                      {/* Name */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center font-bold text-xs text-slate-700 shrink-0">
                            {user.full_name?.charAt(0)?.toUpperCase() || "U"}
                          </div>
                          <div className="min-w-0">
                            <div className="font-semibold text-slate-900 truncate flex items-center gap-1.5">
                              <span>{user.full_name}</span>
                              {isSuperAdmin && (
                                <span title="Protected Platform Owner">
                                  <Lock className="h-3.5 w-3.5 text-rose-600" />
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Email */}
                      <td className="px-6 py-4 text-xs font-mono text-slate-700">
                        {user.email}
                      </td>

                      {/* Phone */}
                      <td className="px-6 py-4 text-xs text-slate-600 whitespace-nowrap">
                        {user.phone || "—"}
                      </td>

                      {/* Role */}
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-1">
                          {user.roles.map((r) => (
                            <Badge key={r} variant={getRoleBadgeVariant(r)} className="text-[11px]">
                              {r}
                            </Badge>
                          ))}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <Badge variant={user.is_active ? "success" : "error"}>
                            {user.is_active ? "Active" : "Suspended"}
                          </Badge>
                          {user.is_verified ? (
                            <span className="inline-flex items-center gap-0.5 text-[11px] text-teal-700 font-medium" title="Email Verified">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Verified
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-0.5 text-[11px] text-amber-700 font-medium" title="Unverified Email">
                              <XCircle className="h-3.5 w-3.5" />
                              Unverified
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Created At */}
                      <td className="px-6 py-4 text-xs text-slate-500 whitespace-nowrap">
                        {new Date(user.created_at).toLocaleDateString()}
                      </td>

                      {/* Actions */}
                      <td className="px-6 py-4 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          <Link href={`/control/users/${user.id}`}>
                            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs">
                              <ExternalLink className="h-3.5 w-3.5 mr-1" />
                              Profile
                            </Button>
                          </Link>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 px-2 text-xs"
                            onClick={() => {
                              setRoleError(null);
                              setRoleModalUser(user);
                              setTargetRoleId(user.roles[0] || "STUDENT");
                              setRoleAction("ASSIGN");
                            }}
                          >
                            <Shield className="h-3.5 w-3.5 mr-1 text-slate-600" />
                            Role
                          </Button>
                          <Button
                            variant={user.is_active ? "outline" : "primary"}
                            size="sm"
                            className="h-8 px-2 text-xs"
                            onClick={() => {
                              setStatusError(null);
                              setStatusReason("");
                              setStatusModalUser(user);
                            }}
                          >
                            {user.is_active ? (
                              <UserX className="h-3.5 w-3.5 mr-1 text-red-500" />
                            ) : (
                              <UserCheck className="h-3.5 w-3.5 mr-1 text-teal-600" />
                            )}
                            {user.is_active ? "Suspend" : "Activate"}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3 bg-slate-50">
            <div className="text-xs text-slate-500">
              Showing page <span className="font-semibold text-slate-700">{data.page}</span> of{" "}
              <span className="font-semibold text-slate-700">{data.total_pages}</span> ({data.total} total users)
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="h-8 px-2 text-xs"
              >
                <ChevronLeft className="h-4 w-4 mr-0.5" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                className="h-8 px-2 text-xs"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-0.5" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* CREATE NEW USER MODAL */}
      {createModalOpen && (
        <Modal open={true} onOpenChange={(open) => !open && setCreateModalOpen(false)}>
          <ModalContent className="max-w-lg">
            <ModalHeader>
              <ModalTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-primary-teal" />
                Create New User
              </ModalTitle>
              <ModalDescription>
                Provision a new user account with personal details, login credentials, and assigned role.
              </ModalDescription>
            </ModalHeader>

            {createError && (
              <div className="rounded-lg bg-red-50 p-3.5 text-xs text-red-800 border border-red-200 flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600 mt-0.5" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmitCreate)} className="space-y-4 text-xs">
              {/* Personal Information Group */}
              <div className="space-y-3 border-b border-slate-100 pb-3.5">
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                  Personal Information
                </h3>

                {/* Full Name */}
                <div className="space-y-1">
                  <label htmlFor="create-full-name" className="font-semibold text-slate-700">
                    Full Name <span className="text-red-500">*</span>
                  </label>
                  <Input
                    id="create-full-name"
                    {...register("full_name")}
                    placeholder="e.g. Jane Doe"
                    className="text-xs h-9"
                    error={errors.full_name?.message}
                  />
                </div>

                {/* Email Address */}
                <div className="space-y-1">
                  <label htmlFor="create-email" className="font-semibold text-slate-700">
                    Email Address <span className="text-red-500">*</span>
                  </label>
                  <Input
                    id="create-email"
                    type="email"
                    {...register("email")}
                    placeholder="e.g. jane.doe@example.com"
                    className="text-xs h-9"
                    error={errors.email?.message}
                  />
                </div>

                {/* Phone Number */}
                <div className="space-y-1">
                  <label htmlFor="create-phone" className="font-semibold text-slate-700">
                    Phone Number <span className="text-red-500">*</span>
                  </label>
                  <Input
                    id="create-phone"
                    type="tel"
                    {...register("phone")}
                    placeholder="e.g. +91 98765 43210"
                    className="text-xs h-9"
                    error={errors.phone?.message}
                  />
                </div>
              </div>

              {/* Account Credentials Group */}
              <div className="space-y-3 border-b border-slate-100 pb-3.5">
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                  Account Credentials
                </h3>

                {/* Password */}
                <div className="space-y-1">
                  <label htmlFor="create-password" className="font-semibold text-slate-700">
                    Password <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <Input
                      id="create-password"
                      type={showPassword ? "text" : "password"}
                      {...register("password")}
                      placeholder="Min 12 characters, mixed case, numbers & symbols"
                      className="text-xs h-9 pr-9"
                      error={errors.password?.message}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label="Toggle password visibility"
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <PasswordStrengthMeter password={watchPassword} className="mt-1" />
                </div>

                {/* Confirm Password */}
                <div className="space-y-1">
                  <label htmlFor="create-confirm-password" className="font-semibold text-slate-700">
                    Confirm Password <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <Input
                      id="create-confirm-password"
                      type={showConfirmPassword ? "text" : "password"}
                      {...register("confirm_password")}
                      placeholder="Re-enter password identically"
                      className="text-xs h-9 pr-9"
                      error={errors.confirm_password?.message}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      aria-label="Toggle confirm password visibility"
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Role Assignment Group */}
              <div className="space-y-2">
                <h3 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                  Role Assignment
                </h3>
                <label htmlFor="create-role" className="font-semibold text-slate-700">
                  Select Role <span className="text-red-500">*</span>
                </label>
                <select
                  id="create-role"
                  {...register("role")}
                  className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                >
                  <option value="STUDENT">STUDENT — Enrolled Learner</option>
                  <option value="STAFF">STAFF — Teaching Assistant / Grader</option>
                  <option value="ADMIN">ADMIN — Operations Administrator</option>
                  <option value="SUPER_ADMIN">SUPER_ADMIN — Platform Owner</option>
                </select>
                {errors.role && (
                  <p className="text-red-600 text-[11px] mt-0.5">{errors.role.message}</p>
                )}
              </div>

              <ModalFooter className="pt-4 border-t border-slate-100">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setCreateModalOpen(false)}
                  disabled={createUserMutation.isPending || isSubmitting}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={createUserMutation.isPending || isSubmitting}
                  className="min-w-[120px]"
                >
                  {(createUserMutation.isPending || isSubmitting) && (
                    <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  )}
                  Create User
                </Button>
              </ModalFooter>
            </form>
          </ModalContent>
        </Modal>
      )}

      {/* Role Management Modal (Existing) */}
      {roleModalUser && (
        <Modal open={true} onOpenChange={(open) => !open && setRoleModalUser(null)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>Manage Roles: {roleModalUser.full_name}</ModalTitle>
              <ModalDescription>
                Assign or revoke authoritative system roles. Changes take effect on next token/session refresh.
              </ModalDescription>
            </ModalHeader>

            {roleError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{roleError}</span>
              </div>
            )}

            <div className="space-y-4 text-xs">
              <div>
                <span className="font-semibold text-slate-700">Currently Assigned Roles:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {roleModalUser.roles.map((r) => (
                    <Badge key={r} variant={getRoleBadgeVariant(r)}>
                      {r}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor="target-role-select" className="font-semibold text-slate-700">Target Role:</label>
                <select
                  id="target-role-select"
                  value={targetRoleId}
                  onChange={(e) => setTargetRoleId(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                >
                  <option value="STUDENT">STUDENT — Enrolled Learner</option>
                  <option value="STAFF">STAFF — Teaching Assistant / Grader</option>
                  <option value="ADMIN">ADMIN — Delegated Operations</option>
                  <option value="SUPER_ADMIN">SUPER_ADMIN — Platform Owner</option>
                </select>
              </div>

              <div className="space-y-2">
                <span className="font-semibold text-slate-700">Action:</span>
                <div className="flex gap-4">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="role-action"
                      checked={roleAction === "ASSIGN"}
                      onChange={() => setRoleAction("ASSIGN")}
                    />
                    <span>Grant Role</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="role-action"
                      checked={roleAction === "REVOKE"}
                      onChange={() => setRoleAction("REVOKE")}
                    />
                    <span>Revoke Role</span>
                  </label>
                </div>
              </div>

              {roleModalUser.roles.includes("SUPER_ADMIN") && roleAction === "REVOKE" && targetRoleId === "SUPER_ADMIN" && (
                <div className="rounded-lg bg-amber-50 p-3 text-[11px] text-amber-800 border border-amber-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                  <span>
                    <strong>Invariant Protection:</strong> The sole active Super Admin cannot be demoted. The database will
                    reject this transaction if no other active Super Admin exists.
                  </span>
                </div>
              )}
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRoleModalUser(null)}
                disabled={roleMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => roleMutation.mutate()}
                disabled={roleMutation.isPending}
              >
                {roleMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                Confirm Role Update
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}

      {/* Account Status Toggle Modal (Existing) */}
      {statusModalUser && (
        <Modal open={true} onOpenChange={(open) => !open && setStatusModalUser(null)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>
                {statusModalUser.is_active ? "Suspend Account" : "Activate Account"}: {statusModalUser.full_name}
              </ModalTitle>
              <ModalDescription>
                {statusModalUser.is_active
                  ? "Suspending this user account immediately revokes all active sessions. The student's learning history and enrollments remain preserved."
                  : "Activating this account restores login capabilities for the user."}
              </ModalDescription>
            </ModalHeader>

            {statusError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{statusError}</span>
              </div>
            )}

            <div className="space-y-3 text-xs">
              {statusModalUser.is_active && (
                <div className="rounded-lg bg-red-50 p-3 text-red-800 border border-red-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-600 mt-0.5" />
                  <span>
                    This account will be immediately deactivated and cannot sign in until reactivated by an authorized administrator.
                  </span>
                </div>
              )}

              <div className="space-y-1">
                <label htmlFor="status-reason-input" className="font-semibold text-slate-700">Reason / Internal Justification:</label>
                <Input
                  id="status-reason-input"
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  placeholder="e.g. Requested account hold, policy violation, etc."
                  className="text-xs"
                />
              </div>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStatusModalUser(null)}
                disabled={statusMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant={statusModalUser.is_active ? "destructive" : "primary"}
                size="sm"
                onClick={() => statusMutation.mutate()}
                disabled={statusMutation.isPending}
              >
                {statusMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                Confirm {statusModalUser.is_active ? "Suspension" : "Activation"}
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}
    </div>
  );
}
