"""
Email Notification Adapter
==========================
Implements NotificationPort for email notifications

Uses SMTP or email service providers (SendGrid, Mailgun, etc.)
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional, Dict, Any

from ..ports import (
    NotificationPort,
    NotificationChannel,
    NotificationRequest,
    NotificationResponse,
    NotificationPriority,
)


class EmailNotificationAdapter(NotificationPort):
    """
    Email notification adapter using SMTP
    
    Can be extended to use SendGrid, Mailgun, AWS SES, etc.
    """
    
    def __init__(
        self,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        from_email: str = "",
        from_name: str = "Basalam Platform"
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.EMAIL
    
    @property
    def provider_name(self) -> str:
        return "smtp"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        """Send email notification"""
        if not request.recipient.email:
            return NotificationResponse(
                success=False,
                error="No email address provided",
                provider=self.provider_name
            )
        
        try:
            # Build email
            msg = MIMEMultipart("alternative")
            msg["Subject"] = request.content.title
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = request.recipient.email
            
            # Plain text body
            text_body = MIMEText(request.content.body, "plain")
            msg.attach(text_body)
            
            # HTML body (if template provided)
            if request.content.template_id:
                html_body = self._render_html_template(request)
                if html_body:
                    html_part = MIMEText(html_body, "html")
                    msg.attach(html_part)
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            return NotificationResponse(
                success=True,
                message_id=f"email_{datetime.utcnow().timestamp()}",
                provider=self.provider_name
            )
            
        except Exception as e:
            return NotificationResponse(
                success=False,
                error=str(e),
                provider=self.provider_name
            )
    
    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        """Send multiple emails"""
        responses = []
        for request in requests:
            response = await self.send(request)
            responses.append(response)
        return responses
    
    async def verify_connection(self) -> bool:
        """Verify SMTP connection"""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
            return True
        except Exception:
            return False
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get email template"""
        # Could load from database or file
        templates = {
            "order_created": {
                "subject": "New Order Received - {{order_id}}",
                "html_template": "orders/order_created.html"
            },
            "order_shipped": {
                "subject": "Your Order Has Been Shipped - {{order_id}}",
                "html_template": "orders/order_shipped.html"
            },
            "payment_received": {
                "subject": "Payment Confirmed - {{order_id}}",
                "html_template": "payments/payment_received.html"
            },
        }
        return templates.get(template_id)
    
    def _render_html_template(self, request: NotificationRequest) -> Optional[str]:
        """Render HTML template with variables"""
        if not request.content.variables:
            return None
        
        # Simple template rendering
        template = request.content.body
        
        # Replace variables like {{variable_name}}
        for key, value in request.content.variables.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        
        return template


# Alternative: SendGrid Adapter
class SendGridEmailAdapter(NotificationPort):
    """Email adapter using SendGrid API"""
    
    def __init__(self, api_key: str, from_email: str, from_name: str = "Basalam"):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.EMAIL
    
    @property
    def provider_name(self) -> str:
        return "sendgrid"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        # Implementation using SendGrid API
        # import sendgrid
        # from sendgrid import SendGridAPIClient
        # from sendgrid.helpers.mail import Mail
        pass
    
    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        pass
    
    async def verify_connection(self) -> bool:
        return True
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        pass
