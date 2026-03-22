"""
Image Service Module
===================
Handles image downloading from Basalam CDN, uploading to MinIO/S3,
optimization, and duplicate detection via content hashing.

Tasks:
- 4.10.1: Download images from Basalam CDN
- 4.10.2: Upload to MinIO/S3 with optimization
- 4.10.3: Generate CDN URLs and store metadata
- 4.10.4: Handle duplicate image detection via hash
"""

import hashlib
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import boto3
from botocore.config import Config
from PIL import Image
import io
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.products.models import ProductMedia
from src.core.config import get_settings
from src.core.database import async_session_maker

logger = logging.getLogger(__name__)


class ImageServiceError(Exception):
    """Base exception for image service errors"""

    pass


class ImageDownloadError(ImageServiceError):
    """Error downloading image from source"""

    pass


class ImageOptimizationError(ImageServiceError):
    """Error during image optimization"""

    pass


class ImageUploadError(ImageServiceError):
    """Error uploading to storage"""

    pass


class ImageNotFoundError(ImageServiceError):
    """Image not found in storage"""

    pass


class ImageConfig:
    """Configuration for image service"""

    def __init__(self):
        _s = get_settings()
        self.minio_endpoint = _s.minio_endpoint
        self.minio_access_key = _s.minio_access_key
        self.minio_secret_key = _s.minio_secret_key.get_secret_value()
        self.minio_bucket = _s.minio_bucket
        self.minio_region = _s.minio_region
        self.minio_use_ssl = _s.minio_use_ssl

        self.cdn_base_url = _s.cdn_base_url

        self.image_max_width = _s.image_max_width
        self.image_max_height = _s.image_max_height
        self.image_quality = _s.image_quality
        self.image_format = _s.image_format.upper()

        self.http_timeout = _s.image_http_timeout

        self.basalam_cdn_base = "https://cdn.basalam.com"


class ImageMetadata:
    """Container for processed image metadata"""

    def __init__(
        self,
        content: bytes,
        hash: str,
        mime_type: str,
        width: int,
        height: int,
        size_bytes: int,
        original_url: str,
    ):
        self.content = content
        self.hash = hash
        self.mime_type = mime_type
        self.width = width
        self.height = height
        self.size_bytes = size_bytes
        self.original_url = original_url


