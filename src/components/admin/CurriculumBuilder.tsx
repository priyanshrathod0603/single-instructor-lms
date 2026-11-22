"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  Edit2,
  ChevronUp,
  ChevronDown,
  Film,
  FileText,
  HelpCircle,
  ClipboardList,
  Eye,
  GripVertical,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import {
  CourseRevision,
  CurriculumLesson,
  CurriculumSection,
  LessonType,
} from "@/types/course";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { LessonEditorModal } from "./LessonEditorModal";

interface CurriculumBuilderProps {
  courseId: string;
  revision: CourseRevision;
}

export const CurriculumBuilder: React.FC<CurriculumBuilderProps> = ({
  courseId,
  revision,
}) => {
  const queryClient = useQueryClient();
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const [isAddingSection, setIsAddingSection] = useState(false);

  // Lesson creation state
  const [activeSectionIdForLesson, setActiveSectionIdForLesson] = useState<string | null>(null);
  const [newLessonTitle, setNewLessonTitle] = useState("");
  const [newLessonType, setNewLessonType] = useState<LessonType>("VIDEO");

  // Lesson editing state
  const [editingLesson, setEditingLesson] = useState<CurriculumLesson | null>(null);

  // Mutations
  const addSectionMutation = useMutation({
    mutationFn: () =>
      coursesApi.createSection(courseId, revision.id, {
        title: newSectionTitle,
        sort_order: revision.sections?.length || 0,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
      setNewSectionTitle("");
      setIsAddingSection(false);
    },
  });

  const deleteSectionMutation = useMutation({
    mutationFn: (sectionId: string) => coursesApi.deleteSection(sectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
    },
  });

  const reorderSectionsMutation = useMutation({
    mutationFn: (items: Array<{ id: string; sort_order: number }>) =>
      coursesApi.reorderSections(courseId, revision.id, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
    },
  });

  const addLessonMutation = useMutation({
    mutationFn: () => {
      if (!activeSectionIdForLesson) throw new Error("No section selected");
      return coursesApi.createLesson(activeSectionIdForLesson, {
        title: newLessonTitle,
        lesson_type: newLessonType,
        sort_order: 99,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
      setActiveSectionIdForLesson(null);
      setNewLessonTitle("");
    },
  });

  const deleteLessonMutation = useMutation({
    mutationFn: (lessonId: string) => coursesApi.deleteLesson(lessonId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
    },
  });

  const reorderLessonsMutation = useMutation({
    mutationFn: ({ sectionId, items }: { sectionId: string; items: Array<{ id: string; sort_order: number }> }) =>
      coursesApi.reorderLessons(sectionId, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
    },
  });

  const moveSection = (index: number, direction: "up" | "down") => {
    const sections = [...(revision.sections || [])];
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= sections.length) return;

    const temp = sections[index];
    sections[index] = sections[targetIndex];
    sections[targetIndex] = temp;

    const items = sections.map((sec, idx) => ({ id: sec.id, sort_order: idx }));
    reorderSectionsMutation.mutate(items);
  };

  const moveLesson = (section: CurriculumSection, lessonIndex: number, direction: "up" | "down") => {
    const lessons = [...(section.lessons || [])];
    const targetIndex = direction === "up" ? lessonIndex - 1 : lessonIndex + 1;
    if (targetIndex < 0 || targetIndex >= lessons.length) return;

    const temp = lessons[lessonIndex];
    lessons[lessonIndex] = lessons[targetIndex];
    lessons[targetIndex] = temp;

    const items = lessons.map((les, idx) => ({ id: les.id, sort_order: idx }));
    reorderLessonsMutation.mutate({ sectionId: section.id, items });
  };

  const getLessonIcon = (type: LessonType) => {
    switch (type) {
      case "VIDEO":
        return <Film className="h-4 w-4 text-teal-600" />;
      case "ARTICLE":
        return <FileText className="h-4 w-4 text-coral-orange" />;
      case "QUIZ":
        return <HelpCircle className="h-4 w-4 text-purple-600" />;
      case "ASSIGNMENT":
        return <ClipboardList className="h-4 w-4 text-amber-600" />;
      default:
        return <FileText className="h-4 w-4 text-slate-500" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Sections List */}
      <div className="space-y-4">
        {(!revision.sections || revision.sections.length === 0) && (
          <div className="rounded-[16px] border border-dashed border-slate-300 bg-white p-10 text-center">
            <h3 className="font-heading text-base font-bold text-slate-800">No Curriculum Sections</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
              Build your course curriculum by adding sequential sections and pedagogical lessons.
            </p>
          </div>
        )}

        {revision.sections?.map((section, sIndex) => (
          <div
            key={section.id}
            className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden"
          >
            {/* Section Header */}
            <div className="flex items-center justify-between bg-slate-50/80 px-6 py-4 border-b border-slate-200">
              <div className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-700">
                  {sIndex + 1}
                </span>
                <h3 className="font-heading font-bold text-base text-slate-900">{section.title}</h3>
                <span className="text-xs text-slate-500">
                  ({section.lessons?.length || 0} lessons)
                </span>
              </div>

              {/* Section Controls */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label="Move Section Up"
                  disabled={sIndex === 0}
                  onClick={() => moveSection(sIndex, "up")}
                  className="p-1.5 text-slate-400 hover:text-slate-800 disabled:opacity-30 rounded"
                >
                  <ChevronUp className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="Move Section Down"
                  disabled={sIndex === (revision.sections?.length || 0) - 1}
                  onClick={() => moveSection(sIndex, "down")}
                  className="p-1.5 text-slate-400 hover:text-slate-800 disabled:opacity-30 rounded"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="Delete Section"
                  onClick={() => {
                    if (window.confirm(`Delete section "${section.title}" and all its lessons?`)) {
                      deleteSectionMutation.mutate(section.id);
                    }
                  }}
                  className="p-1.5 text-slate-400 hover:text-rose-600 rounded ml-2"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Lessons List inside Section */}
            <div className="p-4 space-y-2">
              {section.lessons?.map((lesson, lIndex) => (
                <div
                  key={lesson.id}
                  className="flex items-center justify-between rounded-[12px] border border-slate-100 bg-slate-50/50 p-3 hover:bg-slate-50 hover:border-slate-200 transition-all"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-1.5 rounded-lg bg-white border border-slate-200 shrink-0">
                      {getLessonIcon(lesson.lesson_type)}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-900 truncate">
                          {lesson.title}
                        </span>
                        {lesson.is_preview && (
                          <Badge variant="success" className="text-[10px] py-0 px-1.5">
                            Free Preview
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {lesson.lesson_type} · {lesson.duration_seconds || 0}s
                        {lesson.resources && lesson.resources.length > 0 && ` · ${lesson.resources.length} resources`}
                      </p>
                    </div>
                  </div>

                  {/* Lesson Controls */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      aria-label="Move Lesson Up"
                      disabled={lIndex === 0}
                      onClick={() => moveLesson(section, lIndex, "up")}
                      className="p-1.5 text-slate-400 hover:text-slate-800 disabled:opacity-30 rounded"
                    >
                      <ChevronUp className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      aria-label="Move Lesson Down"
                      disabled={lIndex === (section.lessons?.length || 0) - 1}
                      onClick={() => moveLesson(section, lIndex, "down")}
                      className="p-1.5 text-slate-400 hover:text-slate-800 disabled:opacity-30 rounded"
                    >
                      <ChevronDown className="h-4 w-4" />
                    </button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingLesson(lesson)}
                    >
                      <Edit2 className="h-3 w-3 mr-1.5" />
                      Edit
                    </Button>
                    <button
                      type="button"
                      aria-label="Delete Lesson"
                      onClick={() => {
                        if (window.confirm(`Delete lesson "${lesson.title}"?`)) {
                          deleteLessonMutation.mutate(lesson.id);
                        }
                      }}
                      className="p-1.5 text-slate-400 hover:text-rose-600 rounded ml-1"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}

              {/* Add Lesson Form / Trigger */}
              {activeSectionIdForLesson === section.id ? (
                <div className="rounded-[12px] border border-primary-teal/30 bg-teal-50/30 p-3 space-y-3">
                  <div className="flex flex-col sm:flex-row gap-2">
                    <Input
                      value={newLessonTitle}
                      onChange={(e) => setNewLessonTitle(e.target.value)}
                      placeholder="New lesson headline..."
                      className="flex-1 bg-white"
                      autoFocus
                    />
                    <select
                      value={newLessonType}
                      onChange={(e) => setNewLessonType(e.target.value as LessonType)}
                      className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                    >
                      <option value="VIDEO">Video Lesson</option>
                      <option value="ARTICLE">Article Lesson</option>
                      <option value="QUIZ">Quiz Assessment</option>
                      <option value="ASSIGNMENT">Assignment Project</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2 justify-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setActiveSectionIdForLesson(null);
                        setNewLessonTitle("");
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={!newLessonTitle.trim() || addLessonMutation.isPending}
                      isLoading={addLessonMutation.isPending}
                      onClick={() => addLessonMutation.mutate()}
                    >
                      Create Lesson
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveSectionIdForLesson(section.id)}
                  className="w-full justify-center text-slate-500 hover:text-primary-teal"
                >
                  <Plus className="h-3.5 w-3.5 mr-1.5" />
                  Add Lesson to Section
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Add New Section Block */}
      {isAddingSection ? (
        <div className="rounded-[16px] border border-slate-200 bg-white p-4 shadow-sm space-y-3">
          <h4 className="text-sm font-bold text-slate-900">Add New Curriculum Section</h4>
          <Input
            value={newSectionTitle}
            onChange={(e) => setNewSectionTitle(e.target.value)}
            placeholder="e.g. Module 1: Foundations & Architecture"
            autoFocus
          />
          <div className="flex items-center gap-2 justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setIsAddingSection(false);
                setNewSectionTitle("");
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!newSectionTitle.trim() || addSectionMutation.isPending}
              isLoading={addSectionMutation.isPending}
              onClick={() => addSectionMutation.mutate()}
            >
              Create Section
            </Button>
          </div>
        </div>
      ) : (
        <Button
          variant="outline"
          size="default"
          onClick={() => setIsAddingSection(true)}
          className="w-full justify-center py-4 border-dashed"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add New Curriculum Section
        </Button>
      )}

      {/* Dedicated Lesson Editor Modal */}
      {editingLesson && (
        <LessonEditorModal
          isOpen={!!editingLesson}
          onClose={() => setEditingLesson(null)}
          lesson={editingLesson}
          courseId={courseId}
        />
      )}
    </div>
  );
};
