"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  IndianRupee,
  Layers,
  ListChecks,
  Loader2,
  Save,
  Sparkles,
  Tag,
  Wand2,
} from "lucide-react";

import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { coursesApi } from "@/lib/api/courses";
import { parseApiError } from "@/lib/api/errors";
import {
  CourseMetadataFormValues,
  SLUG_PATTERN,
  buildCoursePricingPayload,
  calculateDiscountPercentage,
  courseMetadataFormSchema,
  formatInrFromPaise,
  paiseToRupeesInput,
  parseRupeesToPaise,
  slugifyCourseTitle,
} from "@/lib/validation/courseForm";
import {
  CourseDetail,
  CourseDifficultyLevel,
  DEFAULT_COURSE_CATEGORIES,
  DEFAULT_COURSE_LANGUAGES,
  DIFFICULTY_LEVEL_LABELS,
} from "@/types/course";

import { StringListEditor } from "./StringListEditor";
import { TagInputField } from "./TagInputField";
import { ThumbnailUploadCard } from "./ThumbnailUploadCard";

export interface CourseMetadataFormProps {
  mode: "create" | "edit";
  courseId?: string;
  initialCourse?: CourseDetail;
  onSaved?: (savedCourse: CourseDetail) => void;
  onCancel?: () => void;
}

function mapCourseToFormValues(course?: CourseDetail): CourseMetadataFormValues {
  if (!course) {
    return {
      title: "",
      slug: "",
      headline: "",
      description: "",
      thumbnail_url: "",
      thumbnail_media_id: null,
      category: "General",
      difficulty_level: "ALL_LEVELS",
      language: "English",
      tags: [],
      learning_outcomes: [],
      requirements: [],
      is_free: false,
      regular_price_rupees: "",
      discounted_price_rupees: "",
      currency: "INR",
    };
  }

  let regularRupees = "";
  let discountedRupees = "";

  if (!course.is_free) {
    if (course.compare_at_price_inr && course.compare_at_price_inr > course.price_inr) {
      regularRupees = paiseToRupeesInput(course.compare_at_price_inr);
      discountedRupees = paiseToRupeesInput(course.price_inr);
    } else {
      regularRupees = paiseToRupeesInput(course.price_inr);
    }
  }

  const normalizedDiff = (course.difficulty_level || "ALL_LEVELS").toUpperCase();
  const validDiff: CourseDifficultyLevel =
    normalizedDiff === "BEGINNER" ||
    normalizedDiff === "INTERMEDIATE" ||
    normalizedDiff === "ADVANCED" ||
    normalizedDiff === "ALL_LEVELS"
      ? normalizedDiff
      : "ALL_LEVELS";

  return {
    title: course.title || "",
    slug: course.slug || "",
    headline: course.headline || "",
    description: course.description || "",
    thumbnail_url: course.thumbnail_url || "",
    thumbnail_media_id: course.thumbnail_media_id ?? null,
    category: course.category || "General",
    difficulty_level: validDiff,
    language: course.language || "English",
    tags: Array.isArray(course.tags) ? [...course.tags] : [],
    learning_outcomes: Array.isArray(course.learning_outcomes)
      ? [...course.learning_outcomes]
      : [],
    requirements: Array.isArray(course.requirements) ? [...course.requirements] : [],
    is_free: Boolean(course.is_free),
    regular_price_rupees: regularRupees,
    discounted_price_rupees: discountedRupees,
    currency: "INR",
  };
}

