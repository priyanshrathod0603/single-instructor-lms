"use client";

import React, { useState, useEffect } from "react";
import { User, Mail, Shield, LogOut, CheckCircle, Save } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { usersApi } from "@/lib/api/users";
import { useAuthStore } from "@/lib/store/authStore";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

export default function StudentProfilePage() {
  const { user, logout, isLoggingOut } = useAuth();
  const setUser = useAuthStore((s) => s.setUser);

  const [fullName, setFullName] = useState(user?.full_name || "");
  const [isUpdating, setIsUpdating] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (user?.full_name) {
      setFullName(user.full_name);
    }
  }, [user?.full_name]);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user?.id) return;

    setIsUpdating(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const updatedUser = await usersApi.updateProfile(user.id, {
        full_name: fullName.trim(),
      });
      setUser(updatedUser);
      setSuccessMessage("Profile updated successfully!");
    } catch (err: any) {
      // PRESERVE FORM INPUT ON ERROR
      setErrorMessage(
        err?.message || "Failed to update profile. Your changes have been preserved."
      );
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Account Settings & Security
        </h1>
        <p className="font-sans text-sm text-slate-600 mt-1">
          Manage your personal details, verify credentials, and review active session security.
        </p>
      </div>

      {/* Profile Information Card */}
      <Card className="p-6 sm:p-8 border border-slate-200 bg-white space-y-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-mint text-primary-teal font-heading font-bold text-lg">
              {user?.full_name?.charAt(0) || "S"}
            </div>
            <div>
              <h2 className="font-heading text-lg font-bold text-slate-900">
                Personal Information
              </h2>
              <p className="font-sans text-xs text-slate-500">
                Update how your name appears on your completion certificates
              </p>
            </div>
          </div>
          <Badge variant="mint" size="sm">
            {user?.roles?.[0] || "Student"}
          </Badge>
        </div>

        {errorMessage && <ErrorAlert message={errorMessage} />}

        {successMessage && (
          <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-xs sm:text-sm text-emerald-800">
            <CheckCircle className="h-4 w-4 text-emerald-600 shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        <form onSubmit={handleUpdateProfile} className="space-y-4">
          <Input
            label="Full Legal Name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            helperText="This exact name will be engraved onto your verifiable PDF certificates."
          />

          <Input
            label="Email Address (Account Identifier)"
            type="email"
            value={user?.email || ""}
            disabled
            helperText="Your email address is your primary security credential and cannot be edited directly."
          />

          <div className="pt-2 flex justify-end">
            <Button type="submit" variant="primary" size="default" isLoading={isUpdating}>
              <Save className="mr-2 h-4 w-4" />
              Save Profile Changes
            </Button>
          </div>
        </form>
      </Card>

      {/* Single-Active-Session Governance Card */}
      <Card className="p-6 sm:p-8 border border-slate-200 bg-white space-y-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-peach/60 text-accent-coral shrink-0">
            <Shield className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <h3 className="font-heading text-base font-bold text-slate-900">
              Single-Active-Session Governance
            </h3>
            <p className="font-sans text-xs sm:text-sm text-slate-600 leading-relaxed">
              To protect course content and maintain account security, this platform strictly enforces a <strong>single active session</strong> policy. Signing in from another device or browser will atomically displace and terminate your prior session.
            </p>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <span className="font-mono text-xs text-slate-500">
            Need to sign out on this device?
          </span>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => logout()}
            disabled={isLoggingOut}
            isLoading={isLoggingOut}
            className="shrink-0"
          >
            <LogOut className="mr-1.5 h-3.5 w-3.5" />
            Sign Out Session
          </Button>
        </div>
      </Card>

      <AuthLoadingOverlay
        isOpen={isLoggingOut}
        statusMessage="Signing out securely…"
        subMessage="Ending your active session"
      />
    </div>
  );
}
