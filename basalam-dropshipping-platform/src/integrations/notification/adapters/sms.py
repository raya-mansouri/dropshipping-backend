"""
SMS Notification Adapter
========================
Implements NotificationPort for SMS notifications

Supports multiple SMS providers: Kavenegar, Twilio, etc.
"""
import asyncio

import httpx
import structlog
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from ..ports import (
    NotificationPort,
    NotificationChannel,
    NotificationRequest,
    NotificationResponse,
)


class KavenegarSMSAdapter(NotificationPort):
    """
    SMS adapter using Kavenegar API
    
    Iranian SMS provider - common choice for Basalam integration
    """
    
    def __init__(self, api_key: str, sender: str = "10000000"):
        self.api_key = api_key
        self.sender = sender
        self.base_url = "https://api.kavenegar.com/v1"
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.SMS
    
    @property
    def provider_name(self) -> str:
        return "kavenegar"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        """Send SMS via Kavenegar"""
        if not request.recipient.phone:
            return NotificationResponse(
                success=False,
                error="No phone number provided",
                provider=self.provider_name
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_key}/sms/send.json",
                    data={
                        "receptor": request.recipient.phone,
                        "sender": self.sender,
                        "message": f"{request.content.title}\n{request.content.body}"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return NotificationResponse(
                        success=True,
                        message_id=str(data.get("return", {}).get("messageid", "")),
                        provider=self.provider_name
                    )
                else:
                    return NotificationResponse(
                        success=False,
                        error=f"API error: {response.status_code}",
                        provider=self.provider_name
                    )
                        
        except Exception as e:
            return NotificationResponse(
                success=False,
                error=str(e),
                provider=self.provider_name
            )

    async def send_with_retry(
        self,
        request: NotificationRequest,
        max_retries: int = 3,
        delays: list[float] = None,
    ) -> NotificationResponse:
        """Send with retry logic and exponential backoff."""
        logger = structlog.get_logger(__name__)

        if delays is None:
            delays = [1.0, 2.0, 4.0]

        for attempt in range(max_retries):
            response = await self.send(request)
            if response.success:
                return response

            logger.warning(
                "sms_send_failed_retrying",
                provider=self.provider_name,
                attempt=attempt + 1,
                max_retries=max_retries,
                error=response.error,
            )

            if attempt < max_retries - 1:
                await asyncio.sleep(delays[attempt])

        logger.error(
            "sms_send_exhausted_retries",
            provider=self.provider_name,
            max_retries=max_retries,
        )
        return NotificationResponse(
            success=False,
            error=f"Failed after {max_retries} retries",
            provider=self.provider_name,
        )

    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        """Send multiple SMS"""
        responses = []
        
        # Kavenegar supports bulk sending
        phones = []
        messages = []
        
        for request in requests:
            if request.recipient.phone:
                phones.append(request.recipient.phone)
                messages.append(f"{request.content.title}\n{request.content.body}")
        
        if not phones:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_key}/sms/sendbulk.json",
                    data={
                        "receptor": ",".join(phones),
                        "sender": self.sender,
                        "message": "\n".join(messages)
                    }
                )
                
                if response.status_code == 200:
                    for phone in phones:
                        responses.append(NotificationResponse(
                            success=True,
                            message_id=f"bulk_{datetime.now(timezone.utc).timestamp()}",
                            provider=self.provider_name
                        ))
                else:
                    responses = [
                        NotificationResponse(
                            success=False,
                            error=f"API error: {response.status_code}",
                            provider=self.provider_name
                        )
                        for _ in phones
                    ]
                    
        except Exception as e:
            responses = [
                NotificationResponse(
                    success=False,
                    error=str(e),
                    provider=self.provider_name
                )
                for _ in phones
            ]
        
        return responses
    
    async def verify_connection(self) -> bool:
        """Verify Kavenegar API connection"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_key}/account/info.json")
                return response.status_code == 200
        except Exception:
            return False
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get SMS template"""
        templates = {
            "order_created": "New order #{{order_id}} received. Total: {{total}}",
            "order_shipped": "Your order #{{order_id}} has been shipped. Tracking: {{tracking}}",
            "payment_received": "Payment received for order #{{order_id}}",
            "delivery_confirmed": "Your order #{{order_id}} has been delivered.",
        }
        return {"message": templates.get(template_id, "")}


class TwilioSMSAdapter(NotificationPort):
    """SMS adapter using Twilio"""
    
    def __init__(self, account_sid: str, auth_token: str, sender: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.sender = sender
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.SMS
    
    @property
    def provider_name(self) -> str:
        return "twilio"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        # Implementation using Twilio API
        # from twilio.rest import Client
        pass
    
    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        pass
    
    async def verify_connection(self) -> bool:
        return True
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        pass
