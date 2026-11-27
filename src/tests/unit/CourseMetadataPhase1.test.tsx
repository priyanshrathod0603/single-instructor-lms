import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CourseMetadataForm } from "@/components/admin/course-form";
import AdminCoursesPage from "@/app/(admin)/admin/courses/page";
import { coursesApi } from "@/lib/api/courses";
import { mediaApi } from "@/lib/api/media";
import {
  buildCoursePricingPayload,
  calculateDiscountPercentage,
  parseRupeesToPaise,
  slugifyCourseTitle,
} from "@/lib/validation/courseForm";
import { CourseDetail } from "@/types/course";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/admin/courses",
}));

vi.mock("@/lib/api/courses", () => ({
  coursesApi: {
    getMetadataOptions: vi.fn(),
    checkSlugAvailability: vi.fn(),
    createCourse: vi.fn(),
    updateCourse: vi.fn(),
    listManageCourses: vi.fn(),
    createRevision: vi.fn(),
    archiveCourse: vi.fn(),
    getCourseDetail: vi.fn(),
  },
}));

vi.mock("@/lib/api/media", () => ({
  mediaApi: {
    uploadCourseThumbnail: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const DEFAULT_METADATA_OPTIONS = {
  categories: ["Web Development", "System Design", "General"],
  difficulty_levels: [
    { value: "BEGINNER", label: "Beginner" },
    { value: "INTERMEDIATE", label: "Intermediate" },
    { value: "ADVANCED", label: "Advanced" },
    { value: "ALL_LEVELS", label: "All Levels" },
  ],
  languages: ["English", "Hindi", "Hinglish"],
  currencies: ["INR"],
};

const SAMPLE_COURSE: CourseDetail = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "distributed-systems-mastery",
  title: "Distributed Systems Mastery",
  headline: "Architect resilient high-throughput services",
  description: "Full engineering deep dive.",
  thumbnail_url: "/api/v1/media/public/22222222-2222-2222-2222-222222222222",
  thumbnail_media_id: "22222222-2222-2222-2222-222222222222",
  category: "System Design",
  difficulty_level: "INTERMEDIATE",
  language: "Hinglish",
  learning_outcomes: ["Design consensus algorithms", "Scale PostgreSQL"],
  requirements: ["HTTP basics", "Basic Linux CLI"],
  status: "DRAFT",
  price_inr: 299900,
  compare_at_price_inr: 799900,
  currency: "INR",
  discount_percentage: 63,
  is_free: false,
  tags: ["postgres", "distributed"],
  created_at: "2026-11-26T10:00:00Z",
  updated_at: "2026-11-26T12:00:00Z",
  curriculum: [],
};

describe("Phase 1: Course Metadata Validation Helpers", () => {
  it("slugifies titles and parses rupees to integer paise cleanly", () => {
    expect(slugifyCourseTitle("  Next.js & FastAPI 2026! ")).toBe("nextjs-fastapi-2026");
    expect(parseRupeesToPaise("2999")).toBe(299900);
    expect(parseRupeesToPaise("2999.50")).toBe(299950);
    expect(calculateDiscountPercentage(799900, 299900)).toBe(63);
    expect(
      buildCoursePricingPayload({
        is_free: false,
        regular_price_rupees: "7999",
        discounted_price_rupees: "2999",
      }),
    ).toEqual({
      is_free: false,
      price_inr: 299900,
      compare_at_price_inr: 799900,
    });
  });
});

describe("Phase 1: CourseMetadataForm Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(coursesApi.getMetadataOptions).mockResolvedValue(DEFAULT_METADATA_OPTIONS);
    vi.mocked(coursesApi.checkSlugAvailability).mockResolvedValue({
      slug: "test-slug",
      available: true,
      reason: null,
    });
  });

  it("renders all 6 required course creation sections", async () => {
    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    expect(screen.getByText("Basic Course Information")).toBeInTheDocument();
    expect(screen.getByText("Course Thumbnail")).toBeInTheDocument();
    expect(screen.getByText("Course Level & Language")).toBeInTheDocument();
    expect(screen.getByText("What You Will Learn")).toBeInTheDocument();
    expect(screen.getByText("Course Requirements / Prerequisites")).toBeInTheDocument();
    expect(screen.getByText("Pricing Configuration (INR)")).toBeInTheDocument();
  });

  it("auto-generates slug while typing title and stops once manually edited", async () => {
    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const titleInput = screen.getByLabelText(/Course Title/i);
    const slugInput = screen.getByLabelText(/Course URL Slug/i) as HTMLInputElement;

    fireEvent.change(titleInput, { target: { value: "Advanced Backend Systems" } });
    await waitFor(() => {
      expect(slugInput.value).toBe("advanced-backend-systems");
    });

    fireEvent.change(slugInput, { target: { value: "custom-course-slug" } });
    fireEvent.change(titleInput, { target: { value: "Renamed Course Title" } });
    expect(slugInput.value).toBe("custom-course-slug");

    // Reset button restores auto-generation
    const resetBtn = screen.getByRole("button", { name: /Auto-generate from title/i });
    fireEvent.click(resetBtn);
    await waitFor(() => {
      expect(slugInput.value).toBe("renamed-course-title");
    });
  });

  it("blocks short/empty title submission and preserves user inputs on validation error", async () => {
    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const titleInput = screen.getByLabelText(/Course Title/i) as HTMLInputElement;
    const headlineInput = screen.getByLabelText(/Short Subtitle \/ Headline/i) as HTMLInputElement;

    fireEvent.change(titleInput, { target: { value: "Go" } });
    fireEvent.change(headlineInput, { target: { value: "Preserved headline text" } });
    fireEvent.submit(titleInput.closest("form")!);

    await waitFor(() => {
      expect(
        screen.getAllByText(/Course title must be at least 3 characters\./i).length,
      ).toBeGreaterThan(0);
    });
    expect(coursesApi.createCourse).not.toHaveBeenCalled();
    expect(headlineInput.value).toBe("Preserved headline text");
  });

  it("updates headline character counter accurately", () => {
    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const headlineInput = screen.getByLabelText(/Short Subtitle \/ Headline/i);
    fireEvent.change(headlineInput, { target: { value: "Production systems" } });
    expect(screen.getByText("18 / 512")).toBeInTheDocument();
  });

  it("allows selecting category, custom category, difficulty level, language, and tags", async () => {
    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const categorySelect = screen.getByLabelText(/^Category/i) as HTMLSelectElement;
    fireEvent.change(categorySelect, { target: { value: "System Design" } });
    expect(categorySelect.value).toBe("System Design");

    fireEvent.change(categorySelect, { target: { value: "__custom__" } });
    const customCat = await screen.findByPlaceholderText("Enter custom category");
    fireEvent.change(customCat, { target: { value: "Compilers & Runtimes" } });

    const diffSelect = screen.getByLabelText(/Difficulty Level/i) as HTMLSelectElement;
    fireEvent.change(diffSelect, { target: { value: "ADVANCED" } });
    expect(diffSelect.value).toBe("ADVANCED");

    const langSelect = screen.getByLabelText(/Primary Instruction Language/i) as HTMLSelectElement;
    fireEvent.change(langSelect, { target: { value: "Hinglish" } });
    expect(langSelect.value).toBe("Hinglish");

    const tagInput = screen.getByLabelText(/Discovery Tags/i);
    fireEvent.change(tagInput, { target: { value: "Rust" } });
    fireEvent.keyDown(tagInput, { key: "Enter" });
    expect(screen.getByText("#rust")).toBeInTheDocument();
  });

  it("adds, rejects empty/duplicate entries, reorders, and removes learning outcomes & requirements", () => {
    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const outcomeInput = screen.getByLabelText("Learning Outcomes");
    const addOutcomeBtn = screen.getByRole("button", { name: /Add Outcome/i });

    // Reject blank outcome
    fireEvent.click(addOutcomeBtn);
    expect(screen.getByText(/Enter a valid learning outcome before adding/i)).toBeInTheDocument();

    // Add two outcomes
    fireEvent.change(outcomeInput, { target: { value: "Master indexing" } });
    fireEvent.click(addOutcomeBtn);
    fireEvent.change(outcomeInput, { target: { value: "Benchmark throughput" } });
    fireEvent.click(addOutcomeBtn);

    // Reject duplicate (case-insensitive)
    fireEvent.change(outcomeInput, { target: { value: "master indexing" } });
    fireEvent.click(addOutcomeBtn);
    expect(screen.getByText(/That learning outcome is already listed/i)).toBeInTheDocument();

    // Reorder second outcome up
    const moveUpBtn = screen.getByRole("button", { name: /Move learning outcome 2 up/i });
    fireEvent.click(moveUpBtn);
    const firstItemInput = screen.getByLabelText("Learning outcome 1") as HTMLInputElement;
    expect(firstItemInput.value).toBe("Benchmark throughput");

    // Add and remove requirement
    const reqInput = screen.getByLabelText("Course Requirements");
    fireEvent.change(reqInput, { target: { value: "Basic SQL knowledge" } });
    fireEvent.click(screen.getByRole("button", { name: /Add Requirement/i }));
    expect((screen.getByLabelText("Requirement 1") as HTMLInputElement).value).toBe(
      "Basic SQL knowledge",
    );

    fireEvent.click(screen.getByRole("button", { name: /Remove requirement 1/i }));
    expect(screen.queryByLabelText("Requirement 1")).not.toBeInTheDocument();
  });

  it("handles Free Course toggle and validates discounted price <= regular price", async () => {
    vi.mocked(coursesApi.createCourse).mockResolvedValue({
      ...SAMPLE_COURSE,
      is_free: true,
      price_inr: 0,
      compare_at_price_inr: null,
    });

    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const regularInput = screen.getByLabelText(/Regular Price \(INR\)/i) as HTMLInputElement;
    const discountInput = screen.getByLabelText(/Discounted Selling Price/i) as HTMLInputElement;

    // Live discount calculation
    fireEvent.change(regularInput, { target: { value: "7999" } });
    fireEvent.change(discountInput, { target: { value: "2999" } });
    expect(screen.getByText("63% OFF")).toBeInTheDocument();
    expect(screen.getByText("₹2,999")).toBeInTheDocument();

    // Reject discounted price > regular price
    fireEvent.change(discountInput, { target: { value: "8500" } });
    fireEvent.change(screen.getByLabelText(/Course Title/i), {
      target: { value: "Valid Pricing Course" },
    });
    fireEvent.submit(regularInput.closest("form")!);

    await waitFor(() => {
      expect(
        screen.getAllByText(/Discounted price cannot exceed regular price\./i).length,
      ).toBeGreaterThan(0);
    });
    expect(coursesApi.createCourse).not.toHaveBeenCalled();

    // Toggle Free Course hides price inputs and resets pricing to Free (₹0)
    const freeCheckbox = screen.getByLabelText(/Free Course/i);
    fireEvent.click(freeCheckbox);
    expect(screen.getByText("Free (₹0)")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Regular Price \(INR\)/i)).not.toBeInTheDocument();

    fireEvent.submit(freeCheckbox.closest("form")!);
    await waitFor(() => {
      expect(coursesApi.createCourse).toHaveBeenCalledWith(
        expect.objectContaining({
          is_free: true,
          price_inr: 0,
          compare_at_price_inr: null,
        }),
      );
    });
  });

  it("validates thumbnail format/size locally and handles upload, replace, and remove", async () => {
    vi.mocked(mediaApi.uploadCourseThumbnail).mockResolvedValue({
      id: "media-thumb-1",
      uploader_id: "u1",
      filename: "thumb.png",
      file_key: "public-images/u1/thumb.png",
      bucket: "lms-media",
      mime_type: "image/png",
      file_size_bytes: 1200,
      status: "READY",
      public_url: "/api/v1/media/public/media-thumb-1",
      created_at: "2026-11-26T00:00:00Z",
      updated_at: "2026-11-26T00:00:00Z",
    });

    renderWithQueryClient(<CourseMetadataForm mode="create" />);
    const fileInput = screen.getByLabelText("Upload course thumbnail image");

    // Reject invalid MIME file
    const badFile = new File(["hello"], "evil.exe", { type: "application/x-msdownload" });
    fireEvent.change(fileInput, { target: { files: [badFile] } });
    expect(
      screen.getByText(/Unsupported image format\. Please choose a JPEG, PNG, or WebP file\./i),
    ).toBeInTheDocument();

    // Upload valid PNG file
    const validFile = new File([new Uint8Array([137, 80, 78, 71])], "cover.png", {
      type: "image/png",
    });
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    await waitFor(() => {
      expect(mediaApi.uploadCourseThumbnail).toHaveBeenCalledTimes(1);
      expect(screen.getByAltText(/Course thumbnail preview/i)).toBeInTheDocument();
    });

    // Remove thumbnail cleanly
    fireEvent.click(screen.getByRole("button", { name: /^Remove$/i }));
    expect(screen.queryByAltText(/Course thumbnail preview/i)).not.toBeInTheDocument();
  });

  it("preserves user form inputs when API save fails with server error", async () => {
    vi.mocked(coursesApi.createCourse).mockRejectedValue({
      status: 409,
      message: "Course with slug 'system-design' already exists.",
      code: "COURSE_SLUG_EXISTS",
    });

    renderWithQueryClient(<CourseMetadataForm mode="create" />);

    const titleInput = screen.getByLabelText(/Course Title/i) as HTMLInputElement;
    const descInput = screen.getByLabelText(/Full Course Description/i) as HTMLTextAreaElement;

    fireEvent.change(titleInput, { target: { value: "System Design" } });
    fireEvent.change(descInput, { target: { value: "Detailed module plan" } });
    fireEvent.click(screen.getByLabelText(/Free Course/i));

    fireEvent.submit(titleInput.closest("form")!);

    await waitFor(() => {
      expect(screen.getByText(/Saving failed/i)).toBeInTheDocument();
    });
    expect(titleInput.value).toBe("System Design");
    expect(descInput.value).toBe("Detailed module plan");
  });

  it("populates edit mode with saved metadata and submits PATCH updates", async () => {
    vi.mocked(coursesApi.updateCourse).mockResolvedValue({
      ...SAMPLE_COURSE,
      title: "Distributed Systems Mastery v2",
    });

    renderWithQueryClient(
      <CourseMetadataForm
        mode="edit"
        courseId={SAMPLE_COURSE.id}
        initialCourse={SAMPLE_COURSE}
      />,
    );

    expect((screen.getByLabelText(/Course Title/i) as HTMLInputElement).value).toBe(
      "Distributed Systems Mastery",
    );
    expect((screen.getByLabelText(/Regular Price \(INR\)/i) as HTMLInputElement).value).toBe(
      "7999",
    );
    expect((screen.getByLabelText(/Discounted Selling Price/i) as HTMLInputElement).value).toBe(
      "2999",
    );
    expect((screen.getByLabelText("Learning outcome 1") as HTMLInputElement).value).toBe(
      "Design consensus algorithms",
    );

    fireEvent.change(screen.getByLabelText(/Course Title/i), {
      target: { value: "Distributed Systems Mastery v2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save Course Changes/i }));

    await waitFor(() => {
      expect(coursesApi.updateCourse).toHaveBeenCalledWith(
        SAMPLE_COURSE.id,
        expect.objectContaining({
          title: "Distributed Systems Mastery v2",
          price_inr: 299900,
          compare_at_price_inr: 799900,
          category: "System Design",
          difficulty_level: "INTERMEDIATE",
          language: "Hinglish",
        }),
      );
    });
  });
});

describe("Phase 1: AdminCoursesPage Directory States & Actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(coursesApi.getMetadataOptions).mockResolvedValue(DEFAULT_METADATA_OPTIONS);
  });

  it("renders loading, empty, error with retry, and populated course states cleanly", async () => {
    // 1. Loading state
    vi.mocked(coursesApi.listManageCourses).mockReturnValueOnce(new Promise(() => {}));
    const { unmount } = renderWithQueryClient(<AdminCoursesPage />);
    expect(screen.getByText(/Loading course directory/i)).toBeInTheDocument();
    unmount();

    // 2. Error state with retry
    vi.mocked(coursesApi.listManageCourses).mockRejectedValueOnce(new Error("Network error"));
    const errRender = renderWithQueryClient(<AdminCoursesPage />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load courses/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
    errRender.unmount();

    // 3. Empty state
    vi.mocked(coursesApi.listManageCourses).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      per_page: 20,
      total_pages: 0,
    });
    const emptyRender = renderWithQueryClient(<AdminCoursesPage />);
    await waitFor(() => {
      expect(screen.getByText(/No Courses Created Yet/i)).toBeInTheDocument();
    });
    emptyRender.unmount();

    // 4. Success state showing metadata, pricing, discount, and modal archive confirmation
    vi.mocked(coursesApi.listManageCourses).mockResolvedValue({
      items: [SAMPLE_COURSE],
      total: 1,
      page: 1,
      per_page: 20,
      total_pages: 1,
    });
    vi.mocked(coursesApi.archiveCourse).mockResolvedValue({
      ...SAMPLE_COURSE,
      status: "ARCHIVED",
    });

    renderWithQueryClient(<AdminCoursesPage />);
    await waitFor(() => {
      expect(screen.getAllByText("Distributed Systems Mastery").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("₹2,999").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-63%").length).toBeGreaterThan(0);

    const archiveButtons = screen.getAllByRole("button", {
      name: /Archive Distributed Systems Mastery/i,
    });
    fireEvent.click(archiveButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(/Are you sure you want to archive/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Archive Course$/i }));

    await waitFor(() => {
      expect(coursesApi.archiveCourse).toHaveBeenCalledWith(SAMPLE_COURSE.id);
    });
  });
});
