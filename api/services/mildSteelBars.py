import base64
import numpy as np
import cv2
import os
from ultralytics.utils.plotting import Annotator, colors
from ultralytics import YOLO  # Assuming you're using the YOLOv5 or YOLOv8 library
from torchvision.ops import nms  # Importing NMS from torchvision
import torch  # Required for tensor operations


# Load the segmentation model for pipe segmentation
pipe_segmentation_model = YOLO("../api/artifacts/Segmentation/PipeSegmentation.pt")
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
    """
    Detects objects in an image using YOLO model, counts them, and returns the count and modified image.
    
    :param img: Path to the image file
    :return: Modified image with object count and a string of the count
    """
    # Initialize the YOLO model
    model = YOLO("../api/artifacts/metalBars/mild_metal_bars.pt")

    
    # Decode the base64 image to a numpy array
    image_data = base64.b64decode(base64_image)
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Read the image
    # img = cv2.imread(img)
    img1 = img.copy()

    # Run detection
    results = model(img1, conf=0.3, max_det=700)

    # Extract boxes, scores, and class IDs from results
    boxes = results[0].boxes.xyxy
    scores = results[0].boxes.conf
    class_ids = results[0].boxes.cls

    # No need to re-create tensors, use .clone().detach() to prevent the warning
    boxes_tensor = boxes.clone().detach()
    scores_tensor = scores.clone().detach()

    # Apply NMS using torchvision's nms function
    keep_indices = nms(boxes_tensor, scores_tensor, iou_threshold=0.1)

    # Filter boxes, scores, and class IDs based on NMS results
    boxes = boxes[keep_indices]
    scores = scores[keep_indices]
    class_ids = class_ids[keep_indices]

    height_original, width_original = img.shape[:2]
    height_resized, width_resized = img1.shape[:2]
    scale_x = width_original / width_resized
    scale_y = height_original / height_resized

    count = 0

    # Loop through detected objects and count
    for i in range(len(boxes)):
        cls = int(class_ids[i]) + 1  # Add +1 here to adjust class ID for counting
        count += cls
        x1, y1, x2, y2 = boxes[i]

        x1 = int(x1 * scale_x)
        y1 = int(y1 * scale_y)
        x2 = int(x2 * scale_x)
        y2 = int(y2 * scale_y)

        center_x = int((x1 + x2) / 2)
        center_y = int((y1 + y2) / 2)

        bbox_width = x2 - x1
        bbox_height = y2 - y1
        radius = int(max(bbox_width, bbox_height) * 0.15)

        # Draw circles on the image at the object center
        cv2.circle(img, (center_x, center_y), radius=radius, color=(255, 255, 255), thickness=-2)

    # Add the total object count to the image
    cv2.putText(img, f"Total: {count}", (20, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (225, 0, 255), 2)

    # Save the modified image
    cv2.imwrite("output_image.jpg", img)

    # Return the processed image and object count
    return img, str(count) + " objects"


# # Example usage
# img_path = r"C:\Users\udayz\Downloads\IMG_20240924_113147170_HDR_AE.jpg"
# img, count = count_objects_with_yolo(img_path)
