import base64
from ultralytics import YOLO
import numpy as np
import cv2

model = YOLO(r"E:\fun2shh\Projects\fastapi_user_subscription_service\api\artifacts\nonTelescopicPipe\nonTelescopic.pt")
def count_objects_with_yolo(base64_image):
    # Decode the base64 image to a numpy array
    image_data = base64.b64decode(base64_image)
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Run detection
    results = model(img)

    # Initialize a blank canvas for drawing
    for result in results:
        if hasattr(result, 'boxes'):
            boxes = result.boxes.cpu().numpy()  # Ensure boxes are in numpy format
            for box in boxes:
                r = box.xyxy[0].astype(int)
                x_center = int((r[0] + r[2]) / 2)
                y_center = int((r[1] + r[3]) / 2)
                cv2.circle(img, (x_center, y_center), 3, (255, 255, 255), -1)  # Draw a green dot at the center

    # Count the detected objects
    count = sum(len(result.boxes.cpu().numpy()) for result in results if hasattr(result, 'boxes'))

    # Text settings
    font = cv2.FONT_HERSHEY_SIMPLEX
    text = f"Count: {count}"
    text_position = (10, 20)  # Top-right corner, adjust as necessary
    font_scale = 0.7
    font_color = (255, 255, 255)  # White
    line_type = 2

    # Put text on the image
    cv2.putText(img, text, text_position, font, font_scale, font_color, line_type)

    return img, str(count) + " objects"
