"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Award, Download, Copy, Check, ExternalLink, ShieldCheck, ArrowLeft, BookOpen } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { certificatesApi } from "@/lib/api/certificates";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { CertificateResponse } from "@/types/certificate";

// Sub-component to fetch certificate per course
function CourseCertificateRow({
  courseId,
  courseTitle,
}: {
  courseId: string;
  courseTitle: string;
}) {
  const [copied, setCopied] = useState(false);

  const { data: certificate, isLoading, isError } = useQuery<CertificateResponse>({
    queryKey: ["certificate-item", courseId],
    queryFn: () => certificatesApi.getCourseCertificate(courseId),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="p-5 border-b border-slate-100 flex items-center justify-between">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-8 w-28" />
      </div>
    );
  }

  // If 400 or not completed yet, don't show row
  if (isError || !certificate) {
    return null;
  }

  const handleCopyLink = () => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const url = `${origin}/verify/certificate/${certificate.verification_hash}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between p-5 gap-4 hover:bg-slate-50/50 transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-mint/70 text-primary-teal shrink-0">
          <Award className="h-6 w-6" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-heading text-base font-bold text-slate-900">
              {courseTitle || certificate.course_title || "Course Certificate"}
            </h3>
            <Badge variant="mint" size="sm">
              <ShieldCheck className="mr-1 h-3 w-3 text-primary-teal" />
              Verified
            </Badge>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono text-slate-500">
            <span>Certificate #{certificate.certificate_no}</span>
            <span>Issued: {new Date(certificate.issued_at).toLocaleDateString()}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant="outline"
          size="sm"
          onClick={handleCopyLink}
          className="min-h-[36px] text-xs"
        >
          {copied ? (
            <>
              <Check className="mr-1.5 h-3.5 w-3.5 text-emerald-600" />
              Copied Link
            </>
          ) : (
            <>
              <Copy className="mr-1.5 h-3.5 w-3.5" />
              Share Link
            </>
          )}
        </Button>

        <a
          href={certificatesApi.getDownloadUrl(courseId)}
          target="_blank"
          rel="noreferrer"
        >
          <Button variant="primary" size="sm" className="min-h-[36px] text-xs">
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Download PDF
          </Button>
        </a>
      </div>
    </div>
  );
}

export default function CertificatesPage() {
  const {
    data: enrollmentsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["student-enrollments-certificates"],
    queryFn: () => enrollmentsApi.listOwnEnrollments({ page: 1, per_page: 50 }),
  });

  const enrollments = enrollmentsData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Contextual Back Navigation */}
      <div>
        <Link
          href="/app"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Overview
        </Link>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            My Verifiable Certificates
          </h1>
          <p className="font-sans text-sm text-slate-600 mt-1">
            Download your high-resolution verifiable completion credentials and public verification links.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <Card key={i} className="p-6 space-y-3">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-full" />
            </Card>
          ))}
        </div>
      ) : isError ? (
        <ErrorAlert
          title="Could not load certificates"
          message={error?.message || "Failed to load enrolled course certificates."}
          onRetry={() => refetch()}
        />
      ) : enrollments.length === 0 ? (
        <EmptyState
          icon={<Award className="h-8 w-8 text-primary-teal" />}
          title="No Certificates Earned Yet"
          description="Complete 100% of your course syllabus to receive an official cryptographic certificate of completion."
          actionLabel="View My Courses"
          onAction={() => {
            window.location.href = "/app/courses";
          }}
        />
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-xs text-slate-600 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
            <span>
              Certificates are automatically minted upon reaching 100% curriculum completion in an enrolled course.
            </span>
            <Link
              href="/app/courses"
              className="text-primary-teal font-semibold hover:underline shrink-0 flex items-center gap-1"
            >
              <BookOpen className="h-3.5 w-3.5" />
              <span>Continue Learning</span>
            </Link>
          </div>
          <Card className="border border-slate-200 bg-white shadow-card divide-y divide-slate-100 overflow-hidden">
            {enrollments.map((enr) => (
              <CourseCertificateRow
                key={enr.id}
                courseId={enr.course_id}
                courseTitle={enr.course_title || "Course"}
              />
            ))}
          </Card>
        </div>
      )}
    </div>
  );
}
