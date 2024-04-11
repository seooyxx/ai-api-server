import cv2
import torch
import numpy as np
from PIL import Image
from ultralytics import YOLO
import head_segmentation.segmentation_pipeline as seg_pipeline

class FaceDetector: 
    def __init__(self, model_path):
        self.model = YOLO(model_path, task='detect')
        self.warmup_model(imgsz=640)  
        self.original_image = None
        self.results = None

    def warmup_model(self, imgsz=640):
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        dummy_img = torch.zeros((1, 3, imgsz, imgsz), device=device)
        self.model.predict(dummy_img, task='detect')


    def detect(self, image_paths, imgsz=640, max_det=1):
        """
        Args:
            image_paths (List[numpy.ndarray]): A List of images for detecting.
            imgsz (int, optional): Resizing size. Defaults to 640.
            max_det (int, optional): Maximum # of detections per image. Defaults to 1.

        Returns:
            Python generator of Results.
        """
        self.original_image = image_paths
        self.results = self.model(self.original_image, 
                                  max_det=max_det, 
                                  imgsz=imgsz,)
        return self.results

    def crop_faces(self, margin):
        """
        Args:
            margin (float): A margin value to add around the detected face bbox.

        Returns:
            List[numpy.ndarray]: A list of cropped images containing the detected faces.
        """
        cropped_images = []
        for i, r in enumerate(self.results):
            for box in r.boxes.xyxy:
                x1, y1, x2, y2 = map(lambda x: int(x.item()), box[:4])
                new_x1, new_y1, new_x2, new_y2 = self.calculate_margins(x1, y1, x2, y2, margin, i)
                cropped_img = self.original_image[i][new_y1:new_y2, new_x1:new_x2]
                cropped_images.append(cropped_img)
        return cropped_images

    def calculate_margins(self, x1, y1, x2, y2, margin, i):
        bbox_width = x2 - x1
        bbox_height = y2 - y1
        image_width, image_height = self.original_image[i].shape[1], self.original_image[i].shape[0]
        new_x1 = max(0, x1 - margin * 0.2 * bbox_width)
        new_y1 = max(0, y1 - margin * 0.3 * bbox_height)
        new_x2 = min(image_width, x2 + margin * 0.2 * bbox_width) 
        new_y2 = min(image_height, y2 + margin * 0.2 * bbox_height) 
        return int(new_x1), int(new_y1), int(new_x2), int(new_y2)
    
class HeadSegmenter:
    def __init__(self, device='cpu'):
        self.device = device
        self.segmentation_pipeline = seg_pipeline.HumanHeadSegmentationPipeline(device=device)
        self.fill_color = [0x79, 0x00, 0x30] # crimson

    def segment_and_color(self, images):
        """
        Args:
            List[numpy.ndarray]: A list of (cropped) images.  

        Returns:
            List[PIL.Image.Image]
        """
        segmented_images = []
        for image in images:
            segmented_image = self.segment_head(image)
            segmented_images.append(Image.fromarray(segmented_image))
        return segmented_images

    def segment_head(self, image):
        segmentation_map = self.segmentation_pipeline.predict(image)
        segmentation_overlay = cv2.cvtColor(segmentation_map, cv2.COLOR_GRAY2RGB)
        segmentation_overlay[segmentation_map == 0] = self.fill_color
        result_image = np.where(segmentation_overlay == self.fill_color, segmentation_overlay, image)
        return result_image.astype('uint8')

def align_pil_image(img: Image.Image)->Image.Image:
    if hasattr(img, '_getexif'):
        exif = img._getexif()
        if exif is not None:
            orientation = exif.get(0x0112)
            if orientation == 3:
                img = img.transpose(Image.ROTATE_180)
            elif orientation == 6:
                img = img.transpose(Image.ROTATE_270)
            elif orientation == 8:
                img = img.transpose(Image.ROTATE_90)
    return img

if __name__ == "__main__":
    import time
    face_detector = FaceDetector('yolov8n-face.onnx')
    head_segmenter = HeadSegmenter('cuda')
    img = align_pil_image(Image.open('test.jpg'))

    start = time.time()
    yolo_res = face_detector.detect([np.array(img)])
    d_time = time.time()
    crop_res = face_detector.crop_faces(margin=0.5)
    c_time = time.time()
    seg_res = head_segmenter.segment_and_color(crop_res)
    s_time = time.time()
    print("------------------------------------")
    print(f"Total Time: {s_time - start}")
    print("------------------------------------")
    print(f"Detection Time: {d_time - start}")
    print("------------------------------------")
    print(f"Cropping Time: {c_time - d_time}")
    print("------------------------------------")
    print(f"Segmentation Time: {s_time - c_time}")
    print("------------------------------------")
    Image.fromarray(crop_res[0]).save('cropped_face.jpg')
    seg_res[0].save('segmented_face.jpg')
    print(yolo_res)