class StorageService:
    """Handles MinIO/S3 storage operations"""

    def __init__(self, config: ImageConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=f"http://{self.config.minio_endpoint}"
                if not self.config.minio_use_ssl
                else None,
                aws_access_key_id=self.config.minio_access_key,
                aws_secret_access_key=self.config.minio_secret_key,
                region_name=self.config.minio_region,
                config=Config(signature_version="s3v4"),
            )
        return self._client

    async def upload(
        self,
        content: bytes,
        key: str,
        mime_type: str,
    ) -> str:
        """Upload content to S3/MinIO and return the key"""
        try:
            client = self._get_client()
            client.put_object(
                Bucket=self.config.minio_bucket,
                Key=key,
                Body=content,
                ContentType=mime_type,
            )
            logger.info(f"Uploaded image to storage: {key}")
            return key
        except Exception as e:
            logger.error(f"Failed to upload to storage: {e}")
            raise ImageUploadError(f"Failed to upload image: {e}") from e

    async def exists(self, key: str) -> bool:
        """Check if key exists in storage"""
        try:
            client = self._get_client()
            client.head_object(Bucket=self.config.minio_bucket, Key=key)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete object from storage"""
        try:
            client = self._get_client()
            client.delete_object(Bucket=self.config.minio_bucket, Key=key)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete image {key}: {e}")
            return False

    def generate_cdn_url(self, key: str) -> str:
        """Generate CDN URL for the stored image"""
        return f"{self.config.cdn_base_url}/{key}"


class ImageProcessor:
    """Handles image optimization and processing"""

    SUPPORTED_FORMATS = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
    }

    MIME_TYPES = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }

    def __init__(self, config: ImageConfig):
        self.config = config

    def _get_format_from_mime(self, mime_type: str) -> str:
        """Get PIL format from mime type"""
        mime_to_format = {
            "image/jpeg": "JPEG",
            "image/jpg": "JPEG",
            "image/png": "PNG",
            "image/webp": "WEBP",
        }
        return mime_to_format.get(mime_type.lower(), "JPEG")

    def _get_extension(self, format: str) -> str:
        """Get file extension from format"""
        format_to_ext = {
            "JPEG": "jpg",
            "PNG": "png",
            "WEBP": "webp",
        }
        return format_to_ext.get(format, "jpg")

    async def process(
        self, content: bytes, original_mime: str
    ) -> Tuple[bytes, str, int, int]:
        """
        Optimize image: resize if needed and convert to target format.
        Returns: (processed_content, mime_type, width, height)
        """
        try:
            image = Image.open(io.BytesIO(content))

            if image.mode == "RGBA" and self.config.image_format == "JPEG":
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3])
                image = background

            width, height = image.size

            if (
                width > self.config.image_max_width
                or height > self.config.image_max_height
            ):
                image.thumbnail(
                    (self.config.image_max_width, self.config.image_max_height),
                    Image.Resampling.LANCZOS,
                )
                width, height = image.size

            output = io.BytesIO()
            target_format = self.SUPPORTED_FORMATS.get(self.config.image_format, "WEBP")

            image.save(
                output,
                format=target_format,
                quality=self.config.image_quality,
                optimize=True,
            )

            processed_content = output.getvalue()
            mime_type = self.MIME_TYPES.get(target_format, "image/webp")

            logger.info(
                f"Image processed: {len(content)} -> {len(processed_content)} bytes, "
                f"{width}x{height}, {mime_type}"
            )

            return processed_content, mime_type, width, height

        except Exception as e:
            logger.error(f"Image optimization failed: {e}")
            raise ImageOptimizationError(f"Failed to optimize image: {e}") from e

    def compute_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of image content"""
        return hashlib.sha256(content).hexdigest()


