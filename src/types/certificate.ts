/**
 * TypeScript definitions for Certificates and Public Verification.
 * Synchronized with backend: backend/app/schemas/certificate.py
 */

export interface CertificateResponse {
  id: string;
  certificate_no: string;
  student_id: string;
  course_id: string;
  issued_at: string;
  verification_hash: string;
  pdf_url: string;
  is_revoked: boolean;
  student_name?: string | null;
  course_title?: string | null;
  verify_url?: string | null;
}

export interface CertificateVerifyResponse {
  verified: boolean;
  status: "VALID" | "REVOKED" | "INVALID" | string;
  certificate_no?: string | null;
  student_name?: string | null;
  course_title?: string | null;
  issued_at?: string | null;
  verification_hash?: string | null;
  pdf_url?: string | null;
  revoked_at?: string | null;
  revoked_reason?: string | null;
}