export const CourseMetadataForm: React.FC<CourseMetadataFormProps> = ({
  mode,
  courseId,
  initialCourse,
  onSaved,
  onCancel,
}) => {
  const [slugManuallyEdited, setSlugManuallyEdited] = useState<boolean>(mode === "edit");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [serverError, setServerError] = useState<{
    message: string;
    code?: string;
    requestId?: string;
  } | null>(null);
  const [slugAvailability, setSlugAvailability] = useState<{
    status: "idle" | "checking" | "available" | "unavailable";
    reason?: string | null;
  }>({ status: "idle" });
  const [customCategoryMode, setCustomCategoryMode] = useState(false);

  const errorSummaryRef = useRef<HTMLDivElement>(null);

  const { data: metadataOptions } = useQuery({
    queryKey: ["course-metadata-options"],
    queryFn: () => coursesApi.getMetadataOptions(),
    staleTime: 60_000,
    retry: false,
  });

  const defaultValues = useMemo(() => mapCourseToFormValues(initialCourse), [initialCourse]);

  const {
    register,
    control,
    handleSubmit,
    setValue,
    setError,
    reset,
    formState: { errors, isDirty, isSubmitting, touchedFields },
  } = useForm<CourseMetadataFormValues>({
    resolver: zodResolver(courseMetadataFormSchema),
    mode: "onTouched",
    defaultValues,
  });

  // Sync form when initialCourse updates (e.g. parent re-fetch on edit) cleanly without clobbering active edits
  const lastLoadedCourseId = useRef<string | undefined>(initialCourse?.id);
  useEffect(() => {
    if (initialCourse && initialCourse.id !== lastLoadedCourseId.current) {
      lastLoadedCourseId.current = initialCourse.id;
      reset(mapCourseToFormValues(initialCourse));
      setSlugManuallyEdited(true);
    }
  }, [initialCourse, reset]);

  // Warn on browser tab close / reload when unsaved changes exist
  useEffect(() => {
    if (!isDirty) return;
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const watchedTitle = useWatch({ control, name: "title" });
  const watchedSlug = useWatch({ control, name: "slug" });
  const watchedHeadline = useWatch({ control, name: "headline" });
  const watchedCategory = useWatch({ control, name: "category" });
  const watchedLanguage = useWatch({ control, name: "language" });
  const watchedTags = useWatch({ control, name: "tags" });
  const watchedOutcomes = useWatch({ control, name: "learning_outcomes" });
  const watchedRequirements = useWatch({ control, name: "requirements" });
  const watchedThumbUrl = useWatch({ control, name: "thumbnail_url" });
  const watchedThumbMediaId = useWatch({ control, name: "thumbnail_media_id" });
  const watchedIsFree = useWatch({ control, name: "is_free" });
  const watchedRegularRupees = useWatch({ control, name: "regular_price_rupees" });
  const watchedDiscountRupees = useWatch({ control, name: "discounted_price_rupees" });

  // Auto-generate slug from title in create mode (or until manual edit)
  useEffect(() => {
    if (!slugManuallyEdited && typeof watchedTitle === "string") {
      const nextSlug = slugifyCourseTitle(watchedTitle);
      setValue("slug", nextSlug, {
        shouldValidate: Boolean(touchedFields.slug),
        shouldDirty: mode === "create" ? Boolean(nextSlug) : isDirty,
      });
    }
  }, [watchedTitle, slugManuallyEdited, setValue, touchedFields.slug, mode, isDirty]);

  // Debounced backend slug uniqueness check
  useEffect(() => {
    const cleanSlug = (watchedSlug || "").trim().toLowerCase();
    if (!cleanSlug || !SLUG_PATTERN.test(cleanSlug)) {
      setSlugAvailability({ status: "idle" });
      return;
    }
    if (
      mode === "edit" &&
      initialCourse?.slug &&
      cleanSlug === initialCourse.slug.toLowerCase()
    ) {
      setSlugAvailability({ status: "available", reason: null });
      return;
    }

    let cancelled = false;
    setSlugAvailability({ status: "checking" });
    const timer = window.setTimeout(async () => {
      try {
        const res = await coursesApi.checkSlugAvailability(
          cleanSlug,
          mode === "edit" ? courseId : undefined,
        );
        if (cancelled) return;
        setSlugAvailability({
          status: res.available ? "available" : "unavailable",
          reason: res.reason,
        });
      } catch {
        if (!cancelled) {
          setSlugAvailability({ status: "idle" });
        }
      }
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [watchedSlug, mode, courseId, initialCourse?.slug]);

  const categoryChoices = useMemo(() => {
    const base = metadataOptions?.categories?.length
      ? metadataOptions.categories
      : [...DEFAULT_COURSE_CATEGORIES];
    const set = new Set<string>(base);
    if (watchedCategory && !set.has(watchedCategory)) {
      set.add(watchedCategory);
    }
    return Array.from(set);
  }, [metadataOptions?.categories, watchedCategory]);

  const difficultyChoices = useMemo(() => {
    if (metadataOptions?.difficulty_levels?.length) {
      return metadataOptions.difficulty_levels;
    }
    return Object.entries(DIFFICULTY_LEVEL_LABELS).map(([value, label]) => ({
      value,
      label,
    }));
  }, [metadataOptions?.difficulty_levels]);

  const languageChoices = useMemo(() => {
    const base = metadataOptions?.languages?.length
      ? metadataOptions.languages
      : [...DEFAULT_COURSE_LANGUAGES];
    const set = new Set<string>(base);
    if (watchedLanguage && !set.has(watchedLanguage)) {
      set.add(watchedLanguage);
    }
    return Array.from(set);
  }, [metadataOptions?.languages, watchedLanguage]);

  const pricingPreview = useMemo(() => {
    if (watchedIsFree) {
      return {
        isFree: true,
        effectivePaise: 0,
        regularPaise: null as number | null,
        discountPct: null as number | null,
      };
    }
    const regularPaise = parseRupeesToPaise(watchedRegularRupees);
    const discountPaise = parseRupeesToPaise(watchedDiscountRupees);
    const validRegular =
      regularPaise !== null && !Number.isNaN(regularPaise) && regularPaise > 0
        ? regularPaise
        : null;
    const validDiscount =
      discountPaise !== null &&
      !Number.isNaN(discountPaise) &&
      discountPaise > 0 &&
      validRegular !== null &&
      discountPaise < validRegular
        ? discountPaise
        : null;

    return {
      isFree: false,
      effectivePaise: validDiscount ?? validRegular ?? 0,
      regularPaise: validRegular,
      discountPct:
        validRegular !== null && validDiscount !== null
          ? calculateDiscountPercentage(validRegular, validDiscount)
          : null,
    };
  }, [watchedIsFree, watchedRegularRupees, watchedDiscountRupees]);

  const fieldErrorMessages = useMemo(() => {
    return Object.entries(errors)
      .map(([, err]) => err?.message)
      .filter((msg): msg is string => Boolean(msg));
  }, [errors]);

  const onValidSubmit = async (values: CourseMetadataFormValues) => {
    setServerError(null);
    setSaveState("saving");

    const pricing = buildCoursePricingPayload(values);
    const payloadBase = {
      title: values.title.trim(),
      slug: values.slug.trim().toLowerCase(),
      headline: values.headline.trim() || null,
      description: values.description.trim() || null,
      thumbnail_url: values.thumbnail_url.trim() || null,
      thumbnail_media_id: values.thumbnail_media_id || null,
      category: values.category.trim(),
      difficulty_level: values.difficulty_level,
      language: values.language.trim(),
      learning_outcomes: values.learning_outcomes.map((s) => s.trim()).filter(Boolean),
      requirements: values.requirements.map((s) => s.trim()).filter(Boolean),
      tags: Array.from(new Set(values.tags.map((t) => t.trim().toLowerCase()).filter(Boolean))),
      is_free: pricing.is_free,
      price_inr: pricing.price_inr,
      compare_at_price_inr: pricing.compare_at_price_inr,
      currency: "INR",
    };

    try {
      let savedCourse: CourseDetail;
      if (mode === "create") {
        savedCourse = await coursesApi.createCourse(payloadBase);
        toast.success(`Draft course "${savedCourse.title}" created successfully!`);
      } else {
        if (!courseId) {
          throw new Error("Missing courseId for course update.");
        }
        savedCourse = await coursesApi.updateCourse(courseId, payloadBase);
        reset(mapCourseToFormValues(savedCourse));
        toast.success("Course metadata saved successfully.");
      }
      setSaveState("saved");
      onSaved?.(savedCourse);
    } catch (err) {
      const apiErr = parseApiError(err);
      setSaveState("error");
      setServerError({
        message: apiErr.message,
        code: apiErr.code,
        requestId: apiErr.requestId,
      });

      if (apiErr.code === "COURSE_SLUG_EXISTS") {
        setError("slug", {
          type: "server",
          message: apiErr.message,
        });
      }
      toast.error(apiErr.message || "Could not save course.");
      errorSummaryRef.current?.focus();
    }
  };

  const onInvalidSubmit = () => {
    setSaveState("error");
    window.setTimeout(() => {
      errorSummaryRef.current?.focus();
    }, 0);
  };

  const titleField = register("title");
  const slugField = register("slug");

  return (
    <form
      onSubmit={handleSubmit(onValidSubmit, onInvalidSubmit)}
      className="space-y-6"
      noValidate
    >
      {/* Persistent Save Status Banner */}
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2.5 text-sm">
          {saveState === "saving" ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-mint px-3 py-1 text-xs font-semibold text-brand-teal">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving changes…
            </span>
          ) : saveState === "error" ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 border border-rose-200">
              <AlertTriangle className="h-3.5 w-3.5" />
              Saving failed — review fields below
            </span>
          ) : isDirty ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800 border border-amber-200">
              <AlertTriangle className="h-3.5 w-3.5" />
              Unsaved changes
            </span>
          ) : saveState === "saved" ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Saved
            </span>
          ) : (
            <span className="text-xs font-medium text-slate-500">
              {mode === "create"
                ? "Fill out your course metadata to save an initial draft."
                : "Edits update container metadata cleanly without mutating live snapshots."}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {onCancel && (
            <Button type="button" variant="outline" size="sm" onClick={onCancel} className="min-h-[40px]">
              Cancel
            </Button>
          )}
          <Button
            type="submit"
            variant="primary"
            size="sm"
            isLoading={isSubmitting || saveState === "saving"}
            disabled={isSubmitting || slugAvailability.status === "unavailable"}
            className="min-h-[40px]"
          >
            <Save className="mr-1.5 h-4 w-4" />
            {mode === "create" ? "Save Draft Course" : "Save Course Changes"}
          </Button>
        </div>
      </div>

      {/* Accessible Validation & Server Error Summary */}
      {(serverError || fieldErrorMessages.length > 0) && (
        <div
          ref={errorSummaryRef}
          tabIndex={-1}
          role="alert"
          aria-live="assertive"
          className="space-y-3 focus:outline-none"
        >
          {serverError && (
            <ErrorAlert
              title="Unable to save course"
              message={serverError.message}
              requestId={serverError.requestId}
            />
          )}
          {fieldErrorMessages.length > 0 && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50/90 p-4 text-rose-900">
              <h3 className="text-sm font-semibold text-rose-900">
                Please fix {fieldErrorMessages.length} field{" "}
                {fieldErrorMessages.length === 1 ? "issue" : "issues"} before saving:
              </h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-rose-800">
                {fieldErrorMessages.map((msg, idx) => (
                  <li key={`${msg}-${idx}`}>{msg}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Section A: Basic Course Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BookOpen className="h-5 w-5 text-brand-teal" />
            Basic Course Information
          </CardTitle>
          <CardDescription>
            Core identity, URL slug, catalog description, category, and discovery tags.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Input
            id="course-title"
            label="Course Title *"
            placeholder="e.g., Master Class: Modern Scalable Architecture"
            maxLength={255}
            error={errors.title?.message}
            helperText="3–255 characters. Displayed across your course catalog, player, and checkout."
            {...titleField}
          />

          {/* Slug field with auto/manual switch & availability indicator */}
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="course-slug" className="text-sm font-medium text-slate-700">
                Course URL Slug *
              </label>
              {slugManuallyEdited && (
                <button
                  type="button"
                  onClick={() => {
                    setSlugManuallyEdited(false);
                    const generated = slugifyCourseTitle(watchedTitle || "");
                    setValue("slug", generated, { shouldValidate: true, shouldDirty: true });
                  }}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-brand-teal hover:bg-brand-mint/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  Auto-generate from title
                </button>
              )}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Input
                  id="course-slug"
                  placeholder="system-design-distributed-backend"
                  maxLength={255}
                  error={
                    errors.slug?.message ||
                    (slugAvailability.status === "unavailable"
                      ? slugAvailability.reason || "This slug is already taken."
                      : undefined)
                  }
                  {...slugField}
                  onChange={(e) => {
                    setSlugManuallyEdited(true);
                    slugField.onChange(e);
                  }}
                />
              </div>
              <div className="shrink-0 sm:self-start sm:pt-2.5">
                {slugAvailability.status === "checking" && (
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Checking slug…
                  </span>
                )}
                {slugAvailability.status === "available" && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Available
                  </span>
                )}
              </div>
            </div>
            <p className="text-xs text-slate-500">
              Public link preview: <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">/courses/{watchedSlug || "your-course-slug"}</code>
            </p>
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label htmlFor="course-headline" className="text-sm font-medium text-slate-700">
                Short Subtitle / Headline
              </label>
              <span className="text-xs text-slate-500">
                {(watchedHeadline || "").length} / 512
              </span>
            </div>
            <Input
              id="course-headline"
              placeholder="A crisp one-line value proposition shown on catalog cards"
              maxLength={512}
              error={errors.headline?.message}
              {...register("headline")}
            />
          </div>

          <Textarea
            id="course-description"
            label="Full Course Description"
            rows={6}
            placeholder="Describe who this course is for, architectural topics covered, real-world outcomes, and teaching approach…"
            maxLength={20000}
            error={errors.description?.message}
            helperText="Supports clear multi-paragraph descriptions. HTML/script tags are stripped automatically for safety."
            {...register("description")}
          />

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {/* Category Selection */}
            <div className="space-y-2">
              <label htmlFor="course-category" className="block text-sm font-medium text-slate-700">
                Category *
              </label>
              {!customCategoryMode ? (
                <div className="space-y-2">
                  <select
                    id="course-category"
                    value={watchedCategory}
                    onChange={(e) => {
                      if (e.target.value === "__custom__") {
                        setCustomCategoryMode(true);
                        setValue("category", "", { shouldDirty: true, shouldValidate: false });
                      } else {
                        setValue("category", e.target.value, {
                          shouldDirty: true,
                          shouldValidate: true,
                        });
                      }
                    }}
                    className="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
                  >
                    {categoryChoices.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                    <option value="__custom__">+ Custom Category…</option>
                  </select>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Input
                    id="course-category-custom"
                    placeholder="Enter custom category"
                    maxLength={64}
                    error={errors.category?.message}
                    {...register("category")}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setCustomCategoryMode(false);
                      if (!watchedCategory?.trim()) {
                        setValue("category", "General", { shouldValidate: true, shouldDirty: true });
                      }
                    }}
                    className="min-h-[44px] shrink-0"
                  >
                    Presets
                  </Button>
                </div>
              )}
              {!customCategoryMode && errors.category?.message && (
                <p role="alert" className="text-xs font-medium text-rose-600">
                  {errors.category.message}
                </p>
              )}
            </div>

            {/* Tags Input */}
            <div>
              <TagInputField
                id="course-tags"
                label="Discovery Tags"
                tags={watchedTags || []}
                onChange={(nextTags) =>
                  setValue("tags", nextTags, { shouldDirty: true, shouldValidate: true })
                }
                error={errors.tags?.message}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section B: Course Thumbnail */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Sparkles className="h-5 w-5 text-brand-coral" />
            Course Thumbnail
          </CardTitle>
          <CardDescription>
            Upload a verified JPEG, PNG, or WebP cover image or link an HTTPS asset URL.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ThumbnailUploadCard
            thumbnailUrl={watchedThumbUrl || ""}
            thumbnailMediaId={watchedThumbMediaId ?? null}
            courseTitle={watchedTitle || ""}
            error={errors.thumbnail_url?.message}
            onChange={({ thumbnailUrl, thumbnailMediaId }) => {
              setValue("thumbnail_url", thumbnailUrl, { shouldDirty: true, shouldValidate: true });
              setValue("thumbnail_media_id", thumbnailMediaId, { shouldDirty: true });
            }}
          />
        </CardContent>
      </Card>

      {/* Section C: Course Level & Language */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Layers className="h-5 w-5 text-brand-teal" />
            Course Level & Language
          </CardTitle>
          <CardDescription>
            Help prospective students gauge instructional pace and delivery language.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="course-difficulty" className="block text-sm font-medium text-slate-700">
                Difficulty Level *
              </label>
              <select
                id="course-difficulty"
                aria-invalid={!!errors.difficulty_level}
                className="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
                {...register("difficulty_level")}
              >
                {difficultyChoices.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {errors.difficulty_level?.message && (
                <p role="alert" className="text-xs font-medium text-rose-600">
                  {errors.difficulty_level.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <label htmlFor="course-language" className="block text-sm font-medium text-slate-700">
                Primary Instruction Language *
              </label>
              <select
                id="course-language"
                aria-invalid={!!errors.language}
                className="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
                {...register("language")}
              >
                {languageChoices.map((lang) => (
                  <option key={lang} value={lang}>
                    {lang}
                  </option>
                ))}
              </select>
              {errors.language?.message && (
                <p role="alert" className="text-xs font-medium text-rose-600">
                  {errors.language.message}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section D: What You Will Learn */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <ListChecks className="h-5 w-5 text-brand-teal" />
            What You Will Learn
          </CardTitle>
          <CardDescription>
            Concrete skills and takeaways students achieve after completing this course.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <StringListEditor
            id="course-learning-outcomes"
            label="Learning Outcomes"
            description="Order items from foundational to advanced using the arrow controls."
            items={watchedOutcomes || []}
            onChange={(next) =>
              setValue("learning_outcomes", next, { shouldDirty: true, shouldValidate: true })
            }
            placeholder="e.g., Design fault-tolerant APIs with idempotency keys"
            addLabel="Add Outcome"
            itemNoun="Learning outcome"
            error={errors.learning_outcomes?.message}
          />
        </CardContent>
      </Card>

      {/* Section E: Course Requirements / Prerequisites */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Tag className="h-5 w-5 text-brand-coral" />
            Course Requirements / Prerequisites
          </CardTitle>
          <CardDescription>
            Prior knowledge, software, or tools students should have before starting.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <StringListEditor
            id="course-requirements"
            label="Course Requirements"
            description="Keep prerequisites clear and realistic so students feel confident enrolling."
            items={watchedRequirements || []}
            onChange={(next) =>
              setValue("requirements", next, { shouldDirty: true, shouldValidate: true })
            }
            placeholder="e.g., Basic familiarity with HTTP APIs and SQL queries"
            addLabel="Add Requirement"
            itemNoun="Requirement"
            error={errors.requirements?.message}
          />
        </CardContent>
      </Card>

      {/* Section F: Pricing Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <IndianRupee className="h-5 w-5 text-brand-teal" />
            Pricing Configuration (INR)
          </CardTitle>
          <CardDescription>
            Configure direct-to-student INR pricing or mark the course free for open enrollment.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <label
            htmlFor="course-is-free"
            className="flex cursor-pointer items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-brand-cream/50 p-4 transition-colors hover:border-brand-teal/40"
          >
            <div>
              <span className="block text-sm font-semibold text-slate-900">
                Free Course
              </span>
              <span className="block text-xs text-slate-600">
                Students can enroll at ₹0 without Razorpay checkout.
              </span>
            </div>
            <input
              id="course-is-free"
              type="checkbox"
              checked={Boolean(watchedIsFree)}
              onChange={(e) => {
                const checked = e.target.checked;
                setValue("is_free", checked, { shouldDirty: true, shouldValidate: true });
                if (checked) {
                  setValue("regular_price_rupees", "", { shouldDirty: true, shouldValidate: true });
                  setValue("discounted_price_rupees", "", { shouldDirty: true, shouldValidate: true });
                }
              }}
              className="h-5 w-5 rounded border-slate-300 text-brand-teal focus:ring-brand-teal"
            />
          </label>

          {!watchedIsFree && (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Input
                id="course-regular-price"
                label="Regular Price (INR) *"
                type="text"
                inputMode="decimal"
                placeholder="e.g., 7999"
                error={errors.regular_price_rupees?.message}
                helperText="Standard price in Indian Rupees (stored safely as integer paise)."
                {...register("regular_price_rupees")}
              />

              <Input
                id="course-discounted-price"
                label="Discounted Selling Price (INR, optional)"
                type="text"
                inputMode="decimal"
                placeholder="e.g., 2999"
                error={errors.discounted_price_rupees?.message}
                helperText="Must be lower than Regular Price to show a launch discount."
                {...register("discounted_price_rupees")}
              />
            </div>
          )}

          {/* Live Commercial Pricing Preview */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Student Checkout Price Preview (INR)
                </p>
                <div className="mt-1 flex flex-wrap items-baseline gap-2.5">
                  {pricingPreview.isFree ? (
                    <span className="text-xl font-bold text-emerald-700">Free (₹0)</span>
                  ) : (
                    <>
                      <span className="text-xl font-bold text-slate-900">
                        {formatInrFromPaise(pricingPreview.effectivePaise)}
                      </span>
                      {pricingPreview.discountPct !== null && pricingPreview.regularPaise !== null && (
                        <>
                          <span className="text-sm text-slate-400 line-through">
                            {formatInrFromPaise(pricingPreview.regularPaise)}
                          </span>
                          <span className="rounded-full bg-brand-peach px-2.5 py-0.5 text-xs font-bold text-rose-700">
                            {pricingPreview.discountPct}% OFF
                          </span>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>

              <span className="rounded-xl bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 border border-slate-200">
                Currency: INR (₹)
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Bottom Sticky/Accessible Form Actions */}
      <div className="flex flex-col-reverse gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-500">
          {isDirty
            ? "You have unsaved metadata changes."
            : "All metadata fields match the latest saved version."}
        </p>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {onCancel && (
            <Button type="button" variant="outline" onClick={onCancel} className="min-h-[44px]">
              Cancel
            </Button>
          )}
          <Button
            type="submit"
            variant="primary"
            isLoading={isSubmitting || saveState === "saving"}
            disabled={isSubmitting || slugAvailability.status === "unavailable"}
            className="min-h-[44px]"
          >
            <Save className="mr-2 h-4 w-4" />
            {mode === "create" ? "Create Draft Course" : "Save Course Metadata"}
          </Button>
        </div>
      </div>
    </form>
  );
};
