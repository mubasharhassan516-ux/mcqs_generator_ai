"""
whatsapp_sender.py
==================
Sends the Google Form link to a WhatsApp number via Twilio's API with enhanced
messaging features, templates, and better error handling.

Setup:
    1. Sign up at https://www.twilio.com/ and get a free trial account.
    2. Activate the Twilio Sandbox for WhatsApp:
       https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
    3. Note your Account SID and Auth Token from the Twilio Console.
    4. Set the following environment variables (or add to .env):

          TWILIO_ACCOUNT_SID   = ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
          TWILIO_AUTH_TOKEN    = your_auth_token_here
          TWILIO_WHATSAPP_FROM = whatsapp:+14155238886   ← Twilio sandbox number

    5. The recipient must first send the sandbox join message to the Twilio
       number (e.g., "join <your-sandbox-word>") before messages can be
       delivered in sandbox mode.

    For production, use an approved Twilio WhatsApp Business number.
"""

import os
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── Read credentials from environment ────────────────────────────────────────
ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.environ.get(
    "TWILIO_WHATSAPP_FROM",
    "whatsapp:+14155238886",  # Twilio sandbox default
)

# Message templates
MESSAGE_TEMPLATES = {
    "default": (
        "📝 *{title}*\n\n"
        "Your AI-generated MCQ quiz is ready! Click the link below to start:\n\n"
        "🔗 {url}\n\n"
        "{stats}\n"
        "Good luck! 🎯\n\n"
        "_Sent by AI MCQ Generator Pro_"
    ),
    "brief": (
        "📝 *{title}*\n"
        "🔗 {url}\n"
        "{stats}"
    ),
    "detailed": (
        "📝 *{title}*\n\n"
        "✨ Your personalized MCQ quiz has been generated!\n\n"
        "📊 *Quiz Details:*\n"
        "{stats}\n\n"
        "🔗 *Link:* {url}\n\n"
        "💡 *Tips:*\n"
        "• Take your time with each question\n"
        "• Review explanations after answering\n"
        "• Share with friends for collaborative learning\n\n"
        "Good luck! 🎯\n\n"
        "_Powered by AI MCQ Generator Pro_"
    ),
    "teacher": (
        "👨‍🏫 *Quiz Ready: {title}*\n\n"
        "Your quiz has been created and is ready for students.\n\n"
        "📋 *Quiz Summary:*\n"
        "{stats}\n\n"
        "🔗 *Student Link:* {url}\n\n"
        "📊 *Results will be automatically collected in Google Sheets.\n\n"
        "Best regards,\n"
        "_AI MCQ Generator Pro_"
    )
}


def _normalise_number(phone: str) -> str:
    """
    Ensure the phone number starts with 'whatsapp:+' and the country code.
    Accepts formats: '+923001234567', '923001234567', '03001234567' (PK assumed).
    """
    if not phone:
        return ""
    
    phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Already in Twilio format
    if phone.startswith("whatsapp:"):
        return phone

    # Strip leading zeros or plus
    if phone.startswith("+"):
        return f"whatsapp:{phone}"

    # Pakistan local number without country code (10 digits starting with 0)
    if phone.startswith("0") and len(phone) == 11:
        return f"whatsapp:+92{phone[1:]}"

    # India local number (10 digits starting with 0)
    if phone.startswith("0") and len(phone) == 10:
        return f"whatsapp:+91{phone[1:]}"

    # US/Canada number (10 digits)
    if len(phone) == 10 and phone.isdigit():
        return f"whatsapp:+1{phone}"

    # Assume it already includes the country code
    if phone.isdigit():
        return f"whatsapp:+{phone}"
    
    return f"whatsapp:{phone}"


def _validate_phone_number(phone: str) -> tuple[bool, str]:
    """Validate phone number format and return (is_valid, formatted_number)."""
    try:
        formatted = _normalise_number(phone)
        
        # Basic validation
        if not formatted or len(formatted) < 15:  # whatsapp:+XX... minimum length
            return False, formatted
        
        # Check if it has the correct prefix
        if not formatted.startswith("whatsapp:+"):
            return False, formatted
        
        # Extract the number part and check if it has enough digits
        number_part = formatted.replace("whatsapp:+", "")
        if len(number_part) < 10 or not number_part.isdigit():
            return False, formatted
        
        return True, formatted
    except Exception:
        return False, phone


