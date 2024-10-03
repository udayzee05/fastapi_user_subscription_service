
import cv2
import base64
import numpy as np
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator, colors
import torch
from torchvision.ops import nms
import platform
import pathlib

if platform.system() == 'Windows':
    pathlib.PosixPath = pathlib.WindowsPath
else:
    pathlib.WindowsPath = pathlib.PosixPath

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

    return process_image_base64_and_count(base64_image, "../api/artifacts/PVCPipeDetection/telescopic.pt")


def process_image_base64_and_count(base64_image, model_path, iou_threshold=0.2):
    """Load model, process a base64-encoded image to detect objects, filter overlapping boxes, draw circles, and return counts and processed image in base64."""
   
    # Load the YOLOv5 model
    model = torch.hub.load("ultralytics/yolov5", "custom", model_path, force_reload=True)
    model.conf = 0.25  # NMS confidence threshold
    model.imgsz = 640
    model.max_det = 3000  # Maximum number of detections per image
   
    # Class colors for visualization
    class_colors = {
        '1': (255, 255, 255),  # White
        '2': (0, 255, 0),  # Green
        '3': (0, 0, 255),  # Red
        '4': (255, 255, 0),  # Cyan
        '5': (255, 0, 255),  # Magenta
        '6': (0, 255, 255),  # Yellow
    }

    def filter_overlapping_boxes(detections, iou_threshold=0.2):
        """Filter detections to keep only the highest confidence box in case of significant overlap."""
        detections = detections.sort_values(by='confidence', ascending=False).reset_index(drop=True)
        boxes = detections[['xmin', 'ymin', 'xmax', 'ymax']].values.astype(np.float32)
        scores = detections['confidence'].values.astype(np.float32)

        # Convert to torch tensors
        boxes_tensor = torch.tensor(boxes)
        scores_tensor = torch.tensor(scores)

        # Apply NMS
        indices = nms(boxes_tensor, scores_tensor, iou_threshold)
       
        return detections.iloc[indices.tolist()]

    def draw_circles_and_count(image, detections):
        """Draw circles around detected objects and add counts to the image."""
        # Convert the input image to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
       
        # Filter detections to remove overlapping boxes
        filtered_detections = filter_overlapping_boxes(detections, iou_threshold)
       
        # Initialize total count
        total_sum = 0
       
        for _, row in filtered_detections.iterrows():
            xmin, ymin, xmax, ymax, confidence, class_id, class_name = row
           
            # Draw a circle at the center of the bounding box
            center_x = int((xmin + xmax) / 2)
            center_y = int((ymin + ymax) / 2)
            radius = int((xmax - xmin) / 4)  # Example radius size
            color = class_colors.get(str(int(class_name)), (255, 255, 255))  # Default to white if class_name not in color map
            thickness = 2
           
            # Draw the circle on the image
            cv2.circle(image_rgb, (center_x, center_y), radius, color, thickness)
           
            # Add the value of `class_id` to the total sum
            total_sum += int(class_id) + 1
       
        # Add the total sum to the image
        cv2.putText(image_rgb, f"{total_sum}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
       
        return image_rgb, total_sum

    # Decode the base64 image
    image_data = base64.b64decode(base64_image)
    np_img = np.frombuffer(image_data, np.uint8)
    image = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    # Inference using the model
    results = model(image)

    # Convert results to DataFrame
    detections_df = results.pandas().xyxy[0]
   
    # Draw circles, get counts, and return the processed image and count
    processed_image, total_count = draw_circles_and_count(image, detections_df)
   
    # Convert the processed image back to base64
    # _, buffer = cv2.imencode('.jpg', processed_image)
    # processed_image_base64 = base64.b64encode(buffer).decode('utf-8')
   
    return processed_image, str(total_count) + " objects"


# Example usage
# base64_image = "..."  # Replace with actual base64-encoded image string
# model_path = "/path/to/model/best.torchscript"
# processed_image_base64, count = process_image_base64_and_count(base64_image, model_path)



