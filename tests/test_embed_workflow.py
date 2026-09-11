# -*- coding: utf-8 -*-
"""Проверка embed_workflow (PNG metadata + соседний .json). Отдельный прогон — без tempfile-конфликтов."""
import os
import sys
import json
import time
import shutil
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from nodes import SimpleImageSave


def main():
    node = SimpleImageSave()
    arr = (np.random.rand(1, 8, 8, 3) * 255).astype(np.uint8) / 255.0
    images = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: arr))

    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "imgsave_wf_test")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        prompt = {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        extra = {"workflow": {"id": "abc", "nodes": [1, 2]}, "extra_pnginfo": {}}
        result = node.save_image(
            active=True, output_path=tmp, create_date_folder=False, create_processed_folder=False,
            prefix_1="wf", prefix_2="", separator="_", use_counter=True, embed_workflow=True,
            image_format="png", quality=90, images=images, prompt=prompt, extra_pnginfo=extra)
        saved = result["result"][1]
        json_path = os.path.splitext(saved)[0] + ".json"
        assert os.path.exists(json_path), "workflow json не сохранён"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("id") == "abc" and data.get("prompt"), data

        from PIL import Image
        img = Image.open(saved)
        meta = img.info.get("prompt")
        assert meta and json.loads(meta)["3"]["inputs"]["seed"] == 42, f"metadata prompt: {meta!r}"
        print("OK: embed workflow (PNG metadata + .json)")
    finally:
        time.sleep(0.5)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
