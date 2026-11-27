"use client";

import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Film,
  FileText,
  HelpCircle,
  ClipboardList,
  Plus,
  Trash2,
  UploadCloud,
  Check,
  AlertCircle,
  X,
  Paperclip,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { quizzesApi } from "@/lib/api/quizzes";
import { assignmentsApi } from "@/lib/api/assignments";
import { CurriculumLesson, LessonType, ResourceType } from "@/types/course";
import { MediaAssetResponse, SUPPORTED_VIDEO_MIME_TYPES } from "@/types/media";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { MediaLibraryModal } from "./MediaLibraryModal";

interface LessonEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  lesson: CurriculumLesson | null;
  courseId: string;
}

export const LessonEditorModal: React.FC<LessonEditorModalProps> = ({
  isOpen,
  onClose,
  lesson,
  courseId,
}) => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"general" | "content" | "resources">("general");

  // General fields
  const [title, setTitle] = useState("");
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [isPreview, setIsPreview] = useState(false);

  // Video Content
  const [videoAssetId, setVideoAssetId] = useState<string | null>(null);
  const [videoFileKey, setVideoFileKey] = useState<string | null>(null);
  const [isMediaModalOpen, setIsMediaModalOpen] = useState(false);

  // Article Content
  const [markdownBody, setMarkdownBody] = useState("");

  // Quiz state
  const [quizPassPercentage, setQuizPassPercentage] = useState(80);
  const [quizTimeLimit, setQuizTimeLimit] = useState(15);
  const [csvContent, setCsvContent] = useState("");
  const [quizMessage, setQuizMessage] = useState<string | null>(null);

  // Assignment state
  const [assignmentInstructions, setAssignmentInstructions] = useState("");
  const [assignmentMaxScore, setAssignmentMaxScore] = useState(100);
  const [rubricTitle, setRubricTitle] = useState("Grading Rubric");
  const [rubricCriteria, setRubricCriteria] = useState<Array<{ title: string; max_points: number; weight: number }>>([
    { title: "Technical Correctness", max_points: 50, weight: 1 },
    { title: "Code Quality & Documentation", max_points: 50, weight: 1 },
  ]);
  const [assignmentMessage, setAssignmentMessage] = useState<string | null>(null);

  // Resource adding
  const [resourceTitle, setResourceTitle] = useState("");
  const [resourceType, setResourceType] = useState<ResourceType>("PDF");
  const [resourceFileUrl, setResourceFileUrl] = useState("");

  useEffect(() => {
    if (lesson) {
      setTitle(lesson.title);
      setDurationSeconds(lesson.duration_seconds || 0);
      setIsPreview(lesson.is_preview || false);

      const content =
        lesson.content && typeof lesson.content === "object" && !Array.isArray(lesson.content)
          ? lesson.content
          : {};
      const resolvedVideoId =
        (typeof content.media_asset_id === "string" && content.media_asset_id.trim()) ||
        (typeof content.media_id === "string" && content.media_id.trim()) ||
        (typeof content.video_id === "string" && content.video_id.trim()) ||
        null;
      setVideoAssetId(resolvedVideoId);
      setVideoFileKey((content.file_key as string) || null);
      setMarkdownBody((content.body as string) || (content.markdown as string) || "");
    }
  }, [lesson]);

  // Query Quiz details if lesson is QUIZ
  const { data: existingQuiz } = useQuery({
    queryKey: ["lesson-quiz", lesson?.id],
    queryFn: () => quizzesApi.getLessonQuiz(lesson!.id),
    enabled: isOpen && lesson?.lesson_type === "QUIZ",
    retry: false,
  });

  // Query Assignment details if lesson is ASSIGNMENT
  const { data: existingAssignment } = useQuery({
    queryKey: ["lesson-assignment", lesson?.id],
    queryFn: () => assignmentsApi.getLessonAssignment(lesson!.id),
    enabled: isOpen && lesson?.lesson_type === "ASSIGNMENT",
    retry: false,
  });

  useEffect(() => {
    setQuizMessage(null);
    setAssignmentMessage(null);
  }, [lesson?.id]);

  useEffect(() => {
    if (existingQuiz) {
      setQuizPassPercentage(existingQuiz.pass_percentage);
      setQuizTimeLimit(existingQuiz.time_limit_minutes);
    } else if (lesson?.lesson_type === "QUIZ") {
      setQuizPassPercentage(80);
      setQuizTimeLimit(15);
    }
  }, [existingQuiz, lesson?.id, lesson?.lesson_type]);

  useEffect(() => {
    if (existingAssignment) {
      setAssignmentInstructions(existingAssignment.instructions || "");
      setAssignmentMaxScore(existingAssignment.max_score ?? 100);
      if (existingAssignment.active_rubric) {
        setRubricTitle(existingAssignment.active_rubric.title || "Grading Rubric");
        if (existingAssignment.active_rubric.criteria?.length) {
          setRubricCriteria(
            existingAssignment.active_rubric.criteria.map((c) => ({
              title: c.title,
              max_points: c.max_points,
              weight: c.weight ?? 1,
            }))
          );
        }
      }
    } else if (lesson?.lesson_type === "ASSIGNMENT") {
      setAssignmentInstructions("");
      setAssignmentMaxScore(100);
      setRubricTitle("Grading Rubric");
      setRubricCriteria([
        { title: "Technical Correctness", max_points: 50, weight: 1 },
        { title: "Code Quality & Documentation", max_points: 50, weight: 1 },
      ]);
    }
  }, [existingAssignment, lesson?.id, lesson?.lesson_type]);

  const updateLessonMutation = useMutation({
    mutationFn: async () => {
      if (!lesson) return;
      const content: Record<string, unknown> = { ...(lesson.content || {}) };

      if (lesson.lesson_type === "VIDEO") {
        if (videoAssetId) content.media_asset_id = videoAssetId;
        if (videoFileKey) content.file_key = videoFileKey;
      } else if (lesson.lesson_type === "ARTICLE") {
        content.body = markdownBody;
      }

      await coursesApi.updateLesson(lesson.id, {
        title,
        duration_seconds: Number(durationSeconds),
        is_preview: isPreview,
        content,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision"] });
      onClose();
    },
  });

  const addResourceMutation = useMutation({
    mutationFn: () => {
      if (!lesson) throw new Error("No lesson");
      return coursesApi.createResource(lesson.id, {
        title: resourceTitle,
        resource_type: resourceType,
        file_url: resourceFileUrl,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision"] });
      setResourceTitle("");
      setResourceFileUrl("");
    },
  });

  const deleteResourceMutation = useMutation({
    mutationFn: (resourceId: string) => coursesApi.deleteResource(resourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision"] });
    },
  });

  const saveQuizMutation = useMutation({
    mutationFn: async () => {
      if (!lesson) return;
      let targetQuizId = existingQuiz?.id;
      if (!targetQuizId) {
        const createdQuiz = await quizzesApi.createQuiz(lesson.id, {
          title,
          pass_percentage: Number(quizPassPercentage),
          time_limit_minutes: Number(quizTimeLimit),
        });
        targetQuizId = createdQuiz.id;
      } else {
        await quizzesApi.updateQuiz(targetQuizId, {
          title,
          pass_percentage: Number(quizPassPercentage),
          time_limit_minutes: Number(quizTimeLimit),
        });
      }

      if (csvContent.trim() && targetQuizId) {
        await quizzesApi.bulkImportCsv(targetQuizId, csvContent);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lesson-quiz", lesson?.id] });
      setQuizMessage("Quiz successfully configured!");
      setCsvContent("");
    },
    onError: (err: any) => {
      setQuizMessage(err?.message || "Failed to update quiz.");
    },
  });

  const saveAssignmentMutation = useMutation({
    mutationFn: async () => {
      if (!lesson) return;
      let assignId = existingAssignment?.id;
      if (!assignId) {
        const created = await assignmentsApi.createAssignment(lesson.id, {
          title,
          instructions: assignmentInstructions,
          max_score: Number(assignmentMaxScore),
        });
        assignId = created.id;
      } else {
        await assignmentsApi.updateAssignment(assignId, {
          title,
          instructions: assignmentInstructions,
          max_score: Number(assignmentMaxScore),
        });
      }

      if (assignId && rubricCriteria.length > 0) {
        await assignmentsApi.createRubric(assignId, {
          title: rubricTitle,
          criteria: rubricCriteria.map((c, i) => ({
            title: c.title,
            max_points: Number(c.max_points),
            weight: Number(c.weight),
            sort_order: i,
          })),
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lesson-assignment", lesson?.id] });
      setAssignmentMessage("Assignment and rubric successfully saved!");
    },
    onError: (err: any) => {
      setAssignmentMessage(err?.message || "Failed to update assignment.");
    },
  });

  if (!isOpen || !lesson) return null;

  return (
    <>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="lesson-editor-title"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 sm:p-6"
      >
        <div className="relative w-full max-w-3xl max-h-[90vh] flex flex-col rounded-[16px] bg-white shadow-2xl border border-slate-200 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50">
            <div className="flex items-center gap-3">
              <Badge variant="outline">{lesson.lesson_type}</Badge>
              <h2 id="lesson-editor-title" className="font-heading text-lg font-bold text-slate-900 truncate">
                Edit Lesson: {lesson.title}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-700 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg"
              aria-label="Close modal"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Tab Navigation */}
          <div className="flex border-b border-slate-200 px-6 bg-white gap-6">
            <button
              onClick={() => setActiveTab("general")}
              className={`py-3 text-sm font-semibold border-b-2 transition-colors ${
                activeTab === "general"
                  ? "border-primary-teal text-primary-teal"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              General Settings
            </button>
            <button
              onClick={() => setActiveTab("content")}
              className={`py-3 text-sm font-semibold border-b-2 transition-colors ${
                activeTab === "content"
                  ? "border-primary-teal text-primary-teal"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {lesson.lesson_type === "VIDEO"
                ? "Video Media"
                : lesson.lesson_type === "ARTICLE"
                ? "Article Body"
                : lesson.lesson_type === "QUIZ"
                ? "Quiz Configuration"
                : "Assignment & Rubric"}
            </button>
            <button
              onClick={() => setActiveTab("resources")}
              className={`py-3 text-sm font-semibold border-b-2 transition-colors ${
                activeTab === "resources"
                  ? "border-primary-teal text-primary-teal"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Lesson Resources ({lesson.resources?.length || 0})
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {activeTab === "general" && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Lesson Title
                  </label>
                  <Input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Enter lesson title"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                      Estimated Duration (Seconds)
                    </label>
                    <Input
                      type="number"
                      value={durationSeconds}
                      onChange={(e) => setDurationSeconds(Number(e.target.value))}
                      placeholder="e.g. 600"
                    />
                  </div>

                  <div className="flex items-center gap-3 pt-6">
                    <input
                      type="checkbox"
                      id="is-preview-check"
                      checked={isPreview}
                      onChange={(e) => setIsPreview(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-primary-teal focus:ring-primary-teal"
                    />
                    <label htmlFor="is-preview-check" className="text-sm font-medium text-slate-700">
                      Enable Free Public Preview
                    </label>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "content" && (
              <div className="space-y-4">
                {lesson.lesson_type === "VIDEO" && (
                  <div className="space-y-4">
                    <div className="rounded-[12px] border border-slate-200 p-4 bg-slate-50">
                      <h4 className="text-sm font-bold text-slate-900 mb-1">Attached Video Asset</h4>
                      {videoAssetId ? (
                        <div className="flex items-center justify-between rounded-lg bg-white p-3 border border-slate-200 mt-2">
                          <div className="flex items-center gap-2">
                            <Film className="h-5 w-5 text-primary-teal" />
                            <div>
                              <p className="text-xs font-mono text-slate-800">Media ID: {videoAssetId}</p>
                              {videoFileKey && <p className="text-[11px] text-slate-500">{videoFileKey}</p>}
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setIsMediaModalOpen(true)}
                          >
                            Change Video
                          </Button>
                        </div>
                      ) : (
                        <div className="text-center py-6">
                          <Film className="mx-auto h-8 w-8 text-slate-400 mb-2" />
                          <p className="text-sm text-slate-600 mb-3">No video attached to this lesson yet.</p>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => setIsMediaModalOpen(true)}
                          >
                            <Film className="h-4 w-4 mr-2" />
                            Select Video from Library
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {lesson.lesson_type === "ARTICLE" && (
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                      Article Markdown Body
                    </label>
                    <Textarea
                      rows={12}
                      value={markdownBody}
                      onChange={(e) => setMarkdownBody(e.target.value)}
                      placeholder="Write comprehensive pedagogical article content here in Markdown format..."
                    />
                  </div>
                )}

                {lesson.lesson_type === "QUIZ" && (
                  <div className="space-y-4">
                    {quizMessage && (
                      <div className="p-3 rounded-lg bg-teal-50 border border-teal-200 text-teal-800 text-xs">
                        {quizMessage}
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                          Pass Percentage (%)
                        </label>
                        <Input
                          type="number"
                          value={quizPassPercentage}
                          onChange={(e) => setQuizPassPercentage(Number(e.target.value))}
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                          Time Limit (Minutes)
                        </label>
                        <Input
                          type="number"
                          value={quizTimeLimit}
                          onChange={(e) => setQuizTimeLimit(Number(e.target.value))}
                        />
                      </div>
                    </div>

                    <div className="rounded-[12px] border border-slate-200 p-4 bg-slate-50">
                      <h4 className="text-xs font-bold uppercase text-slate-700 mb-2">
                        Bulk Import Questions via CSV
                      </h4>
                      <p className="text-xs text-slate-500 mb-2">
                        Format: type,prompt,points,explanation,opt1:correct,opt2:incorrect
                      </p>
                      <Textarea
                        rows={4}
                        value={csvContent}
                        onChange={(e) => setCsvContent(e.target.value)}
                        placeholder="MCQ_SINGLE,What is React?,1,UI library,A library:true,A framework:false"
                      />
                      <div className="mt-3">
                        <Button
                          variant="secondary"
                          size="sm"
                          isLoading={saveQuizMutation.isPending}
                          onClick={() => saveQuizMutation.mutate()}
                        >
                          Save Quiz Settings & Import CSV
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                {lesson.lesson_type === "ASSIGNMENT" && (
                  <div className="space-y-4">
                    {assignmentMessage && (
                      <div className="p-3 rounded-lg bg-teal-50 border border-teal-200 text-teal-800 text-xs">
                        {assignmentMessage}
                      </div>
                    )}
                    <div>
                      <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                        Assignment Instructions & Prompt
                      </label>
                      <Textarea
                        rows={5}
                        value={assignmentInstructions}
                        onChange={(e) => setAssignmentInstructions(e.target.value)}
                        placeholder="Provide detailed instructions for the student's project submission..."
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold uppercase text-slate-700 mb-1">
                        Max Score Points
                      </label>
                      <Input
                        type="number"
                        value={assignmentMaxScore}
                        onChange={(e) => setAssignmentMaxScore(Number(e.target.value))}
                      />
                    </div>

                    <div className="rounded-[12px] border border-slate-200 p-4 bg-slate-50 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-bold uppercase text-slate-700">
                          Rubric Criteria ({rubricCriteria.length})
                        </h4>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setRubricCriteria([
                              ...rubricCriteria,
                              { title: "New Criterion", max_points: 25, weight: 1 },
                            ])
                          }
                        >
                          <Plus className="h-3 w-3 mr-1" />
                          Add Criterion
                        </Button>
                      </div>

                      {rubricCriteria.map((c, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <Input
                            value={c.title}
                            onChange={(e) => {
                              const updated = [...rubricCriteria];
                              updated[i].title = e.target.value;
                              setRubricCriteria(updated);
                            }}
                            className="flex-1"
                            placeholder="Criterion Title"
                          />
                          <Input
                            type="number"
                            value={c.max_points}
                            onChange={(e) => {
                              const updated = [...rubricCriteria];
                              updated[i].max_points = Number(e.target.value);
                              setRubricCriteria(updated);
                            }}
                            className="w-24"
                            placeholder="Points"
                          />
                          <button
                            type="button"
                            onClick={() => setRubricCriteria(rubricCriteria.filter((_, idx) => idx !== i))}
                            className="text-slate-400 hover:text-rose-600 p-2"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      ))}

                      <Button
                        variant="secondary"
                        size="sm"
                        isLoading={saveAssignmentMutation.isPending}
                        onClick={() => saveAssignmentMutation.mutate()}
                      >
                        Save Assignment & Rubric
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "resources" && (
              <div className="space-y-6">
                {/* Existing resources list */}
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase text-slate-700">Attached Resources</h4>
                  {!lesson.resources || lesson.resources.length === 0 ? (
                    <p className="text-xs text-slate-500 py-3">No supplementary resources attached.</p>
                  ) : (
                    lesson.resources.map((res) => (
                      <div
                        key={res.id}
                        className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-3"
                      >
                        <div className="flex items-center gap-2">
                          <Paperclip className="h-4 w-4 text-slate-500" />
                          <span className="text-sm font-medium text-slate-900">{res.title}</span>
                          <Badge variant="outline">{res.resource_type}</Badge>
                        </div>
                        <button
                          type="button"
                          onClick={() => deleteResourceMutation.mutate(res.id)}
                          className="text-slate-400 hover:text-rose-600 p-1 rounded"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>

                {/* Add new resource */}
                <div className="rounded-[12px] border border-slate-200 p-4 bg-slate-50 space-y-3">
                  <h4 className="text-xs font-bold uppercase text-slate-700">Add New Resource</h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <Input
                      value={resourceTitle}
                      onChange={(e) => setResourceTitle(e.target.value)}
                      placeholder="Resource Title (e.g. Lecture Slides PDF)"
                    />
                    <select
                      value={resourceType}
                      onChange={(e) => setResourceType(e.target.value as ResourceType)}
                      className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                    >
                      <option value="PDF">Protected PDF</option>
                      <option value="SOURCE_CODE">Source Code</option>
                      <option value="LINK">External Link</option>
                      <option value="ASSET">General Asset</option>
                    </select>
                  </div>
                  <Input
                    value={resourceFileUrl}
                    onChange={(e) => setResourceFileUrl(e.target.value)}
                    placeholder="File Key or Resource URL (e.g. lesson-resources/...)"
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!resourceTitle || !resourceFileUrl || addResourceMutation.isPending}
                    isLoading={addResourceMutation.isPending}
                    onClick={() => addResourceMutation.mutate()}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Attach Resource
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4 bg-slate-50">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={updateLessonMutation.isPending}
              onClick={() => updateLessonMutation.mutate()}
            >
              <Check className="h-4 w-4 mr-2" />
              Save Lesson Changes
            </Button>
          </div>
        </div>
      </div>

      {/* Nested Media Library Modal for picking video */}
      <MediaLibraryModal
        isOpen={isMediaModalOpen}
        onClose={() => setIsMediaModalOpen(false)}
        allowedMimeType={SUPPORTED_VIDEO_MIME_TYPES.join(",")}
        title="Select Video for Lesson"
        onSelect={(asset) => {
          setVideoAssetId(asset.id);
          setVideoFileKey(asset.file_key);
        }}
      />
    </>
  );
};
