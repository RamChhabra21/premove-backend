from firebase_admin import messaging
from app.core.logging_config import logger

def send_fcm_notification(token: str, title: str, body: str, data: dict = None):
    """
    Sends a silent data-only push notification to a specific device token.
    No notification block = onMessageReceived is always called, even in background.
    """
    if not token:
        logger.warning("FCM attempt with empty token, skipping.")
        return None

    try:
        message = messaging.Message(
            data={
                **(data or {}),
                "title": title,
                "body": body,
            },
            token=token,
            android=messaging.AndroidConfig(
                priority="high",
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        content_available=True
                    )
                ),
            ),
        )

        response = messaging.send(message)
        logger.info(f"Successfully sent FCM message: {response}")
        return response

    except Exception as e:
        logger.error(f"Error sending FCM message: {e}")
        return None