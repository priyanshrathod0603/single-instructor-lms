"use client";

import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings,
  Shield,
  ShieldCheck,
  Lock,
  Save,
  RotateCw,
  Mail,
  Phone,
  Globe,
  Image as ImageIcon,
  Building,
  Server,
  Layers,
  AlertCircle,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import { PlatformSettingsUpdatePayload } from "@/types/commerce";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function PlatformSettingsPage() {
  const queryClient = useQueryClient();

  // Fetch current platform settings & safe system context
  const { data: settings, isLoading, refetch } = useQuery({
    queryKey: ["control-platform-settings"],
    queryFn: () => controlApi.getPlatformSettings(),
    staleTime: 30000,
  });

  // Form State
  const [platformName, setPlatformName] = useState("");
  const [brandName, setBrandName] = useState("");
  const [brandDescription, setBrandDescription] = useState("");
  const [supportEmail, setSupportEmail] = useState("");
  const [supportPhone, setSupportPhone] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // Sync state when settings query loads
  useEffect(() => {
    if (settings) {
      setPlatformName(settings.platform_name || "");
      setBrandName(settings.brand_name || "");
      setBrandDescription(settings.brand_description || "");
      setSupportEmail(settings.support_email || "");
      setSupportPhone(settings.support_phone || "");
      setLogoUrl(settings.logo_url || "");
    }
  }, [settings]);

  // Mutation
  const updateMutation = useMutation({
    mutationFn: (payload: PlatformSettingsUpdatePayload) =>
      controlApi.updatePlatformSettings(payload),
    onSuccess: () => {
      toast.success("Platform settings updated successfully");
      queryClient.invalidateQueries({ queryKey: ["control-platform-settings"] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error?.message || err.message || "Failed to update platform settings";
      setFormError(msg);
      toast.error(msg);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!platformName.trim() || !brandName.trim()) {
      setFormError("Platform Name and Brand Name cannot be empty.");
      return;
    }

    const payload: PlatformSettingsUpdatePayload = {
      platform_name: platformName.trim(),
      brand_name: brandName.trim(),
      brand_description: brandDescription.trim() || null,
      support_email: supportEmail.trim() || null,
      support_phone: supportPhone.trim() || null,
      logo_url: logoUrl.trim() || null,
    };

    updateMutation.mutate(payload);
  };

  return (
    <div className="space-y-8 p-6 max-w-5xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Platform Information & Settings
            </h1>
            <Badge variant="outline" className="bg-primary-teal/10 text-primary-teal border-primary-teal/20 text-xs">
              Super Admin Exclusive
            </Badge>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure instructor branding, public contact details, and review server runtime configuration.
          </p>
        </div>

        <Button
          variant="outline"
          onClick={() => {
            refetch();
            toast.success("Settings reloaded");
          }}
          className="flex items-center gap-2 min-h-[44px]"
        >
          <RotateCw className="h-4 w-4" />
          Reload
        </Button>
      </div>

      {/* Security Architecture Notice (Master Secret Isolation) */}
      <div className="bg-slate-900 text-white rounded-xl p-5 border border-slate-800 shadow-md">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-primary-teal/20 text-primary-teal rounded-lg mt-0.5">
            <Lock className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              Strict Master Secret Isolation
              <Badge variant="outline" className="text-[10px] bg-emerald-950 text-emerald-300 border-emerald-800">
                Guaranteed
              </Badge>
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              In accordance with project security invariants, cryptographic secrets (<code className="text-xs text-primary-teal">SECRET_KEY</code>, PostgreSQL credentials, Redis authentication, Razorpay secrets, SMTP passwords, and cloud storage access keys) are strictly managed via server environment variables. They are never stored in the database or serialized across the control portal API.
            </p>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-16 text-slate-500">
          <Loader2 className="h-8 w-8 animate-spin text-primary-teal mb-3" />
          <p className="text-sm">Loading platform configuration...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left 2 Cols: Editable Branding Form */}
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6 shadow-xs">
              <div className="flex items-center gap-2 pb-4 mb-4 border-b border-slate-100 dark:border-slate-800">
                <Building className="h-5 w-5 text-primary-teal" />
                <h2 className="text-base font-bold text-slate-900 dark:text-white">
                  Brand & Public Platform Information
                </h2>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {formError && (
                  <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 rounded-md border border-rose-200 flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    <span>{formError}</span>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Platform Name *
                    </label>
                    <Input
                      required
                      value={platformName}
                      onChange={(e) => setPlatformName(e.target.value)}
                      placeholder="e.g. Single-Instructor LMS"
                    />
                    <p className="text-[11px] text-slate-400 mt-1">
                      Global application name shown in title headers.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Brand Name *
                    </label>
                    <Input
                      required
                      value={brandName}
                      onChange={(e) => setBrandName(e.target.value)}
                      placeholder="e.g. Apex Learning"
                    />
                    <p className="text-[11px] text-slate-400 mt-1">
                      Instructor brand identity on certificates and receipts.
                    </p>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Brand Description
                  </label>
                  <textarea
                    rows={3}
                    value={brandDescription}
                    onChange={(e) => setBrandDescription(e.target.value)}
                    placeholder="Short description of the platform, instructor credentials, and mission..."
                    className="w-full p-2.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm focus:outline-none focus:ring-1 focus:ring-primary-teal text-slate-900 dark:text-slate-100"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Support Email
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        type="email"
                        value={supportEmail}
                        onChange={(e) => setSupportEmail(e.target.value)}
                        placeholder="support@example.com"
                        className="pl-9"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Support Phone
                    </label>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        type="tel"
                        value={supportPhone}
                        onChange={(e) => setSupportPhone(e.target.value)}
                        placeholder="+91 98765 43210"
                        className="pl-9"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Logo Image URL
                  </label>
                  <div className="relative">
                    <ImageIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <Input
                      type="url"
                      value={logoUrl}
                      onChange={(e) => setLogoUrl(e.target.value)}
                      placeholder="https://cdn.example.com/logo.png"
                      className="pl-9"
                    />
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1">
                    URL to public brand logo image (PNG/SVG recommended).
                  </p>
                </div>

                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex justify-end">
                  <Button
                    type="submit"
                    disabled={updateMutation.isPending}
                    className="bg-primary-teal hover:bg-primary-teal/90 text-white flex items-center gap-2 min-h-[44px]"
                  >
                    {updateMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Saving Changes...
                      </>
                    ) : (
                      <>
                        <Save className="h-4 w-4" />
                        Save Platform Settings
                      </>
                    )}
                  </Button>
                </div>
              </form>
            </div>
          </div>

          {/* Right Col: Safe Read-Only Runtime Context */}
          <div className="space-y-6">
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 shadow-xs">
              <div className="flex items-center gap-2 pb-3 mb-4 border-b border-slate-100 dark:border-slate-800">
                <Server className="h-5 w-5 text-primary-teal" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Runtime Environment
                </h3>
              </div>

              <div className="space-y-3.5 text-xs">
                <div>
                  <span className="text-slate-400 block mb-0.5">Application Version</span>
                  <span className="font-mono font-semibold text-slate-900 dark:text-white bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                    {settings?.version}
                  </span>
                </div>

                <div>
                  <span className="text-slate-400 block mb-0.5">Deployment Environment</span>
                  <Badge
                    variant="outline"
                    className={`text-xs ${
                      settings?.environment === "production"
                        ? "bg-rose-50 text-rose-700 border-rose-200"
                        : "bg-emerald-50 text-emerald-700 border-emerald-200"
                    }`}
                  >
                    {settings?.environment?.toUpperCase()}
                  </Badge>
                </div>

                <div>
                  <span className="text-slate-400 block mb-0.5">Platform Currency</span>
                  <span className="font-semibold text-slate-900 dark:text-white">
                    {settings?.currency} (₹ Indian Rupee)
                  </span>
                </div>

                <div>
                  <span className="text-slate-400 block mb-0.5">Client Frontend URL</span>
                  <span className="font-mono text-slate-600 dark:text-slate-300 break-all">
                    {settings?.frontend_url}
                  </span>
                </div>

                <div>
                  <span className="text-slate-400 block mb-0.5">Video CDN Stream URL</span>
                  <span className="font-mono text-slate-600 dark:text-slate-300 break-all">
                    {settings?.cdn_stream_base_url}
                  </span>
                </div>

                <div>
                  <span className="text-slate-400 block mb-0.5">Transactional Email Provider</span>
                  <Badge variant="outline" className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                    {settings?.email_provider}
                  </Badge>
                </div>

                <div>
                  <span className="text-slate-400 block mb-0.5">Media Storage Provider</span>
                  <Badge variant="outline" className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                    {settings?.storage_provider}
                  </Badge>
                </div>

                {settings?.updated_at && (
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-400">
                    Last modified: {new Date(settings.updated_at).toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
