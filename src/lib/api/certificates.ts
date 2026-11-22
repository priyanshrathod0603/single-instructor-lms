import { apiClient } from "./client";
import {
  CertificateResponse,
  CertificateVerifyResponse,
} from "@/types/certificate";

export const certificatesApi = {
  /**
   * Retrieve certificate for 100% completed course.
   */
  async getCourseCertificate(courseId: string): Promise<CertificateResponse> {
    return apiClient.get<CertificateResponse>(
      `/certificates/${encodeURIComponent(courseId)}`
    );
  },

  /**
   * Get direct download URL for verifiable certificate PDF.
   */
  getDownloadUrl(courseId: string): string {
    return `/api/v1/certificates/${encodeURIComponent(courseId)}/download`;
  },

  /**
   * Public verification endpoint resolving certificate authenticity without auth.
   */
  async verifyCertificatePublic(
    verificationHash: string
  ): Promise<CertificateVerifyResponse> {
    return apiClient.get<CertificateVerifyResponse>(
      `/certificates/verify/${encodeURIComponent(verificationHash)}`
    );
  },
};