def _format_stats(question_count: int, difficulty: str = None, 
                  topics: List[str] = None, form_url: str = None) -> str:
    """Format statistics for the message."""
    stats = []
    
    if question_count:
        stats.append(f"📊 Questions: {question_count}")
    
    if difficulty:
        # Capitalize difficulty
        difficulty_map = {
            "easy": "Easy 🟢",
            "medium": "Medium 🟡",
            "hard": "Hard 🔴",
            "expert": "Expert ⚫",
            "mixed": "Mixed 🎯"
        }
        stats.append(f"🎯 Difficulty: {difficulty_map.get(difficulty, difficulty)}")
    
    if topics and len(topics) > 0:
        topic_str = ", ".join(topics[:3])
        if len(topics) > 3:
            topic_str += f" and {len(topics) - 3} more"
        stats.append(f"📚 Topics: {topic_str}")
    
    if form_url and "demo" in form_url:
        stats.append("⚠️ *Demo Mode* - Configure Google Forms for full features")
    
    return "\n".join(stats) if stats else ""


def send_whatsapp_message(
    to_phone: str,
    form_url: str,
    form_title: str = "Your MCQ Quiz",
    question_count: int = 0,
    difficulty: str = None,
    topics: List[str] = None,
    template: str = "default",
    media_url: str = None,
) -> Dict[str, Any]:
    """
    Send a WhatsApp message with the Google Form link.

    Parameters
    ----------
    to_phone      : recipient's phone number (any reasonable format)
    form_url      : the respondent-facing Google Form URL
    form_title    : title of the quiz (for the message body)
    question_count: number of questions (optional, included in message)
    difficulty    : difficulty level of the quiz
    topics        : list of topics covered
    template      : message template to use (default, brief, detailed, teacher)
    media_url     : optional media URL to attach (image preview, etc.)

    Returns
    -------
    dict with keys: success (bool), sid (str | None), error (str | None)
    """
    
    # Validate phone number
    is_valid, formatted_number = _validate_phone_number(to_phone)
    if not is_valid:
        logger.warning(f"Invalid phone number format: {to_phone}")
        return {
            "success": False,
            "sid": None,
            "error": f"Invalid phone number format: {to_phone}",
            "demo": False,
            "formatted_number": formatted_number
        }

    # Check credentials
    if not ACCOUNT_SID or not AUTH_TOKEN:
        logger.warning(
            "Twilio credentials not set – returning demo response. "
            "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in your .env file."
        )
        
        # Return a demo response with message preview
        stats = _format_stats(question_count, difficulty, topics, form_url)
        template_data = {
            "title": form_title,
            "url": form_url,
            "stats": stats
        }
        message_preview = MESSAGE_TEMPLATES.get(template, MESSAGE_TEMPLATES["default"]).format(**template_data)
        
        return {
            "success": False,
            "sid": None,
            "error": "Twilio credentials not configured",
            "demo": True,
            "message_preview": message_preview,
            "to": formatted_number,
            "formatted_number": formatted_number
        }

    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
    except ImportError:
        raise ImportError(
            "twilio package is required. Run: pip install twilio"
        )

    # Format statistics
    stats = _format_stats(question_count, difficulty, topics, form_url)
    
    # Build message using template
    template_data = {
        "title": form_title,
        "url": form_url,
        "stats": stats
    }
    
    body = MESSAGE_TEMPLATES.get(template, MESSAGE_TEMPLATES["default"]).format(**template_data)

    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        
        # Prepare message parameters
        message_params = {
            "from_": FROM_NUMBER,
            "body": body,
            "to": formatted_number,
        }
        
        # Add media if provided
        if media_url:
            message_params["media_url"] = [media_url]
        
        # Send message
        message = client.messages.create(**message_params)
        
        logger.info(
            "WhatsApp message sent to %s | SID: %s | Template: %s", 
            formatted_number, message.sid, template
        )
        
        return {
            "success": True,
            "sid": message.sid,
            "error": None,
            "demo": False,
            "to": formatted_number,
            "status": message.status,
            "date_sent": message.date_sent.isoformat() if message.date_sent else None,
            "formatted_number": formatted_number
        }

    except TwilioRestException as e:
        logger.error("Twilio API error: %s", e)
        
        # Provide helpful error messages based on status code
        error_msg = str(e)
        if e.status == 400:
            if "not a valid phone number" in str(e).lower():
                error_msg = f"Invalid phone number format: {to_phone}"
            elif "not in sandbox" in str(e).lower():
                error_msg = "Recipient hasn't joined the WhatsApp sandbox. They need to send 'join <your-sandbox-word>' to the Twilio number first."
        elif e.status == 401:
            error_msg = "Twilio authentication failed. Check your Account SID and Auth Token."
        elif e.status == 403:
            error_msg = "Permission denied. Check your Twilio account permissions."
        elif e.status == 429:
            error_msg = "Rate limit exceeded. Please try again later."
        
        return {
            "success": False,
            "sid": None,
            "error": error_msg,
            "demo": False,
            "to": formatted_number,
            "status_code": e.status,
            "formatted_number": formatted_number
        }

    except Exception as e:
        logger.error("Failed to send WhatsApp message: %s", e)
        return {
            "success": False,
            "sid": None,
            "error": str(e),
            "demo": False,
            "to": formatted_number,
            "formatted_number": formatted_number
        }


