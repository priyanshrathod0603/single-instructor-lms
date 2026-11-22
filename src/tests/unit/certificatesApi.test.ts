import { describe, it, expect, vi, beforeEach } from "vitest";
import { certificatesApi } from "@/lib/api/certificates";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("certificatesApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches certificate for completed course", async () => {
    const mockCert = {
      id: "cert-1",
      certificate_no: "LMS-2026-001",
      student_id: "stu-1",
      course_id: "course-1",
      issued_at: "2026-01-01T00:00:00Z",
      verification_hash: "v-hash-abc-123",
      pdf_url: "/s3/certificates/cert-1.pdf",
      is_revoked: false,
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockCert);

    const result = await certificatesApi.getCourseCertificate("course-1");

    expect(apiClient.get).toHaveBeenCalledWith("/certificates/course-1");
    expect(result.certificate_no).toBe("LMS-2026-001");
    expect(result.verification_hash).toBe("v-hash-abc-123");
  });

  it("generates correct download URL", () => {
    const url = certificatesApi.getDownloadUrl("course-123");
    expect(url).toBe("/api/v1/certificates/course-123/download");
  });

  it("verifies certificate publicly without auth token", async () => {
    const mockVerify = {
      verified: true,
      status: "VALID",
      certificate_no: "LMS-2026-001",
      student_name: "Priyansh Sharma",
      course_title: "Full-Stack Web Architecture",
      issued_at: "2026-01-01T00:00:00Z",
      verification_hash: "v-hash-abc-123",
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockVerify);

    const result = await certificatesApi.verifyCertificatePublic("v-hash-abc-123");

    expect(apiClient.get).toHaveBeenCalledWith("/certificates/verify/v-hash-abc-123");
    expect(result.verified).toBe(true);
    expect(result.status).toBe("VALID");
    expect(result.student_name).toBe("Priyansh Sharma");
  });
});
