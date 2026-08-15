import firebase_admin
from firebase_admin import credentials, messaging
from app.core.config import settings
import os

# Initialize Firebase Admin SDK if not already initialized
if not firebase_admin._apps:
    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        import json
        cred_dict = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    elif settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
    else:
        options = {"projectId": settings.FIREBASE_PROJECT_ID} if settings.FIREBASE_PROJECT_ID else {}
        firebase_admin.initialize_app(options=options)

message = messaging.Message(
    notification=messaging.Notification(
        title="Premove Test",
        body="FCM is working!",
    ),
    token="fiT7AIUqT-GTgCtBD52X7f:APA91bGfDRpmXdc-ZQl0eYtPj7VInAA2BzzxnywMddws40w5x_f8Xkx6Y1Qe9uZ4S7myNBa259fFFkojx2LI54WwPkbbbNaAtGE07_W7azfq27wlHCn8D-s",
)

response = messaging.send(message)
print(response)