"""
Zarinpal Payment Provider
=========================
Implements the Zarinpal payment gateway (sandbox + production).

Uses httpx.AsyncClient for HTTP calls.
"""
import structlog
from decimal import Decimal
from typing import Dict, Any

import httpx

from src.core.config import get_settings
from .base import PaymentProvider

logger = structlog.get_logger(__name__)


class ZarinpalProvider(PaymentProvider):
    """Zarinpal payment gateway adapter."""

    URLS = {
        "sandbox": {
            "request": "https://sandbox.zarinpal.com/pg/v4/payment/request.json",
            "payment": "https://sandbox.zarinpal.com/pg/StartPay/",
            "verify": "https://sandbox.zarinpal.com/pg/v4/payment/verify.json",
        },
        "production": {
            "request": "https://api.zarinpal.com/pg/v4/payment/request.json",
            "payment": "https://www.zarinpal.com/pg/StartPay/",
            "verify": "https://api.zarinpal.com/pg/v4/payment/verify.json",
        },
    }

    # Persian error messages for known Zarinpal error codes
    ERROR_CODE_MESSAGES: Dict[int, str] = {
        -9: "خطای اعتبارسنجی",
        -10: "ترمینال شما غیرفعال است",
        -11: "درخواست مورد نظر یافت نشد",
        -12: "امکان ویرایش درخواست میسر نمی‌باشد",
        -21: "هیچ نوع عملیات مالی برای این تراکنش یافت نشد",
        -22: "تراکنش ناموفق",
        -33: "رقم تراکنش با رقم پرداخت شده مطابقت ندارد",
        -34: "سقف تقسیم تراکنش از لحاظ تعداد یا رقم عبور نموده",
        -40: "اجازه دسترسی به متد مربوطه وجود ندارد",
        -41: "اطلاعات ارسال شده مربوط به AdditionalData غیرمعتبر می‌باشد",
        -42: "مدت زمان معتبر طول عمر شناسه پرداخت باید بین 30 دقیقه تا 45 روز می‌باشد",
        -54: "درخواست مورد نظر آرشیو شده است",
    }

    def __init__(self) -> None:
        settings = get_settings()
        self.is_sandbox = settings.payment_env == "sandbox"
        self.merchant_id = (
            "1344b5d4-0048-11e8-94db-005056a205be"
            if self.is_sandbox
            else settings.zarinpal_merchant_id
        )
        env = "sandbox" if self.is_sandbox else "production"
        self.api_url = self.URLS[env]["request"]
        self.payment_url = self.URLS[env]["payment"]
        self.verify_url = self.URLS[env]["verify"]

        logger.info("zarinpal_provider_initialized", env=env)

    async def create_payment(
        self,
        amount: Decimal,
        callback_url: str,
        description: str = "شارژ کیف پول",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Create a Zarinpal payment request."""
        data: Dict[str, Any] = {
            "merchant_id": self.merchant_id,
            "amount": int(amount),
            "callback_url": callback_url,
            "description": description,
            "metadata": metadata or {},
        }

        logger.info(
            "zarinpal_create_payment",
            amount=int(amount),
            callback_url=callback_url,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    json=data,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                result = response.json()

            logger.info("zarinpal_create_response", result=result)

            if result.get("data", {}).get("code") == 100:
                authority = result["data"]["authority"]
                payment_url = f"{self.payment_url}{authority}"
                logger.info("zarinpal_payment_created", authority=authority)
                return {
                    "status": True,
                    "token": authority,
                    "url": payment_url,
                }

            error_msg = result.get("errors", {}).get(
                "message", "خطا در اتصال به درگاه پرداخت"
            )
            logger.error("zarinpal_create_failed", error=error_msg, response=result)
            return {"status": False, "message": error_msg}

        except Exception as e:
            logger.error("zarinpal_create_exception", error=str(e), exc_info=True)
            raise

    async def verify_payment(
        self,
        token: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Verify a Zarinpal payment."""
        data = {
            "merchant_id": self.merchant_id,
            "authority": token,
            "amount": int(amount),
        }

        logger.info("zarinpal_verify_payment", token=token, amount=int(amount))

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.verify_url,
                    json=data,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                result = response.json()

            logger.info("zarinpal_verify_response", result=result)

            data_section = result.get("data", {})
            code = data_section.get("code")

            # Code 100 = successful, 101 = already verified
            if code in (100, 101):
                ref_id = data_section.get("ref_id")
                logger.info(
                    "zarinpal_payment_verified",
                    ref_id=ref_id,
                    token=token,
                    code=code,
                )
                return {
                    "status": True,
                    "ref_id": ref_id,
                    "verification_code": code,
                }

            # -21 can also mean already processed — treat as success
            if code == -21:
                logger.warning("zarinpal_already_processed", token=token)
                return {
                    "status": True,
                    "ref_id": data_section.get("ref_id", token),
                    "verification_code": code,
                    "note": "Payment already processed",
                }

            # Map error code to Persian message
            error_message = self.ERROR_CODE_MESSAGES.get(
                code, "خطا در تایید پرداخت"
            )

            # Try to extract message from response errors
            errors = result.get("errors", [])
            if isinstance(errors, list) and errors:
                error_message = (
                    errors[0].get("message", error_message)
                    if isinstance(errors[0], dict)
                    else error_message
                )
            elif isinstance(errors, dict):
                error_message = errors.get("message", error_message)

            logger.warning(
                "zarinpal_verify_failed",
                code=code,
                message=error_message,
                token=token,
            )
            return {
                "status": False,
                "message": error_message,
                "code": code,
            }

        except Exception as e:
            logger.error(
                "zarinpal_verify_exception", token=token, error=str(e), exc_info=True
            )
            raise
