
import cv2
import base64
import numpy as np
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator, colors
import torch
from torchvision.ops import nms


# Load the segmentation model for pipe segmentation
pipe_segmentation_model = YOLO("api/artifacts/Segmentation/PipeSegmentation.pt")
# Load the model for counting objects
# counting_model = YOLO("models/nonTelescopic.pt")

def get_segmented_pipes(base64_image):
    # Decode the base64 string
    image_data = base64.b64decode(base64_image)
    nparr = np.fromstring(image_data, np.uint8)
    im0 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

   
    # Perform prediction
    results = pipe_segmentation_model.predict(im0)
    annotator = Annotator(im0, line_width=2)

    # Check if there are any masks in the results
    if results[0].masks is not None:
        clss = results[0].boxes.cls.cpu().tolist()
        masks = results[0].masks.xy
        bboxes = results[0].boxes.xywh.cpu().tolist()
        if bboxes:
            bbox = bboxes[0]  # Assuming only one major region
            mask = masks[0]
            cls = clss[0]
            annotator.seg_bbox(mask=mask, mask_color=colors(int(cls), True), det_label=pipe_segmentation_model.model.names[int(cls)])
           
            # Crop the bounding box region with a 20-pixel margin
            x, y, w, h = bbox
            margin = 1
            x1, y1 = int(x - w / 2 - margin), int(y - h / 2 - margin)
            x2, y2 = int(x + w / 2 + margin), int(y + h / 2 + margin)

            # Ensure coordinates are within image boundaries
            x1, y1 = max(x1, 0), max(y1, 0)
            x2, y2 = min(x2, im0.shape[1]), min(y2, im0.shape[0])

            cropped_image = im0[y1:y2, x1:x2]

            # Convert the cropped image to base64
            _, buffer = cv2.imencode('.jpg', cropped_image)
            cropped_base64 = base64.b64encode(buffer).decode('utf-8')

            return cropped_base64
    return None

def count_objects_with_yolo(base64_image):

    counting_model = YOLO("api/artifacts/metalSquarePipe/metalSquarePipe.pt")
    # Decode the base64 image to a numpy array
    image_data = base64.b64decode(base64_image)
    nparr = np.fromstring(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
       
    # Run detection
    results = counting_model.predict(img,conf=0.3)

    # Initialize a blank canvas for drawing
    for result in results:
        if hasattr(result, 'boxes'):
            boxes = result.boxes.cpu().numpy()  # Ensure boxes are in numpy format
            for box in boxes:
                # Adapted to match expected box structure, assuming box.xyxy[0] has [x1, y1, x2, y2]
                r = box.xyxy[0].astype(int)
                x_center = int((r[0] + r[2]) / 2)
                y_center = int((r[1] + r[3]) / 2)
                cv2.circle(img, (x_center, y_center), 8, (0, 255, 0), -1)  # Draw a green dot at the center

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

    # return img, int(count)
    return img, str(count) + " objects"


