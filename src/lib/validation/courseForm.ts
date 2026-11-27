import * as z from "zod";
import { CourseDifficultyLevel } from "@/types/course";

export const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function slugifyCourseTitle(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Parse a rupee string (e.g. "2999" or "2999.50") into integer paise without float drift.
 * Returns null if blank; returns NaN if malformed/negative.
 */
export function parseRupeesToPaise(raw: string | number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  const trimmed = String(raw).trim().replace(/,/g, "");
  if (!trimmed) return null;
  if (!/^\d+(?:\.\d{1,2})?$/.test(trimmed)) {
    return Number.NaN;
  }
  const [wholePart, fracPart = ""] = trimmed.split(".");
  const whole = Number.parseInt(wholePart, 10);
  const paiseFraction = Number.parseInt(fracPart.padEnd(2, "0"), 10);
  return whole * 100 + paiseFraction;
}

export function paiseToRupeesInput(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "";
  if (paise === 0) return "0";
  const whole = Math.floor(paise / 100);
  const remainder = paise % 100;
  if (remainder === 0) return String(whole);
  return `${whole}.${String(remainder).padStart(2, "0")}`.replace(/0$/, "");
}

export function formatInrFromPaise(paise: number): string {
  const rupees = paise / 100;
  const hasFraction = paise % 100 !== 0;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0,
  }).format(rupees);
}

export function calculateDiscountPercentage(
  regularPaise: number | null,
  discountedPaise: number | null,
): number | null {
  if (
    regularPaise === null ||
    discountedPaise === null ||
    Number.isNaN(regularPaise) ||
    Number.isNaN(discountedPaise) ||
    regularPaise <= 0 ||
    discountedPaise <= 0 ||
    discountedPaise >= regularPaise
  ) {
    return null;
  }
  const pct = Math.round(((regularPaise - discountedPaise) / regularPaise) * 100);
  return pct > 0 ? pct : null;
}