class ImageService:
    """
    Main image service handling download, optimization, upload, and storage.

    Supports:
    - Downloading images from Basalam CDN
    - Optimizing images (resize, compress, format conversion)
    - Uploading to MinIO/S3
    - Duplicate detection via content hash
    - Storing metadata in database
    """

    def __init__(self, config: Optional[ImageConfig] = None):
        self.config = config or ImageConfig()
        self.storage = StorageService(self.config)
        self.processor = ImageProcessor(self.config)

    async def download_from_basalam(
        self,
        image_id: str,
        timeout: Optional[float] = None,
    ) -> bytes:
        """
        Download image from Basalam CDN.

        Args:
            image_id: Basalam image ID/identifier
            timeout: HTTP request timeout in seconds

        Returns:
            Raw image bytes
        """
        url = f"{self.config.basalam_cdn_base}/{image_id}"
        return await self.download_from_url(url, timeout)

    async def download_from_url(
        self,
        url: str,
        timeout: Optional[float] = None,
    ) -> bytes:
        """
        Download image from arbitrary URL.

        Args:
            url: Full URL to image
            timeout: HTTP request timeout in seconds

        Returns:
            Raw image bytes
        """
        timeout_value = timeout or self.config.http_timeout

        try:
            async with httpx.AsyncClient(timeout=timeout_value) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
                logger.info(f"Downloaded image from {url}: {len(content)} bytes")
                return content
        except httpx.HTTPStatusError as e:
            raise ImageDownloadError(
                f"Failed to download image: HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise ImageDownloadError(f"Failed to download image: {e}") from e

    async def process_and_upload(
        self,
        content: bytes,
        original_url: str,
        session: AsyncSession,
    ) -> Tuple[str, ProductMedia]:
        """
        Process image and upload to storage.

        Handles duplicate detection - if image with same hash exists,
        returns existing record instead of re-uploading.

        Args:
            content: Raw image bytes
            original_url: Original source URL for reference
            session: Database session

        Returns:
            Tuple of (cdn_url, ProductMedia record)
        """
        hash_value = self.processor.compute_hash(content)

        existing = await self._find_by_hash(hash_value, session)
        if existing:
            logger.info(f"Duplicate image detected, returning existing: {existing.id}")
            cdn_url = self.storage.generate_cdn_url(existing.storage_key)
            return cdn_url, existing

        mime_type = self._detect_mime_type(content, original_url)

        processed_content, final_mime, width, height = await self.processor.process(
            content, mime_type
        )

        final_hash = self.processor.compute_hash(processed_content)
        key = self._generate_key(final_hash, final_mime)

        await self.storage.upload(processed_content, key, final_mime)

        media = await self._create_media_record(
            session=session,
            url=original_url,
            storage_key=key,
            storage_provider="minio",
            hash_value=final_hash,
            size_bytes=len(processed_content),
            mime_type=final_mime,
            width=width,
            height=height,
        )

        cdn_url = self.storage.generate_cdn_url(key)
        logger.info(f"Image uploaded successfully: {cdn_url}")

        return cdn_url, media

    async def _find_by_hash(
        self,
        hash_value: str,
        session: AsyncSession,
    ) -> Optional[ProductMedia]:
        """Check if image with given hash already exists"""
        stmt = select(ProductMedia).where(ProductMedia.hash == hash_value)
        result = await session.execute(stmt)
        return result.scalars().first()

    def _generate_key(self, hash_value: str, mime_type: str) -> str:
        """Generate unique storage key based on content hash"""
        ext = self._get_extension_from_mime(mime_type)
        date_prefix = datetime.utcnow().strftime("%Y/%m/%d")
        return f"images/{date_prefix}/{hash_value[:2]}/{hash_value}.{ext}"

    def _get_extension_from_mime(self, mime_type: str) -> str:
        """Get file extension from mime type"""
        mime_to_ext = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        return mime_to_ext.get(mime_type.lower(), "jpg")

    def _detect_mime_type(self, content: bytes, url: str) -> str:
        """Detect mime type from content or URL extension"""
        try:
            image = Image.open(io.BytesIO(content))
            format_to_mime = {
                "JPEG": "image/jpeg",
                "PNG": "image/png",
                "WEBP": "image/webp",
                "GIF": "image/gif",
            }
            return format_to_mime.get(image.format, "image/jpeg")
        except Exception:
            url_lower = url.lower()
            if ".png" in url_lower:
                return "image/png"
            elif ".webp" in url_lower:
                return "image/webp"
            elif ".gif" in url_lower:
                return "image/gif"
            return "image/jpeg"

    async def _create_media_record(
        self,
        session: AsyncSession,
        url: str,
        storage_key: str,
        storage_provider: str,
        hash_value: str,
        size_bytes: int,
        mime_type: str,
        width: int,
        height: int,
    ) -> ProductMedia:
        """Create ProductMedia record in database"""
        media = ProductMedia(
            id=uuid4(),
            media_type="image",
            url=url,
            storage_provider=storage_provider,
            storage_key=storage_key,
            hash=hash_value,
            size_bytes=size_bytes,
            mime_type=mime_type,
            width=width,
            height=height,
            status="processed",
        )
        session.add(media)
        await session.flush()
        logger.info(f"Created media record: {media.id}")
        return media

    async def download_and_process(
        self,
        source: str,
        session: AsyncSession,
        is_basalam_id: bool = True,
    ) -> Tuple[str, ProductMedia]:
        """
        Convenience method: download from source and process.

        Args:
            source: Image URL or Basalam image ID
            session: Database session
            is_basalam_id: If True, treat source as Basalam image ID

        Returns:
            Tuple of (cdn_url, ProductMedia record)
        """
        if is_basalam_id:
            content = await self.download_from_basalam(source)
            url = f"{self.config.basalam_cdn_base}/{source}"
        else:
            content = await self.download_from_url(source)
            url = source

        return await self.process_and_upload(content, url, session)

    async def delete_image(
        self,
        media: ProductMedia,
        session: AsyncSession,
    ) -> bool:
        """Delete image from storage and database"""
        try:
            await self.storage.delete(media.storage_key)
            await session.delete(media)
            await session.flush()
            logger.info(f"Deleted image: {media.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete image: {e}")
            return False


async def get_image_service() -> ImageService:
    """Dependency to get ImageService instance"""
    return ImageService()


async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