def send_bulk_whatsapp_messages(
    recipients: List[str],
    form_url: str,
    form_title: str = "Your MCQ Quiz",
    question_count: int = 0,
    difficulty: str = None,
    topics: List[str] = None,
    template: str = "default",
) -> Dict[str, Any]:
    """
    Send WhatsApp messages to multiple recipients.
    
    Returns summary of successful and failed sends.
    """
    results = {
        "total": len(recipients),
        "successful": 0,
        "failed": 0,
        "details": []
    }
    
    for phone in recipients:
        result = send_whatsapp_message(
            to_phone=phone,
            form_url=form_url,
            form_title=form_title,
            question_count=question_count,
            difficulty=difficulty,
            topics=topics,
            template=template
        )
        
        if result.get("success"):
            results["successful"] += 1
        else:
            results["failed"] += 1
        
        results["details"].append({
            "phone": phone,
            "success": result.get("success", False),
            "error": result.get("error"),
            "formatted_number": result.get("formatted_number")
        })
    
    return results


def get_whatsapp_message_status(message_sid: str) -> Dict[str, Any]:
    """Get the status of a sent WhatsApp message."""
    if not ACCOUNT_SID or not AUTH_TOKEN:
        return {"error": "Twilio credentials not configured"}
    
    try:
        from twilio.rest import Client
        
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        message = client.messages(message_sid).fetch()
        
        return {
            "sid": message.sid,
            "status": message.status,
            "to": message.to,
            "from": message.from_,
            "date_sent": message.date_sent.isoformat() if message.date_sent else None,
            "date_created": message.date_created.isoformat() if message.date_created else None,
            "error_code": message.error_code,
            "error_message": message.error_message
        }
    except Exception as e:
        logger.error(f"Failed to get message status: {e}")
        return {"error": str(e)}


def test_whatsapp_configuration() -> Dict[str, Any]:
    """Test Twilio WhatsApp configuration."""
    results = {
        "credentials_set": bool(ACCOUNT_SID and AUTH_TOKEN),
        "from_number": FROM_NUMBER,
        "account_sid_prefix": ACCOUNT_SID[:6] + "..." if ACCOUNT_SID else None,
        "errors": []
    }
    
    if not results["credentials_set"]:
        results["errors"].append("Twilio credentials not set in environment variables")
        return results
    
    try:
        from twilio.rest import Client
        
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        
        # Test authentication by fetching account info
        account = client.api.accounts(ACCOUNT_SID).fetch()
        results["account_name"] = account.friendly_name
        results["account_status"] = account.status
        results["account_type"] = account.type
        
        # Test WhatsApp sender number
        if FROM_NUMBER:
            try:
                # Try to fetch message capabilities (limited test)
                incoming_numbers = client.incoming_phone_numbers.list(limit=1)
                results["sender_number_configured"] = True
            except:
                results["sender_number_configured"] = False
                results["errors"].append("WhatsApp sender number may not be configured")
        else:
            results["errors"].append("FROM_NUMBER not set")
        
    except Exception as e:
        results["errors"].append(f"Authentication failed: {str(e)}")
    
    return results