export function validateImageUrlInput(url: string): boolean {
  const trimmed = url.trim();
  if (!trimmed) return true;
  if (/\s/.test(trimmed)) return false;
  const lower = trimmed.toLowerCase();
  if (lower.startsWith("javascript:") || lower.startsWith("vbscript:") || lower.startsWith("data:")) {
    return false;
  }
  if (trimmed.startsWith("/api/v1/media/public/")) return true;
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export const courseMetadataFormSchema = z
  .object({
    title: z
      .string()
      .refine((v) => v.trim().length >= 3, "Course title must be at least 3 characters.")
      .refine((v) => v.trim().length <= 255, "Course title must be 255 characters or fewer."),
    slug: z
      .string()
      .refine((v) => v.trim().length > 0, "Course slug is required.")
      .refine(
        (v) => SLUG_PATTERN.test(v.trim().toLowerCase()),
        "Slug must use lowercase letters, numbers, and hyphens only (e.g. 'system-design-101').",
      )
      .refine((v) => v.trim().length <= 255, "Slug must be 255 characters or fewer."),
    headline: z.string().max(512, "Short headline must be 512 characters or fewer."),
    description: z.string().max(20000, "Description must be 20,000 characters or fewer."),
    thumbnail_url: z
      .string()
      .max(512, "Thumbnail URL must be 512 characters or fewer.")
      .refine(
        (v) => validateImageUrlInput(v),
        "Provide a valid http(s) image URL or upload an image file.",
      ),
    thumbnail_media_id: z.string().nullable(),
    category: z
      .string()
      .refine((v) => v.trim().length >= 1, "Category is required.")
      .refine((v) => v.trim().length <= 64, "Category must be 64 characters or fewer."),
    difficulty_level: z.enum(["BEGINNER", "INTERMEDIATE", "ADVANCED", "ALL_LEVELS"]),
    language: z
      .string()
      .refine((v) => v.trim().length >= 1, "Language is required.")
      .refine((v) => v.trim().length <= 32, "Language must be 32 characters or fewer."),
    tags: z.array(z.string()).max(20, "Maximum 20 tags allowed."),
    learning_outcomes: z
      .array(z.string().max(240, "Each learning outcome must be 240 characters or fewer."))
      .max(30, "Maximum 30 learning outcomes allowed."),
    requirements: z
      .array(z.string().max(240, "Each requirement must be 240 characters or fewer."))
      .max(30, "Maximum 30 requirements allowed."),
    is_free: z.boolean(),
    regular_price_rupees: z.string(),
    discounted_price_rupees: z.string(),
    currency: z.literal("INR"),
  })
  .superRefine((data, ctx) => {
    const outcomeSeen = new Set<string>();
    for (let i = 0; i < data.learning_outcomes.length; i += 1) {
      const cleaned = data.learning_outcomes[i].trim();
      if (!cleaned) {
        ctx.addIssue({
          code: "custom",
          path: ["learning_outcomes"],
          message: "Learning outcomes cannot contain empty items.",
        });
        break;
      }
      if (outcomeSeen.has(cleaned.toLowerCase())) {
        ctx.addIssue({
          code: "custom",
          path: ["learning_outcomes"],
          message: "Duplicate learning outcomes are not allowed.",
        });
        break;
      }
      outcomeSeen.add(cleaned.toLowerCase());
    }

    const reqSeen = new Set<string>();
    for (let i = 0; i < data.requirements.length; i += 1) {
      const cleaned = data.requirements[i].trim();
      if (!cleaned) {
        ctx.addIssue({
          code: "custom",
          path: ["requirements"],
          message: "Course requirements cannot contain empty items.",
        });
        break;
      }
      if (reqSeen.has(cleaned.toLowerCase())) {
        ctx.addIssue({
          code: "custom",
          path: ["requirements"],
          message: "Duplicate requirements are not allowed.",
        });
        break;
      }
      reqSeen.add(cleaned.toLowerCase());
    }

    if (data.is_free) {
      return;
    }

    const regularPaise = parseRupeesToPaise(data.regular_price_rupees);
    if (regularPaise === null) {
      ctx.addIssue({
        code: "custom",
        path: ["regular_price_rupees"],
        message: "Regular price is required for a paid course (or enable Free Course).",
      });
      return;
    }
    if (Number.isNaN(regularPaise) || regularPaise <= 0) {
      ctx.addIssue({
        code: "custom",
        path: ["regular_price_rupees"],
        message: "Enter a valid positive INR amount (e.g. 2999 or 2999.50).",
      });
      return;
    }

    const discountedPaise = parseRupeesToPaise(data.discounted_price_rupees);
    if (discountedPaise !== null) {
      if (Number.isNaN(discountedPaise) || discountedPaise <= 0) {
        ctx.addIssue({
          code: "custom",
          path: ["discounted_price_rupees"],
          message: "Discounted price must be a valid positive INR amount.",
        });
        return;
      }
      if (discountedPaise > regularPaise) {
        ctx.addIssue({
          code: "custom",
          path: ["discounted_price_rupees"],
          message: "Discounted price cannot exceed regular price.",
        });
      }
    }
  });

export interface CourseMetadataFormValues {
  title: string;
  slug: string;
  headline: string;
  description: string;
  thumbnail_url: string;
  thumbnail_media_id: string | null;
  category: string;
  difficulty_level: CourseDifficultyLevel;
  language: string;
  tags: string[];
  learning_outcomes: string[];
  requirements: string[];
  is_free: boolean;
  regular_price_rupees: string;
  discounted_price_rupees: string;
  currency: "INR";
}

export function buildCoursePricingPayload(
  values: Pick<CourseMetadataFormValues, "is_free" | "regular_price_rupees" | "discounted_price_rupees">,
): {
  is_free: boolean;
  price_inr: number;
  compare_at_price_inr: number | null;
} {
  if (values.is_free) {
    return {
      is_free: true,
      price_inr: 0,
      compare_at_price_inr: null,
    };
  }
  const regularPaise = parseRupeesToPaise(values.regular_price_rupees) ?? 0;
  const discountedPaise = parseRupeesToPaise(values.discounted_price_rupees);

  if (
    discountedPaise !== null &&
    !Number.isNaN(discountedPaise) &&
    discountedPaise > 0 &&
    discountedPaise < regularPaise
  ) {
    return {
      is_free: false,
      price_inr: discountedPaise,
      compare_at_price_inr: regularPaise,
    };
  }

  return {
    is_free: false,
    price_inr: regularPaise,
    compare_at_price_inr: null,
  };
}
