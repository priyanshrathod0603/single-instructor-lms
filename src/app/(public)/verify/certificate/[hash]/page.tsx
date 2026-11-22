"use client";

import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ShieldCheck,
  AlertTriangle,
  Award,
  Calendar,
  User,
  BookOpen,
  Hash,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { certificatesApi } from "@/lib/api/certificates";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

export default function PublicCertificateVerificationPage() {
  const params = useParams();
  const hash = params?.hash as string;

  const {
    data: cert,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["public-certificate-verify", hash],
    queryFn: () => certificatesApi.verifyCertificatePublic(hash),
    enabled: !!hash,
    retry: 1,
  });

  return (
    <div className="min-h-[70vh] flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-2xl w-full space-y-8">
        {/* Verification Status Header */}
        <div className="text-center space-y-2">
          <Badge variant="mint" size="md" className="text-xs uppercase tracking-wider font-semibold">
            Official Credential Verification Registry
          </Badge>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900">
            Certificate Authenticity Verification
          </h1>
          <p className="font-sans text-xs sm:text-sm text-slate-600 max-w-md mx-auto">
            This verification registry confirms the legitimacy and cryptographic integrity of completion credentials issued by the instructor.
          </p>
        </div>

        {/* State Handling */}
        {isLoading ? (
          <Card className="p-8 space-y-6">
            <Skeleton className="h-16 w-16 rounded-full mx-auto" />
            <Skeleton className="h-8 w-64 mx-auto" />
            <div className="space-y-3 pt-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4 mx-auto" />
            </div>
          </Card>
        ) : isError || !cert ? (
          <Card className="p-8 text-center space-y-4 border-rose-200 bg-rose-50/60">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-rose-100 text-rose-700 mx-auto">
              <XCircle className="h-8 w-8" />
            </div>
            <h2 className="font-heading text-xl font-bold text-rose-950">
              Invalid or Unrecognized Certificate
            </h2>
            <p className="text-xs sm:text-sm text-rose-800 max-w-sm mx-auto font-sans">
              The verification hash provided could not be validated against the credential registry.
            </p>
            <div className="pt-2">
              <Link href="/courses">
                <Button variant="primary" size="sm">
                  Browse Authentic Courses
                </Button>
              </Link>
            </div>
          </Card>
        ) : cert.status === "REVOKED" ? (
          /* REVOKED CERTIFICATE */
          <Card className="p-8 text-center space-y-4 border-rose-300 bg-rose-50">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-rose-100 text-rose-700 mx-auto">
              <AlertTriangle className="h-8 w-8" />
            </div>
            <Badge variant="error" size="md">
              REVOKED CREDENTIAL
            </Badge>
            <h2 className="font-heading text-xl font-bold text-rose-950">
              This Certificate Has Been Revoked
            </h2>
            <div className="space-y-1 text-xs sm:text-sm text-rose-800 font-sans">
              <p>
                <span className="font-semibold">Reason:</span>{" "}
                {cert.revoked_reason || "Administrative policy revocation"}
              </p>
              {cert.revoked_at && (
                <p>
                  <span className="font-semibold">Date of Revocation:</span>{" "}
                  {new Date(cert.revoked_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </Card>
        ) : (
          /* VALID AND AUTHENTIC CERTIFICATE */
          <Card className="p-8 sm:p-10 border border-emerald-200 bg-white shadow-xl space-y-6">
            <div className="flex flex-col items-center text-center space-y-3 pb-6 border-b border-slate-100">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                <ShieldCheck className="h-9 w-9" />
              </div>
              <Badge variant="mint" size="md" className="text-xs uppercase tracking-wider font-bold">
                ✓ Cryptographically Verified Credential
              </Badge>
              <h2 className="font-heading text-2xl font-bold text-slate-900">
                Official Certificate of Completion
              </h2>
            </div>

            {/* Verified Details Matrix */}
            <div className="space-y-4 font-sans text-sm">
              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="flex items-center gap-2 text-slate-600 font-medium">
                  <User className="h-4 w-4 text-primary-teal" />
                  Awarded To:
                </span>
                <span className="font-heading font-bold text-slate-900">
                  {cert.student_name || "Verified Student"}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="flex items-center gap-2 text-slate-600 font-medium">
                  <BookOpen className="h-4 w-4 text-primary-teal" />
                  Masterclass Course:
                </span>
                <span className="font-heading font-bold text-slate-900 text-right">
                  {cert.course_title || "Verified Course"}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="flex items-center gap-2 text-slate-600 font-medium">
                  <Calendar className="h-4 w-4 text-primary-teal" />
                  Issue Date:
                </span>
                <span className="font-mono text-slate-900">
                  {cert.issued_at ? new Date(cert.issued_at).toLocaleDateString() : "Verified"}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="flex items-center gap-2 text-slate-600 font-medium">
                  <Award className="h-4 w-4 text-primary-teal" />
                  Certificate Number:
                </span>
                <span className="font-mono font-bold text-primary-teal">
                  #{cert.certificate_no}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
                <span className="flex items-center gap-2 text-slate-600 font-medium text-xs">
                  <Hash className="h-3.5 w-3.5 text-slate-400" />
                  Verification Fingerprint:
                </span>
                <p className="font-mono text-xs text-slate-500 break-all select-all">
                  {cert.verification_hash || hash}
                </p>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 text-center">
              <Link href="/courses">
                <Button variant="outline" size="sm">
                  Explore Course Catalog
                </Button>
              </Link>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
