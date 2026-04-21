"""
Keyword Filter Service
======================
Scans product titles and descriptions against forbidden keywords.

Uses a combination of exact match, substring match, and optional
regex patterns to detect prohibited content.
"""
import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ForbiddenKeyword

logger = structlog.get_logger(__name__)

# Timeout for regex matching to prevent ReDoS attacks (seconds)
_REGEX_TIMEOUT_SECONDS = 2

# Dedicated thread pool for regex execution (isolated from main event loop)
_regex_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="regex-")


def _run_regex_search(pattern: str, text: str) -> Optional[re.Match]:
    """Run regex search in a thread (blocking call). Called via asyncio.to_thread."""
    return re.search(pattern, text, re.IGNORECASE)


class KeywordFilterService:
    """
    Service for scanning product text against forbidden keywords.

    Features:
    - Exact match and substring matching
    - Regex pattern support with async-safe timeout (prevents ReDoS)
    - Multi-language keyword detection
    - Severity-based flagging
    - TTL-based keyword cache
    """

    # Cache TTL in seconds (5 minutes)
    _CACHE_TTL_SECONDS = 300

    def __init__(self, session: AsyncSession):
        self.session = session
        self._keyword_cache: Optional[List[ForbiddenKeyword]] = None
        self._cache_loaded_at: float = 0.0

    async def _load_active_keywords(self) -> List[ForbiddenKeyword]:
        """Load all active forbidden keywords from DB with TTL cache."""
        now = time.monotonic()
        if self._keyword_cache is not None and (now - self._cache_loaded_at) < self._CACHE_TTL_SECONDS:
            return self._keyword_cache

        result = await self.session.execute(
            select(ForbiddenKeyword).where(ForbiddenKeyword.is_active.is_(True))
        )
        self._keyword_cache = list(result.scalars().all())
        self._cache_loaded_at = now
        return self._keyword_cache

    def invalidate_cache(self) -> None:
        """Clear the keyword cache (call after CRUD operations)."""
        self._keyword_cache = None
        self._cache_loaded_at = 0.0

    async def scan_text(
        self,
        text: str,
        language: str = "fa",
    ) -> List[Dict[str, Any]]:
        """
        Scan a text string against all active forbidden keywords.

        Args:
            text: Text to scan (title, description, etc.)
            language: Filter by language code (fa, en, ar)

        Returns:
            List of matches with keyword details
        """
        if not text:
            return []

        keywords = await self._load_active_keywords()
        matches = []
        text_lower = text.lower()

        for kw in keywords:
            if language and kw.language != language:
                continue

            matched = False

            if kw.is_regex:
                try:
                    # Run regex in thread pool with timeout — safe for async event loops
                    # (replaces SIGALRM which breaks asyncio and is Unix-only)
                    match_result = await asyncio.wait_for(
                        asyncio.to_thread(_run_regex_search, kw.keyword, text),
                        timeout=_REGEX_TIMEOUT_SECONDS,
                    )
                    if match_result is not None:
                        matched = True
                except asyncio.TimeoutError:
                    logger.warning("regex_timeout", keyword_id=str(kw.id), pattern=kw.keyword)
                    continue
                except re.error:
                    logger.warning("invalid_regex_pattern", keyword_id=str(kw.id), pattern=kw.keyword)
                    continue
            else:
                if kw.keyword.lower() in text_lower:
                    matched = True

            if matched:
                matches.append({
                    "keyword_id": str(kw.id),
                    "keyword": kw.keyword,
                    "category": kw.category,
                    "severity": kw.severity,
                    "is_regex": kw.is_regex,
                })

        return matches

    async def scan_product(
        self,
        title: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Scan a product's title and description for forbidden content.

        Args:
            title: Product title
            description: Product description

        Returns:
            Scan result with matches and overall status
        """
        title_matches = await self.scan_text(title)
        desc_matches = await self.scan_text(description) if description else []

        all_matches = title_matches + desc_matches

        # Determine overall status
        if not all_matches:
            return {
                "is_clean": True,
                "status": "approved",
                "matches": [],
                "severity": None,
            }

        highest_severity = self._get_highest_severity(all_matches)
        status = self._determine_status(highest_severity)

        return {
            "is_clean": False,
            "status": status,
            "matches": all_matches,
            "severity": highest_severity,
        }

    def _get_highest_severity(self, matches: List[Dict]) -> str:
        """Get the highest severity from a list of matches."""
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        highest = "low"
        for match in matches:
            if severity_order.get(match["severity"], 0) > severity_order.get(highest, 0):
                highest = match["severity"]
        return highest

    def _determine_status(self, severity: str) -> str:
        """Determine product status based on match severity."""
        if severity in ("critical", "high"):
            return "rejected"
        elif severity == "medium":
            return "pending_review"
        else:
            return "flagged"

    # ---------------------------------------------------------------
    # Keyword CRUD (admin operations)
    # ---------------------------------------------------------------

    async def add_keyword(
        self,
        keyword: str,
        category: str = "prohibited",
        severity: str = "high",
        language: str = "fa",
        is_regex: bool = False,
        description: str = "",
        created_by: Optional[UUID] = None,
    ) -> ForbiddenKeyword:
        """Add a new forbidden keyword."""
        kw = ForbiddenKeyword(
            keyword=keyword,
            category=category,
            severity=severity,
            language=language,
            is_regex=is_regex,
            description=description,
            created_by=created_by,
            is_active=True,
        )
        self.session.add(kw)
        await self.session.flush()
        await self.session.refresh(kw)
        self.invalidate_cache()

        logger.info(
            "forbidden_keyword_added",
            keyword_id=str(kw.id),
            keyword=keyword,
            category=category,
        )
        return kw

    async def remove_keyword(self, keyword_id: UUID) -> bool:
        """Soft-delete a forbidden keyword by setting is_active=False."""
        result = await self.session.execute(
            select(ForbiddenKeyword).where(ForbiddenKeyword.id == keyword_id)
        )
        kw = result.scalar_one_or_none()
        if not kw:
            return False

        kw.is_active = False
        await self.session.flush()
        self.invalidate_cache()

        logger.info("forbidden_keyword_removed", keyword_id=str(keyword_id))
        return True

    async def list_keywords(
        self,
        category: Optional[str] = None,
        is_active: Optional[bool] = True,
        limit: int = 100,
    ) -> List[ForbiddenKeyword]:
        """List forbidden keywords with optional filters."""
        stmt = select(ForbiddenKeyword)
        if category:
            stmt = stmt.where(ForbiddenKeyword.category == category)
        if is_active is not None:
            stmt = stmt.where(ForbiddenKeyword.is_active.is_(is_active))
        stmt = stmt.order_by(ForbiddenKeyword.severity.desc(), ForbiddenKeyword.keyword)
        stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
