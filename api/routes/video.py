import logging
from fastapi import Depends,APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from api.core.oauth2 import get_current_user
from api.models.user import User
from api.core.db import db

import cv2
import time
import base64


router = APIRouter(prefix="/video", tags=["Video"])

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def frame_read():

    cap = cv2.VideoCapture(accessing_camera_link.link)
    logger.info(f"Camera Link: {accessing_camera_link.link} and Camera is opened {cap.isOpened()}")
    count = 0
    while True:
        count += 1
        ret, frame = cap.read()
        # print(ret)
        if not ret:
            cap.release()  # Release the video capture
            cap = cv2.VideoCapture(accessing_camera_link.link)
            continue

        frame_read.var = frame

        image = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)

        # Encode the frame as JPEG
        retu, jpeg = cv2.imencode(".jpg", image)

        # Check if encoding was successful
        if not retu:
            continue

        # Yield the frame as a response
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n\r\n"
        )

    # cap.release()
async def camera_opened(camera_link, max_attempts=5, attempt_interval=0.09):

    camera = cv2.VideoCapture(camera_link)
    try:
        camera_on = False
       
        logger.info(f"Camera Link: {camera_link} and Camera is opened {camera.isOpened() } type:{type(camera_link)}")
        for i in range(max_attempts):
            if camera.isOpened():
                logger.info("Camera Opened")
                camera_on = True
                break
            logger.warning("Attempt %d: Camera Not Opened", i+1)
            time.sleep(attempt_interval)
        else:
            logger.error("Failed to open camera after %d attempts", max_attempts)
            return camera_on

    except Exception as e:
        logger.error("Error occurred while opening camera: %s", e)
        return False

    finally:
        logger.info("Camera released")
        camera.release()

    return camera_on



@router.post("/inset_camera_link")
async def inset_camera_link(
    camera_link: dict, user: User = Depends(get_current_user)
):
    try:
        logger.info(f"Setting the camera_link: {camera_link}")

        new_field = "camera_link"
        new_value = camera_link["camera_link"]
        # user.append(new_value)
        return await user.update({}, {"$set": {new_field: new_value}}, upsert=True)

        # user.find({"email": "admin2@example.com"})

    except Exception as e:
        logger.error(e)

@router.get("/accessing_camera_link")
async def accessing_camera_link(user: User = Depends(get_current_user)):
    if user.role != "admin":
        return HTTPException(
            status_code=403,
            detail="Access forbidden: Requires admin role",
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    camera_link = None
    data = user.find({"email": user.email})

    # print(data)
    async for document in data:
        camera_link = document.camera_link

        break

    accessing_camera_link.link = camera_link

    if camera_link is None:
        return {"message": "No Camera link"}
   
    logger.info(f"Camera link found: {camera_link} and type is {type(camera_link)}")

    camera_on = await camera_opened(camera_link)

    if camera_link is not None and  camera_on:
        # print("Camera link found: ", camera_link)
        return {"camera_link": camera_link,}
    else:

        return {"message": "No Camera link"}

   
@router.get("/video_feed")
async def video_feed():

    return StreamingResponse(
        frame_read(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )




def capture_frame(camera_link):
    cap = cv2.VideoCapture(camera_link)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        return None

    ret, jpeg = cv2.imencode('.jpg', frame)
    if not ret:
        return None

    return base64.b64encode(jpeg.tobytes()).decode('utf-8')


@router.get("/capture_frame")
async def capture_frame_endpoint(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Access forbidden: Requires admin role"
        )

    camera_link = None
    data = user.find({"email": user.email})

    async for document in data:
        camera_link = document.camera_link
        break

    if not camera_link:
        return {"message": "No Camera link"}

    frame_base64 = capture_frame(camera_link)
    if not frame_base64:
        return {"message": "Failed to capture frame"}

    return {"frame": frame_base64}

