# -*- coding: utf-8 -*-
"""Локальный тест логики SimpleImageSave без ComfyUI (без torch)."""
import os
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# folder_paths не импортируется вне ComfyUI — nodes.py это обрабатывает.
from nodes import SimpleImageSave


def make_fake_images(n: int = 3):
    """Маскируем .cpu().numpy() без torch."""
    import numpy as np
    arr = (np.random.rand(n, 8, 16, 3) * 255).astype(np.uint8)
    return SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: arr / 255.0))


def test_counter_mode():
    node = SimpleImageSave()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = os.path.join(tmp, "test")
        result = node.save_image(
            active=True, output_path=out_dir, create_date_folder=False, create_processed_folder=False,
            prefix_1="cat", prefix_2="", separator="_", use_counter=True, embed_workflow=False,
            image_format="png", quality=90, images=make_fake_images(3), prompt={"a": 1}, extra_pnginfo=None)
        paths = [os.path.join(out_dir, f"cat_{i:04d}.png") for i in (1, 2, 3)]
        assert all(os.path.exists(p) for p in paths), f"не найдены: {[p for p in paths if not os.path.exists(p)]}"

        # повторный вызов — счётчик должен продолжить с 4 (сканирование папки)
        result = node.save_image(
            active=True, output_path=out_dir, create_date_folder=False, create_processed_folder=False,
            prefix_1="cat", prefix_2="", separator="_", use_counter=True, embed_workflow=False,
            image_format="png", quality=90, images=make_fake_images(1), prompt=None, extra_pnginfo=None)
        assert os.path.exists(os.path.join(out_dir, "cat_0004.png")), "счётчик не продолжил с 4"

        saved_path = result["result"][1]
        filename_text = result["result"][2]
        assert saved_path and os.path.isabs(saved_path)
        assert filename_text == "cat_0004", f"filename_text={filename_text!r}"
    print("OK: counter mode")


def test_time_mode():
    node = SimpleImageSave()
    with tempfile.TemporaryDirectory() as tmp:
        result = node.save_image(
            active=True, output_path=tmp, create_date_folder=False, create_processed_folder=False,
            prefix_1="dog", prefix_2="", separator="_", use_counter=False, embed_workflow=False,
            image_format="jpg", quality=85, images=make_fake_images(1), prompt=None, extra_pnginfo=None)
        saved = result["result"][1]
        assert saved and os.path.exists(saved), "файл не сохранён"
        ts = datetime.now().strftime("%H%M%S")
        assert ts in os.path.basename(saved).split("_")[1], f"нет таймстампа: {os.path.basename(saved)}"
    print("OK: time mode (jpg)")


def test_date_and_processed_folders():
    node = SimpleImageSave()
    with tempfile.TemporaryDirectory() as tmp:
        result = node.save_image(
            active=True, output_path=tmp, create_date_folder=True, create_processed_folder=True,
            prefix_1="", prefix_2="", separator="_", use_counter=True, embed_workflow=False,
            image_format="webp", quality=80, images=make_fake_images(1), prompt=None, extra_pnginfo=None)
        today = datetime.now().strftime("%Y-%m-%d")
        expected_dir = os.path.join(tmp, today, "Processed")
        saved = result["result"][1]
        assert saved.startswith(expected_dir), f"ожидалось {expected_dir}, получено {saved}"
    print("OK: date + processed folders (webp)")


def test_empty_prefix():
    node = SimpleImageSave()
    with tempfile.TemporaryDirectory() as tmp:
        result = node.save_image(
            active=True, output_path=tmp, create_date_folder=False, create_processed_folder=False,
            prefix_1="", prefix_2="", separator="_", use_counter=True, embed_workflow=False,
            image_format="png", quality=90, images=make_fake_images(2), prompt=None, extra_pnginfo=None)
        assert os.path.exists(os.path.join(tmp, "0001.png")), "пустой префикс -> имя только счётчик"
        assert os.path.exists(os.path.join(tmp, "0002.png"))
    print("OK: empty prefix")


def test_active_off():
    node = SimpleImageSave()
    result = node.save_image(
        active=False, output_path="", create_date_folder=False, create_processed_folder=False,
        prefix_1="x", prefix_2="", separator="_", use_counter=True, embed_workflow=False,
        image_format="png", quality=90, images=make_fake_images(1), prompt=None, extra_pnginfo=None)
    assert result["ui"]["images"] == [] and result["result"][1] == ""
    print("OK: active OFF")


if __name__ == "__main__":
    test_counter_mode()
    test_time_mode()
    test_date_and_processed_folders()
    test_empty_prefix()
    test_active_off()
    print("\nВсе тесты пройдены ✅")
