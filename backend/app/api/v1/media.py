"""Media Storage & Video Protection REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.10)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401-TASK404)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009, ADR-010)
"""

import io
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    require_permissions,
)
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.network import get_trusted_client_ip
from app.core.permissions import MEDIA_UPLOAD, MEDIA_VIEW_PROTECTED
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    User,
)
from app.schemas.media import (
    MediaAssetListResponse,
    MediaAssetResponse,
    PlaybackTokenRequest,
    PlaybackTokenResponse,
    TranscodeJobResponse,
    UploadConfirmRequest,
    UploadIntentRequest,
    UploadIntentResponse,
    VerifyPlaybackTokenRequest,
)
from app.services.media_service import MediaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["Media Storage & Protection"])


def get_media_service() -> MediaService:
    """Dependency providing MediaService instance."""
    return MediaService()


@router.post(
    "/upload-intent",
    response_model=UploadIntentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate presigned S3/R2 upload URL",
)
async def create_upload_intent_endpoint(
    data: UploadIntentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(MEDIA_UPLOAD)),
    media_service: MediaService = Depends(get_media_service),
) -> UploadIntentResponse:
    """Validate file boundaries and return presigned PUT upload URL. Requires media:upload."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    return await media_service.create_upload_intent(
        db,
        current_user,
        data,
        ip_address=ip,
        user_agent=ua,
    )


async def _trigger_transcode_worker_safely() -> None:
    """Asynchronously execute a transcode worker cycle in background task."""
    try:
        from app.workers.transcode_worker import TranscodeWorker
        worker = TranscodeWorker()
        await worker.run_once()
    except Exception as err:
        logger.warning("Background transcode worker cycle notice: %s", err)


@router.post(
    "/{id}/confirm",
    response_model=MediaAssetResponse,
    summary="Confirm upload completion and trigger transcode",
)
async def confirm_upload_endpoint(
    id: uuid.UUID,
    data: UploadConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(MEDIA_UPLOAD)),
    media_service: MediaService = Depends(get_media_service),
) -> MediaAssetResponse:
    """Confirm binary upload succeeded, mark status, and prepare metadata. Requires media:upload."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    res = await media_service.confirm_upload(
        db,
        id,
        data,
        current_user,
        ip_address=ip,
        user_agent=ua,
    )
    if res.status == "PROCESSING" and res.mime_type.startswith("video/"):
        background_tasks.add_task(_trigger_transcode_worker_safely)
    return res


@router.get(
    "/{id}/transcode-job",
    response_model=TranscodeJobResponse,
    summary="Retrieve latest transcoding job for media asset",
)
def get_transcode_job_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(MEDIA_UPLOAD)),
    media_service: MediaService = Depends(get_media_service),
) -> TranscodeJobResponse:
    """Retrieve current or latest HLS transcoding job. Requires media:upload."""
    job = media_service.get_transcode_job(db, id, current_user)
    if not job:
        raise ResourceNotFoundException("MediaTranscodeJob", str(id))
    return TranscodeJobResponse.model_validate(job)


@router.post(
    "/{id}/retry-transcode",
    response_model=TranscodeJobResponse,
    summary="Retry a failed or stalled video transcoding job",
)
async def retry_transcode_endpoint(
    id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(MEDIA_UPLOAD)),
    media_service: MediaService = Depends(get_media_service),
) -> TranscodeJobResponse:
    """Retry failed video transcoding. Requires media:upload."""
    job = await media_service.retry_transcode(db, id, current_user)
    background_tasks.add_task(_trigger_transcode_worker_safely)
    return TranscodeJobResponse.model_validate(job)


@router.get(
    "",
    response_model=MediaAssetListResponse,
    summary="List media assets",
)
async def list_media_assets_endpoint(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(MEDIA_UPLOAD)),
    media_service: MediaService = Depends(get_media_service),
) -> MediaAssetListResponse:
    """List media assets. Requires media:upload or elevated role."""
    is_admin = any(r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN))
    uploader_id = None if is_admin else current_user.id

    return await media_service.list_media_assets(
        db,
        uploader_id=uploader_id,
        status=status_filter,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{id}",
    response_model=MediaAssetResponse,
    summary="Retrieve media asset details",
)
async def get_media_asset_endpoint(
    id: uuid.UUID,
    lesson_id: Optional[uuid.UUID] = Query(None, description="Optional curriculum lesson identifier for student authorization"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    media_service: MediaService = Depends(get_media_service),
) -> MediaAssetResponse:
    """Retrieve media asset metadata with authorization check."""
    return await media_service.get_media_asset(db, id, user=current_user, lesson_id=lesson_id)


@router.post(
    "/{id}/playback-token",
    response_model=PlaybackTokenResponse,
    summary="Issue signed, short-lived HLS video stream token",
)
def generate_playback_token_endpoint(
    id: uuid.UUID,
    request: Request,
    payload: Optional[PlaybackTokenRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    media_service: MediaService = Depends(get_media_service),
) -> PlaybackTokenResponse:
    """Issue short-lived (2-hour TTL) signed HLS video playback token.

    Verifies active enrollment or instructor permissions.
    """
    client_ip = get_trusted_client_ip(request)
    lesson_id = payload.lesson_id if payload else None

    return media_service.generate_playback_token(
        db,
        id,
        current_user,
        lesson_id=lesson_id,
        client_ip=client_ip,
    )


@router.get(
    "/{id}/protected-pdf",
    summary="Stream protected watermarked PDF",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Streamed PDF with dynamic student watermark",
        }
    },
)
def stream_protected_pdf_endpoint(
    id: uuid.UUID,
    lesson_id: Optional[uuid.UUID] = Query(None, description="Curriculum lesson identifier"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    media_service: MediaService = Depends(get_media_service),
) -> StreamingResponse:
    """Stream protected PDF with dynamic student provenance watermarking."""
    pdf_bytes, filename = media_service.get_watermarked_pdf(
        db,
        id,
        current_user,
        lesson_id=lesson_id,
    )

    safe_filename = filename.replace('"', '\\"')
    headers = {
        "Content-Disposition": f'inline; filename="{safe_filename}"',
        "Content-Type": "application/pdf",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
    }

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete media asset and storage object",
)
async def delete_media_asset_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(MEDIA_UPLOAD)),
    media_service: MediaService = Depends(get_media_service),
) -> Response:
    """Delete media asset and remove object from storage. Requires media:upload."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    await media_service.delete_media_asset(
        db,
        id,
        current_user,
        ip_address=ip,
        user_agent=ua,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{id}/verify-playback-token",
    summary="Verify short-lived signed playback token",
)
def verify_playback_token_endpoint(
    id: uuid.UUID,
    request: Request,
    token: Optional[str] = Query(None, description="Playback token string to verify"),
    body: Optional[VerifyPlaybackTokenRequest] = None,
    media_service: MediaService = Depends(get_media_service),
) -> dict:
    """Verify signed HLS playback token for edge/stream delivery."""
    token_str = token or (body.token if body else None)
    if not token_str:
        raise BadRequestException(message="Token is required.", code="MISSING_TOKEN")
    client_ip = get_trusted_client_ip(request)
    claims = media_service.verify_playback_token(token_str, id, client_ip=client_ip)
    return {"valid": True, "claims": claims}
