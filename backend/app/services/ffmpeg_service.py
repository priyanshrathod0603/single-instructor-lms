"""FFmpeg and ffprobe video processing, probing, multi-resolution encoding, and HLS generation.

Architecture Specifications:
- VM-02: Video Transcoding Infrastructure (FFmpeg + HLS)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md

Strict Invariants:
1. Subprocess Safety: Commands are always executed as argument lists; shell=True is strictly prohibited.
2. Aspect Ratio & Dimension Integrity: Never upscales source video; ensures even pixel dimensions (trunc(x/2)*2).
3. Audio Safety: Inspects audio presence before encoding; never requests audio transcoding for silent video.
4. Deterministic HLS Structure: Generates master.m3u8, variant playlists, and relative segment references.
5. Strict Validation: Validates master playlist, variant playlists, and all segment files before declaring readiness.
"""

from dataclasses import dataclass, field
import json
import logging
from math import gcd
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Base exception for FFmpeg processing errors."""
    pass


class FFmpegNotFoundError(FFmpegError):
    """Raised when ffmpeg or ffprobe executable is not available on system."""
    pass


class FFmpegTimeoutError(FFmpegError):
    """Raised when FFmpeg execution exceeds configured timeout limit."""
    pass


class FFmpegExecutionError(FFmpegError):
    """Raised when FFmpeg process terminates with a non-zero exit code."""

    def __init__(self, cmd: list[str], returncode: int, stdout: str, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"FFmpeg failed with exit code {returncode}.\nStderr: {stderr[-1000:] if stderr else ''}"
        )


@dataclass(frozen=True)
class VideoProbeResult:
    """Structured diagnostics extracted from ffprobe."""
    width: int
    height: int
    duration_seconds: float
    video_codec: str
    audio_codec: Optional[str]
    frame_rate: float
    bitrate: Optional[int]
    has_audio: bool
    container_format: str
    file_size_bytes: int
    is_portrait: bool
    aspect_ratio: str
    raw_info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoProfile:
    """Target HLS variant encoding profile."""
    name: str                   # e.g. "1080p", "720p", "480p", "360p"
    width: int                  # Bounding box width
    height: int                 # Bounding box height
    video_bitrate: str          # Target video bitrate e.g. "4500k"
    maxrate: str                # Peak video bitrate e.g. "5000k"
    bufsize: str                # VBV buffer size e.g. "7500k"
    audio_bitrate: str          # AAC audio bitrate e.g. "192k"
    h264_profile: str           # "high" or "main"
    h264_level: str             # "4.1", "3.1", "3.0"
    bandwidth_bps: int          # For #EXT-X-STREAM-INF BANDWIDTH attribute


@dataclass
class HlsValidationResult:
    """Result of HLS playlist and segment structural verification."""
    is_valid: bool
    master_playlist_path: Path
    variant_playlists: list[Path] = field(default_factory=list)
    total_segments: int = 0
    errors: list[str] = field(default_factory=list)


# Standard Adaptive Bitrate Profile Specifications
STANDARD_PROFILES: list[VideoProfile] = [
    VideoProfile(
        name="1080p",
        width=1920,
        height=1080,
        video_bitrate="4500k",
        maxrate="5000k",
        bufsize="7500k",
        audio_bitrate="192k",
        h264_profile="high",
        h264_level="4.1",
        bandwidth_bps=5_000_000,
    ),
    VideoProfile(
        name="720p",
        width=1280,
        height=720,
        video_bitrate="2500k",
        maxrate="2800k",
        bufsize="4000k",
        audio_bitrate="128k",
        h264_profile="main",
        h264_level="3.1",
        bandwidth_bps=2_800_000,
    ),
    VideoProfile(
        name="480p",
        width=854,
        height=480,
        video_bitrate="1000k",
        maxrate="1200k",
        bufsize="1800k",
        audio_bitrate="96k",
        h264_profile="main",
        h264_level="3.0",
        bandwidth_bps=1_200_000,
    ),
]


class FFmpegService:
    """Service executing FFmpeg/ffprobe commands and generating HLS outputs."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._ffmpeg_bin: Optional[str] = self._resolve_binary("ffmpeg", self.settings.FFMPEG_PATH)
        self._ffprobe_bin: Optional[str] = self._resolve_binary("ffprobe", self.settings.FFPROBE_PATH)

    def _resolve_binary(self, name: str, explicit_path: Optional[str]) -> Optional[str]:
        """Locate binary executable on system or configured path."""
        if explicit_path is not None and explicit_path.strip():
            candidate = explicit_path.strip()
            return candidate if Path(candidate).is_file() else None
        found = shutil.which(name)
        if found:
            return found
        # Common macOS / Linux installation locations fallback
        for candidate in [f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}", f"/usr/bin/{name}"]:
            if Path(candidate).is_file():
                return candidate
        return None

    @property
    def is_ffmpeg_available(self) -> bool:
        """Check whether ffmpeg executable is available."""
        return self._ffmpeg_bin is not None and Path(self._ffmpeg_bin).is_file()

    @property
    def is_ffprobe_available(self) -> bool:
        """Check whether ffprobe executable is available."""
        return self._ffprobe_bin is not None and Path(self._ffprobe_bin).is_file()

    def get_ffmpeg_version(self) -> Optional[str]:
        """Capture ffmpeg version line for operational diagnostics."""
        if not self.is_ffmpeg_available:
            return None
        try:
            res = subprocess.run(
                [self._ffmpeg_bin, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            first_line = res.stdout.splitlines()[0] if res.stdout else ""
            return first_line.strip()
        except Exception as err:
            logger.warning("Could not read ffmpeg version: %s", err)
            return None

    def get_ffprobe_version(self) -> Optional[str]:
        """Capture ffprobe version line."""
        if not self.is_ffprobe_available:
            return None
        try:
            res = subprocess.run(
                [self._ffprobe_bin, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            first_line = res.stdout.splitlines()[0] if res.stdout else ""
            return first_line.strip()
        except Exception as err:
            logger.warning("Could not read ffprobe version: %s", err)
            return None

    def probe_video(self, file_path: Path) -> VideoProbeResult:
        """Inspect video file metadata using ffprobe.

        Raises:
            FFmpegNotFoundError: If ffprobe binary is missing.
            ValidationException: If input is corrupt, invalid, or missing video streams.
        """
        if not self.is_ffprobe_available:
            raise FFmpegNotFoundError("ffprobe binary is not installed or accessible on PATH.")

        if not file_path.exists() or not file_path.is_file():
            raise ValidationException(f"Media file not found for probing: {file_path}", code="FILE_NOT_FOUND")

        cmd = [
            self._ffprobe_bin,
            "-v", "error",
            "-show_entries",
            "format=duration,size,bit_rate,format_name:stream=index,codec_name,codec_type,width,height,r_frame_rate,bit_rate,sample_rate,channels",
            "-of", "json",
            str(file_path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
            data = json.loads(res.stdout)
        except subprocess.TimeoutExpired as e:
            raise ValidationException("Media file probing timed out.", code="PROBE_TIMEOUT") from e
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() if e.stderr else "Unknown ffprobe error"
            raise ValidationException(f"Invalid or corrupted video file: {err_msg}", code="INVALID_MEDIA_SOURCE") from e
        except Exception as e:
            raise ValidationException(f"Could not parse media probe output: {e}", code="CORRUPT_MEDIA") from e

        streams = data.get("streams", [])
        fmt = data.get("format", {})

        video_stream: Optional[dict[str, Any]] = None
        audio_stream: Optional[dict[str, Any]] = None

        for s in streams:
            if s.get("codec_type") == "video" and not video_stream:
                video_stream = s
            elif s.get("codec_type") == "audio" and not audio_stream:
                audio_stream = s

        if not video_stream:
            raise ValidationException("Source media contains no valid video stream.", code="NO_VIDEO_STREAM")

        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)

        if width <= 0 or height <= 0:
            raise ValidationException(f"Invalid video dimensions: {width}x{height}", code="INVALID_VIDEO_DIMENSIONS")

        # Parse duration
        duration_raw = fmt.get("duration") or video_stream.get("duration") or 0
        try:
            duration_seconds = float(duration_raw)
        except (ValueError, TypeError):
            duration_seconds = 0.0

        if duration_seconds <= 0:
            raise ValidationException("Could not determine video duration or duration is zero.", code="INVALID_VIDEO_DURATION")

        # Parse frame rate (e.g. "30/1" or "29.97")
        r_fps = video_stream.get("r_frame_rate", "30/1")
        try:
            if "/" in r_fps:
                num, den = r_fps.split("/", 1)
                frame_rate = round(float(num) / max(1, float(den)), 2)
            else:
                frame_rate = round(float(r_fps), 2)
        except Exception:
            frame_rate = 30.0

        # Bitrate
        bitrate_raw = fmt.get("bit_rate") or video_stream.get("bit_rate")
        bitrate = int(bitrate_raw) if bitrate_raw and str(bitrate_raw).isdigit() else None

        # Aspect ratio
        is_portrait = height > width
        common_divisor = gcd(width, height) if width > 0 and height > 0 else 1
        aspect_ratio = f"{width // common_divisor}:{height // common_divisor}"

        return VideoProbeResult(
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            video_codec=video_stream.get("codec_name", "unknown"),
            audio_codec=audio_stream.get("codec_name") if audio_stream else None,
            frame_rate=frame_rate,
            bitrate=bitrate,
            has_audio=audio_stream is not None,
            container_format=fmt.get("format_name", "unknown"),
            file_size_bytes=int(fmt.get("size") or file_path.stat().st_size),
            is_portrait=is_portrait,
            aspect_ratio=aspect_ratio,
            raw_info=data,
        )

    def derive_transcode_profiles(self, probe: VideoProbeResult) -> list[VideoProfile]:
        """Derive suitable multi-resolution profiles ensuring NO UPSCALING.

        Rules:
        1. Never scale up beyond source resolution in either dimension.
        2. Portrait videos use height as primary dimension constraint.
        3. Landscape videos use width as primary dimension constraint.
        4. Sub-480p videos generate a single profile matching source dimensions.
        5. Always returns at least one valid profile.
        """
        selected: list[VideoProfile] = []
        src_w, src_h = probe.width, probe.height
        is_portrait = probe.is_portrait

        for std_p in STANDARD_PROFILES:
            target_w = std_p.height if is_portrait else std_p.width
            target_h = std_p.width if is_portrait else std_p.height

            # Strict no-upscale rule: source must meet or exceed both dimensions
            if src_w >= target_w and src_h >= target_h:
                profile_variant = VideoProfile(
                    name=std_p.name,
                    width=target_w,
                    height=target_h,
                    video_bitrate=std_p.video_bitrate,
                    maxrate=std_p.maxrate,
                    bufsize=std_p.bufsize,
                    audio_bitrate=std_p.audio_bitrate,
                    h264_profile=std_p.h264_profile,
                    h264_level=std_p.h264_level,
                    bandwidth_bps=std_p.bandwidth_bps,
                )
                selected.append(profile_variant)

        # Fallback for sub-480p or non-standard low resolution videos
        if not selected:
            # Round dimensions down to even integers for H.264 macroblock compliance
            even_w = src_w - (src_w % 2)
            even_h = src_h - (src_h % 2)
            profile_name = f"{min(even_w, even_h)}p" if min(even_w, even_h) > 0 else "source"
            selected.append(
                VideoProfile(
                    name=profile_name,
                    width=even_w,
                    height=even_h,
                    video_bitrate="800k",
                    maxrate="1000k",
                    bufsize="1500k",
                    audio_bitrate="96k",
                    h264_profile="main",
                    h264_level="3.0",
                    bandwidth_bps=900_000,
                )
            )

        return selected

    def transcode_to_hls(
        self,
        input_path: Path,
        output_dir: Path,
        profiles: list[VideoProfile],
        has_audio: bool,
        segment_duration: int = 6,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        """Transcode input video to multi-resolution HLS streams.

        Args:
            input_path: Local path to source video.
            output_dir: Directory where master.m3u8 and variants will be written.
            profiles: List of derived VideoProfiles to encode.
            has_audio: Whether input video contains an audio stream.
            segment_duration: Target HLS segment duration in seconds.
            timeout_seconds: Maximum seconds permitted per FFmpeg execution.

        Returns:
            Dictionary containing transcode diagnostics and generated profile info.
        """
        if not self.is_ffmpeg_available:
            raise FFmpegNotFoundError("ffmpeg executable is not installed or accessible on PATH.")

        output_dir.mkdir(parents=True, exist_ok=True)
        executed_profiles: list[dict[str, Any]] = []

        for profile in profiles:
            profile_dir = output_dir / profile.name
            segments_dir = profile_dir / "segments"
            segments_dir.mkdir(parents=True, exist_ok=True)

            playlist_path = profile_dir / "playlist.m3u8"
            segment_pattern = segments_dir / "segment_%03d.ts"

            # Filter: scale preserving aspect ratio without exceeding target box, ensure even dimensions
            scale_filter = (
                f"scale=w={profile.width}:h={profile.height}:force_original_aspect_ratio=decrease,"
                f"scale=trunc(iw/2)*2:trunc(ih/2)*2"
            )

            cmd = [
                self._ffmpeg_bin,
                "-y",                           # Overwrite output files
                "-i", str(input_path),
                "-vf", scale_filter,
                "-pix_fmt", "yuv420p",          # Universal browser H.264 compatibility
                "-c:v", "libx264",
                "-preset", "fast",
                "-profile:v", profile.h264_profile,
                "-level", profile.h264_level,
                "-b:v", profile.video_bitrate,
                "-maxrate", profile.maxrate,
                "-bufsize", profile.bufsize,
            ]

            # Handle Audio
            if has_audio:
                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", profile.audio_bitrate,
                    "-ac", "2",
                ])
            else:
                cmd.append("-an")

            # HLS Muxer Configuration
            cmd.extend([
                "-hls_time", str(segment_duration),
                "-hls_playlist_type", "vod",
                "-hls_base_url", "segments/",   # Crucial: relative segment resolution
                "-hls_segment_filename", str(segment_pattern),
                str(playlist_path),
            ])

            logger.info("Executing FFmpeg for profile %s: %s", profile.name, " ".join(cmd[:12]))

            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                if res.returncode != 0:
                    raise FFmpegExecutionError(cmd, res.returncode, res.stdout, res.stderr)
            except subprocess.TimeoutExpired as e:
                raise FFmpegTimeoutError(
                    f"FFmpeg transcode timed out after {timeout_seconds} seconds for profile {profile.name}."
                ) from e

            # Verify variant playlist was produced
            if not playlist_path.exists():
                raise FFmpegError(f"Variant playlist was not produced for profile {profile.name}")

            segments = list(segments_dir.glob("*.ts"))
            executed_profiles.append({
                "name": profile.name,
                "width": profile.width,
                "height": profile.height,
                "bandwidth_bps": profile.bandwidth_bps,
                "playlist_path": str(playlist_path),
                "segments_count": len(segments),
            })

        # Generate master playlist
        master_path = output_dir / "master.m3u8"
        master_lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
        ]

        for p_info in executed_profiles:
            # Codecs string: High profile avc1.640028 or Main avc1.4d401f
            if p_info["name"] == "1080p":
                v_codec = "avc1.640028"
            elif p_info["name"] == "720p":
                v_codec = "avc1.4d401f"
            else:
                v_codec = "avc1.4d401e"

            codecs_str = f'{v_codec},mp4a.40.2' if has_audio else v_codec
            master_lines.append(
                f'#EXT-X-STREAM-INF:BANDWIDTH={p_info["bandwidth_bps"]},'
                f'RESOLUTION={p_info["width"]}x{p_info["height"]},'
                f'CODECS="{codecs_str}"'
            )
            master_lines.append(f'{p_info["name"]}/playlist.m3u8')

        master_path.write_text("\n".join(master_lines) + "\n", encoding="utf-8")

        return {
            "master_playlist_path": str(master_path),
            "profiles": executed_profiles,
        }

    def validate_hls_output(self, output_dir: Path, profiles: list[VideoProfile]) -> HlsValidationResult:
        """Validate structural integrity of generated master and variant playlists and media segments.

        Verifies:
        1. master.m3u8 exists, non-empty, contains #EXTM3U and references each variant playlist.
        2. Each variant playlist exists, non-empty, contains #EXT-X-ENDLIST.
        3. All referenced segment files exist on disk, are non-empty, and valid.
        """
        errors: list[str] = []
        master_path = output_dir / "master.m3u8"

        if not master_path.exists():
            return HlsValidationResult(is_valid=False, master_playlist_path=master_path, errors=["master.m3u8 not found"])

        master_content = master_path.read_text(encoding="utf-8")
        if not master_content.startswith("#EXTM3U"):
            errors.append("master.m3u8 does not start with #EXTM3U")

        variant_paths: list[Path] = []
        total_segments = 0

        for profile in profiles:
            variant_rel = f"{profile.name}/playlist.m3u8"
            if variant_rel not in master_content:
                errors.append(f"master.m3u8 does not reference variant playlist {variant_rel}")

            v_path = output_dir / profile.name / "playlist.m3u8"
            if not v_path.exists():
                errors.append(f"Variant playlist missing: {v_path}")
                continue

            variant_paths.append(v_path)
            v_content = v_path.read_text(encoding="utf-8")

            if not v_content.startswith("#EXTM3U"):
                errors.append(f"{v_path.name} does not start with #EXTM3U")

            if "#EXT-X-ENDLIST" not in v_content:
                errors.append(f"{v_path.name} is missing #EXT-X-ENDLIST terminal marker")

            # Extract segment filenames
            segment_lines = [
                line.strip()
                for line in v_content.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

            if not segment_lines:
                errors.append(f"{v_path.name} contains zero segments")
                continue

            for seg_line in segment_lines:
                total_segments += 1
                seg_path = output_dir / profile.name / seg_line
                if not seg_path.exists():
                    errors.append(f"Referenced segment does not exist: {seg_path}")
                elif seg_path.stat().st_size <= 0:
                    errors.append(f"Referenced segment is empty (0 bytes): {seg_path}")

        return HlsValidationResult(
            is_valid=len(errors) == 0,
            master_playlist_path=master_path,
            variant_playlists=variant_paths,
            total_segments=total_segments,
            errors=errors,
        )
