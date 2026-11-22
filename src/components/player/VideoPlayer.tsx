"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { AlertCircle, Play, Pause, RefreshCw, Volume2, VolumeX, Maximize } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { mediaApi } from "@/lib/api/media";
import { progressApi } from "@/lib/api/progress";
import { useAuth } from "@/lib/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

interface VideoPlayerProps {
  mediaId: string;
  lessonId: string;
  courseId: string;
  initialWatchSeconds?: number;
  onCompleted?: () => void;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  mediaId,
  lessonId,
  courseId,
  initialWatchSeconds = 0,
  onCompleted,
}) => {
  const { user } = useAuth();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasCompleted, setHasCompleted] = useState(false);
  const lastHeartbeatRef = useRef<number>(0);
  const completedSentRef = useRef<boolean>(false);

  // 1. Authoritative signed playback token
  const {
    data: tokenData,
    isLoading: isTokenLoading,
    isError: isTokenError,
    error: tokenError,
    refetch: refetchToken,
  } = useQuery({
    queryKey: ["playback-token", mediaId, lessonId],
    queryFn: () =>
      mediaApi.getPlaybackToken(mediaId, {
        lesson_id: lessonId,
        course_id: courseId,
      }),
    enabled: !!mediaId && !!lessonId,
    staleTime: 60 * 60 * 1000, // 1 hour token cache
    retry: 1,
  });

  // Heartbeat sender
  const sendHeartbeat = useCallback(
    async (seconds: number, isFinished = false) => {
      try {
        const res = await progressApi.recordLessonProgress(lessonId, {
          watch_position_seconds: Math.floor(seconds),
          is_completed: isFinished ? true : undefined,
        });
        if (res.is_completed && !hasCompleted) {
          setHasCompleted(true);
          onCompleted?.();
        }
      } catch (err) {
        // Heartbeat failure should not disrupt video viewing
        console.warn("Heartbeat sync warning:", err);
      }
    },
    [lessonId, hasCompleted, onCompleted]
  );

  // Time update handler with debounced 10s heartbeat and 90% threshold check
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;

    const current = video.currentTime;
    const duration = video.duration;

    // Check 90% completion threshold
    if (duration > 0 && current / duration >= 0.9 && !completedSentRef.current) {
      completedSentRef.current = true;
      sendHeartbeat(current, true);
    }

    // Periodic heartbeat every 10 seconds
    const now = Date.now();
    if (now - lastHeartbeatRef.current >= 10_000) {
      lastHeartbeatRef.current = now;
      sendHeartbeat(current, false);
    }
  };

  // Restore initial watch position
  useEffect(() => {
    const video = videoRef.current;
    if (video && initialWatchSeconds > 0) {
      video.currentTime = initialWatchSeconds;
    }
  }, [initialWatchSeconds, tokenData?.stream_url]);

  if (isTokenLoading) {
    return (
      <div className="relative aspect-video w-full overflow-hidden rounded-[12px] bg-slate-900 flex items-center justify-center">
        <Skeleton className="h-full w-full bg-slate-800" />
        <div className="absolute flex flex-col items-center gap-2 text-white">
          <RefreshCw className="h-6 w-6 animate-spin text-primary-teal" />
          <span className="font-mono text-xs text-slate-300">
            Authorizing secure video stream...
          </span>
        </div>
      </div>
    );
  }

  if (isTokenError || !tokenData) {
    return (
      <div className="aspect-video w-full rounded-[12px] bg-slate-900 p-6 flex flex-col items-center justify-center text-center">
        <div className="max-w-md space-y-3">
          <ErrorAlert
            title="Video Playback Unauthorized or Unavailable"
            message={
              tokenError?.message ||
              "Could not authorize video playback token. Please verify your enrollment."
            }
            onRetry={() => refetchToken()}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-[12px] bg-black shadow-lg group">
      <video
        ref={videoRef}
        src={tokenData.stream_url}
        controls
        playsInline
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onTimeUpdate={handleTimeUpdate}
        className="h-full w-full object-contain"
        preload="metadata"
      />

      {/* Dynamic Security Watermark (Anti-screen-recording) */}
      <div className="pointer-events-none absolute bottom-4 right-4 z-10 select-none opacity-20 font-mono text-[10px] text-white">
        <span>{user?.email || "Student"}</span>
        <span className="ml-1.5">{new Date().toISOString().slice(0, 10)}</span>
      </div>
    </div>
  );
};
