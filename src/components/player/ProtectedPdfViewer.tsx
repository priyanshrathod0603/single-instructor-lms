"use client";

import React, { useState } from "react";
import { FileText, Shield, Maximize2, Minimize2, ExternalLink } from "lucide-react";
import { mediaApi } from "@/lib/api/media";
import { useAuth } from "@/lib/hooks/useAuth";
import { Button } from "@/components/ui/Button";

interface ProtectedPdfViewerProps {
  mediaId: string;
  lessonId?: string;
  title?: string;
}

export const ProtectedPdfViewer: React.FC<ProtectedPdfViewerProps> = ({
  mediaId,
  lessonId,
  title = "Protected Course Document",
}) => {
  const { user } = useAuth();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const streamUrl = mediaApi.getProtectedPdfStreamUrl(mediaId, lessonId);

  return (
    <div
      className={`rounded-[12px] border border-slate-200 bg-white shadow-card overflow-hidden transition-all duration-200 ${
        isFullscreen ? "fixed inset-4 z-50 flex flex-col bg-white" : ""
      }`}
    >
      {/* PDF Header Bar */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 text-primary-teal shrink-0" />
          <span className="font-heading text-sm font-bold text-slate-800 truncate">
            {title}
          </span>
          <span className="hidden sm:inline-flex items-center gap-1 font-mono text-[11px] text-slate-500 bg-slate-200/60 px-2 py-0.5 rounded-full">
            <Shield className="h-3 w-3 text-primary-teal" />
            Watermarked Document
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="h-8 px-2 text-xs"
            aria-label={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* Watermarked PDF Container */}
      <div className="relative flex-1 min-h-[500px] w-full bg-slate-100">
        <iframe
          src={`${streamUrl}#toolbar=0`}
          title={title}
          className="h-full w-full min-h-[500px] border-0"
        />

        {/* Security watermark footer */}
        <div className="border-t border-slate-200 bg-white/95 px-4 py-1.5 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>Protected Document • Licensed to {user?.email || "Student"}</span>
          <span>Copying or unauthorized redistribution prohibited</span>
        </div>
      </div>
    </div>
  );
};
