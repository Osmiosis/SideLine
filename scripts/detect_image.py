from ultralytics import YOLO
from pathlib import Path

# Download YOLOv8m on first run (~50MB to current directory or ~/.cache)
model = YOLO("yolov8m.pt")

# Use a built-in sample image from ultralytics or any local image
# Ultralytics ships with 'bus.jpg' as a default test
results = model("https://ultralytics.com/images/bus.jpg",
                device=0,  # GPU
                save=True,
                project="outputs",
                name="day1_image_test",
                exist_ok=True)

# Print what was detected
for r in results:
    print(f"Detections in image:")
    for box, cls, conf in zip(r.boxes.xyxy.cpu().numpy(),
                               r.boxes.cls.cpu().numpy(),
                               r.boxes.conf.cpu().numpy()):
        class_name = model.names[int(cls)]
        print(f"  {class_name}: {conf:.2f}")
    print(f"Saved to: {r.save_dir}")
