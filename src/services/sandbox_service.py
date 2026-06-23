import logging
import asyncio
import httpx
from datetime import datetime, timezone
from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.constants import SandboxStatus, SandboxType
from src.database.models import Sandbox
from src.database.session import get_db_context
from src.repositories.sandbox_repo import SandboxRepository
from src.services.container_service import get_container_service
from src.services.warm_pool_service import get_warm_pool_service
from src.api.schemas import SandboxCreate

logger = logging.getLogger(__name__)


async def _poll_container_status(
    sandbox_id: str,
    container_name: str,
    container_service,
    max_attempts: int = 80,
):
    """
    Poll the container's HTTP status endpoint to get tunnel URL
    Uses progressive backoff for faster initial detection

    NOTE: This function creates its own DB session because it runs in a
    background task, after the request-scoped session has been closed.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(max_attempts):
            try:
                # Resolve IP dynamically (needed for GKE/K8s)
                container_ip = await container_service.get_container_ip(container_name)

                if not container_ip:
                    logger.debug(
                        f"Container {container_name} no IP yet (attempt {attempt + 1})"
                    )
                    # Use container name as fallback (works for Docker)
                    status_url = f"http://{container_name}:8888/status"
                else:
                    status_url = f"http://{container_ip}:8888/status"

                logger.info(
                    f"Polling container status for sandbox {sandbox_id} (attempt {attempt + 1}/{max_attempts})"
                )
                
                # Check DB first - maybe a callback already updated it!
                async with get_db_context() as db:
                    repo = SandboxRepository(db)
                    db_sandbox = await repo.get_by_id(sandbox_id)
                    if db_sandbox and db_sandbox.status == SandboxStatus.STARTED and db_sandbox.tunnel_url:
                        logger.info(f"Sandbox {sandbox_id} already updated via callback. Polling successful.")
                        return True

                # Call status endpoint
                response = await client.get(status_url)

                if response.status_code == 200:
                    data = response.json()
                    tunnel_url = data.get("tunnel_url")
                    container_status = data.get("status")

                    if tunnel_url and container_status == "ready":
                        # Update sandbox with tunnel URL
                        async with get_db_context() as db:
                            repo = SandboxRepository(db)
                            sandbox = await repo.get_by_id(sandbox_id)
                            if sandbox:
                                sandbox.tunnel_url = tunnel_url
                                sandbox.status = SandboxStatus.STARTED
                                logger.info(
                                    f"Sandbox {sandbox_id} ready with tunnel URL: {tunnel_url}"
                                )
                                return True
                    else:
                        logger.debug(
                            f"Container not ready yet: status={container_status}, tunnel_url={tunnel_url}"
                        )

            except Exception as e:
                logger.debug(
                    f"Failed to poll container status (attempt {attempt + 1}): {e}"
                )

            # Progressive backoff
            base = settings.POLL_INTERVAL_BASE
            if attempt < 10:
                poll_interval = base
            elif attempt < 20:
                poll_interval = base * 2.0
            else:
                poll_interval = base * 4.0

            await asyncio.sleep(poll_interval)

    logger.error(
        f"Failed to get tunnel URL for sandbox {sandbox_id} after {max_attempts} attempts"
    )
    return False


async def _create_sandbox_background(
    sandbox_id: str,
    restart: bool = False,
    use_gpu: bool = False,
    sandbox_type: SandboxType = SandboxType.TERMINAL,
):
    """
    Background task to create sandbox container
    This runs asynchronously after the API returns
    """
    try:
        container_service = get_container_service()

        async with get_db_context() as db:
            repo = SandboxRepository(db)
            sandbox = await repo.get_by_id(sandbox_id)
            if not sandbox:
                logger.error(f"Sandbox {sandbox_id} not found in background task")
                return

            if restart:
                try:
                    container_name = f"sandbox-{sandbox_id}"
                    logger.info(
                        f"Cleaning up previous container {container_name} for restart"
                    )
                    await container_service.delete_sandbox_container(container_name)
                except Exception as e:
                    logger.warning(f"Cleanup failed (might be expected): {e}")

            sandbox.status = SandboxStatus.STARTING

        logger.info(
            f"Creating container for sandbox {sandbox_id} (type={sandbox_type}, gpu={use_gpu})"
        )
        result = await container_service.create_sandbox_container(
            sandbox_id, use_gpu=use_gpu, sandbox_type=sandbox_type
        )

        async with get_db_context() as db:
            repo = SandboxRepository(db)
            sandbox = await repo.get_by_id(sandbox_id)
            if sandbox:
                sandbox.container_id = result["container_id"]
                sandbox.container_name = result["container_name"]
                sandbox.host_port = result.get("host_port")

        container_name = result["container_name"]
        logger.info(
            f"Container created for sandbox {sandbox_id}: {result['container_id']}, host_port: {result.get('host_port')}"
        )

        success = await _poll_container_status(
            sandbox_id, container_name, container_service
        )
        if not success:
            async with get_db_context() as db:
                repo = SandboxRepository(db)
                sandbox = await repo.get_by_id(sandbox_id)
                if sandbox:
                    sandbox.status = SandboxStatus.FAILED
                    sandbox.error_message = "Failed to obtain tunnel URL from container"

    except Exception as e:
        logger.error(f"Failed to create container for sandbox {sandbox_id}: {e}")

        try:
            async with get_db_context() as db:
                repo = SandboxRepository(db)
                sandbox = await repo.get_by_id(sandbox_id)
                if sandbox:
                    sandbox.status = SandboxStatus.FAILED
                    sandbox.error_message = str(e)
        except Exception as db_err:
            logger.error(f"Failed to update sandbox {sandbox_id} status after error: {db_err}")


class SandboxService:
    """
    Orchestrator service for Sandbox business logic
    Coordinates database, container service, and warm pool allocation
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SandboxRepository(db)
        self.container_service = get_container_service()

    async def create_sandbox(
        self,
        sandbox_create: SandboxCreate,
        background_tasks: BackgroundTasks,
        user_id: str | None = None,
    ) -> Sandbox:
        """
        Check capacity, create sandbox record, and attempt warm pool claim or trigger background creation
        """
        active_db_count = await self.repo.count_active_total()
        if active_db_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Server capacity reached (active sandboxes: {active_db_count})",
            )

        try:
            active_real_count = await self.container_service.count_active_containers()
            if active_real_count >= settings.MAX_CONTAINERS_PER_SERVER:
                logger.warning(
                    f"Real container count ({active_real_count}) exceeds DB count ({active_db_count})"
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Server capacity reached",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to check container count: {e}")

        use_gpu = sandbox_create.use_gpu or False
        if use_gpu and not (settings.GKE_AUTOPILOT_ENABLED and settings.GPU_ENABLED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GPU sandboxes are not available (requires GKE Autopilot with GPU enabled)",
            )

        sandbox = Sandbox()
        sandbox.user_id = user_id
        sandbox.type = sandbox_create.type
        sandbox.set_expiry(hours=settings.SANDBOX_TTL_HOURS)
        sandbox.status = SandboxStatus.PENDING
        sandbox.gpu_enabled = use_gpu
        if use_gpu:
            sandbox.gpu_type = settings.GPU_TYPE
            sandbox.gpu_count = settings.GPU_COUNT

        await self.repo.create(sandbox)
        await self.db.commit()
        await self.db.refresh(sandbox)

        logger.info(f"Created sandbox record: {sandbox.id} (gpu={use_gpu})")

        warm_pool = get_warm_pool_service()
        if settings.WARM_POOL_ENABLED and sandbox.type == SandboxType.TERMINAL:
            try:
                warm_container = await warm_pool.claim_container(use_gpu=use_gpu)
                if warm_container and warm_container.tunnel_url:
                    sandbox.container_id = warm_container.container_id
                    sandbox.container_name = warm_container.container_name
                    sandbox.host_port = warm_container.host_port
                    sandbox.tunnel_url = warm_container.tunnel_url
                    sandbox.status = SandboxStatus.STARTED

                    await self.db.commit()
                    await self.db.refresh(sandbox)

                    logger.info(
                        f"INSTANT STARTUP: Sandbox {sandbox.id} claimed warm container "
                        f"{warm_container.warm_id} with tunnel {warm_container.tunnel_url}"
                    )
                    return sandbox
            except Exception as e:
                logger.warning(f"Failed to claim warm container: {e}")

        background_tasks.add_task(
            _create_sandbox_background,
            sandbox.id,
            restart=False,
            use_gpu=use_gpu,
            sandbox_type=sandbox.type,
        )

        return sandbox

    async def get_sandbox(
        self, sandbox_id: str, background_tasks: BackgroundTasks
    ) -> Sandbox:
        """
        Get details of a specific sandbox, and auto-restart it if stopped
        """
        sandbox = await self.repo.get_by_id(sandbox_id)
        if not sandbox:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sandbox {sandbox_id} not found",
            )

        if sandbox.is_expired() and sandbox.status != SandboxStatus.EXPIRED:
            logger.info(f"Lazily marking sandbox {sandbox_id} as expired")
            sandbox.status = SandboxStatus.EXPIRED
            await self.db.commit()
            await self.db.refresh(sandbox)
            return sandbox

        if sandbox.status == SandboxStatus.STOPPED:
            logger.info(f"Auto-restarting stopped sandbox {sandbox_id}")
            sandbox.status = SandboxStatus.PENDING
            await self.db.commit()

            background_tasks.add_task(
                _create_sandbox_background,
                sandbox.id,
                restart=True,
                use_gpu=sandbox.gpu_enabled,
                sandbox_type=sandbox.type,
            )

        return sandbox

    async def list_sandboxes(
        self,
        skip: int = 0,
        limit: int = 100,
        status_filter: SandboxStatus | None = None,
        user_id: str | None = None,
    ) -> tuple[list[Sandbox], int]:
        """
        List all sandboxes with optional filtering and lazy expiration check
        """
        total = await self.repo.count_all(status=status_filter, user_id=user_id)
        sandboxes = await self.repo.list_all(skip=skip, limit=limit, status=status_filter, user_id=user_id)

        updates_made = False
        for s in sandboxes:
            if s.is_expired() and s.status != SandboxStatus.EXPIRED:
                s.status = SandboxStatus.EXPIRED
                updates_made = True

        if updates_made:
            await self.db.commit()

        return sandboxes, total

    async def start_sandbox(
        self, sandbox_id: str, background_tasks: BackgroundTasks
    ) -> Sandbox:
        """
        Manually start a stopped or failed sandbox
        """
        sandbox = await self.repo.get_by_id(sandbox_id)
        if not sandbox:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sandbox {sandbox_id} not found",
            )

        if sandbox.status not in [SandboxStatus.STOPPED, SandboxStatus.FAILED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sandbox is in {sandbox.status} state, cannot start. Create a new one or wait.",
            )

        if sandbox.is_expired():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sandbox has expired",
            )

        sandbox.status = SandboxStatus.PENDING
        sandbox.error_message = None
        await self.db.commit()

        background_tasks.add_task(
            _create_sandbox_background,
            sandbox.id,
            restart=True,
            use_gpu=sandbox.gpu_enabled,
            sandbox_type=sandbox.type,
        )

        return sandbox

    async def delete_sandbox(
        self, sandbox_id: str, background_tasks: BackgroundTasks
    ) -> dict:
        """
        Soft-delete a sandbox and clean up its container in background
        """
        sandbox = await self.repo.get_by_id(sandbox_id)
        if not sandbox:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sandbox {sandbox_id} not found",
            )

        sandbox.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

        if sandbox.container_id:
            container_id_to_delete = sandbox.container_id

            async def _delete_container():
                try:
                    await self.container_service.delete_sandbox_container(
                        container_id_to_delete
                    )
                    logger.info(f"Deleted container for sandbox {sandbox_id}")
                except Exception as e:
                    logger.error(
                        f"Failed to delete container for sandbox {sandbox_id}: {e}"
                    )

            background_tasks.add_task(_delete_container)

        return {
            "status": "success",
            "sandbox_id": sandbox.id,
            "message": "Sandbox deleted successfully",
        }

    async def get_sandbox_status(self, sandbox_id: str) -> dict:
        """
        Poll the status of a sandbox mapped to operations format
        """
        sandbox = await self.repo.get_by_id(sandbox_id)
        if not sandbox:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sandbox {sandbox_id} not found",
            )

        operation_status = "pending"
        if sandbox.status == SandboxStatus.STARTED:
            operation_status = "completed"
        elif sandbox.status == SandboxStatus.FAILED:
            operation_status = "failed"
        elif sandbox.status in [SandboxStatus.STARTING, SandboxStatus.PENDING]:
            operation_status = "in_progress"

        return {
            "operation_id": sandbox.id,
            "status": operation_status,
            "sandbox_id": sandbox.id,
            "message": sandbox.error_message,
        }
