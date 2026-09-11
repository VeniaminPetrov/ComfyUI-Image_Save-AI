# -*- coding: utf-8 -*-
"""
Simple Image Save — упрощённый нод сохранения изображений ComfyUI.

Возможности (намеренно минимум):
  * Сохранение в ЛЮБОЙ путь (абсолютный или относительный от output/).
  * Опциональная папка по текущей дате (YYYY-MM-DD) и подпапка "Processed".
  * Имя файла: prefix_1 + prefix_2 (+ разделитель), счётчик (0001, 0002…) или время (HHMMSS).
  * Форматы: PNG / JPG / WebP (качество для lossy).
  * Опционально: embed workflow в метаданные PNG и сохранение соседнего .json.

Выходы: IMAGE, saved_path (абсолютный путь первой картинки), filename_text (имя без расширения).
"""
import os
import json
import re
from datetime import datetime

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

try:
    import folder_paths  # доступен только внутри ComfyUI
except ImportError:  # для локального теста без ComfyUI
    folder_paths = None


class SimpleImageSave:
    """Сохраняет батч изображений в заданную папку с предсказуемыми именами."""

    WINDOWS_FORBIDDEN = set('<>:"|?*')
    MAX_PATH_LEN = 260

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory() if folder_paths else os.path.join(os.getcwd(), "output")
        self.is_windows = os.name == "nt"
        self._counters = {}

    # ------------------------------------------------------------------ #
    #  Спецификация нода для ComfyUI
    # ------------------------------------------------------------------ #
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "active": ("BOOLEAN", {"default": True, "label_on": "🟢 ON", "label_off": "🔴 OFF"}),
                "output_path": ("STRING", {"default": "", "placeholder": "абсолютный путь или подпапка от output/"}),
                "create_date_folder": ("BOOLEAN", {"default": True, "label_on": "📅 папка по дате ON", "label_off": "OFF"}),
                "create_processed_folder": ("BOOLEAN", {"default": False, "label_on": "🗂 подпапка Processed ON", "label_off": "OFF"}),
                "prefix_1": ("STRING", {"default": "Image"}),
                "prefix_2": ("STRING", {"default": ""}),
                "separator": ("STRING", {"default": "_"}),
                "use_counter": ("BOOLEAN", {"default": True, "label_on": "# счётчик ON", "label_off": "⏱ время (HHMMSS)"}),
                "embed_workflow": ("BOOLEAN", {"default": True, "label_on": "📦 embed workflow ON", "label_off": "OFF"}),
                "image_format": (["png", "jpg", "webp"], {"default": "png"}),
                "quality": ("INT", {"default": 90, "min": 50, "max": 100, "step": 1, "display": "slider", "label": "JPG/WebP Quality"}),
                "images": ("IMAGE",),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "saved_path", "filename_text")
    FUNCTION = "save_image"
    OUTPUT_NODE = True
    CATEGORY = "Utility/Image"
    DESCRIPTION = "Сохранение изображений в заданную папку (простая, предсказуемая нумерация)."

    # ------------------------------------------------------------------ #
    #  Вспомогательные методы
    # ------------------------------------------------------------------ #
    def _validate_path(self, full_path: str) -> bool:
        """Базовая проверка пути: не пустой, не слишком длинный (Win), без запрещённых символов."""
        if not full_path:
            return False
        norm = os.path.normpath(full_path)
        if self.is_windows:
            if len(norm) > self.MAX_PATH_LEN:
                print(f"[ImageSave] Путь слишком длинный (> {self.MAX_PATH_LEN}): {norm}")
                return False
            drive, tail = os.path.splitdrive(norm)  # двоеточие диска — легитимно, проверяем остаток
            if any(ch in self.WINDOWS_FORBIDDEN for ch in tail):
                print(f"[ImageSave] Запрещённые символы в пути: {norm}")
                return False
        return True

    def _resolve_target_dir(self, output_path: str) -> str | None:
        """Нормализует выходной путь: абсолютный либо относительный от output/ ComfyUI."""
        if not output_path or not output_path.strip():
            return self.output_dir
        p = os.path.normpath(output_path.strip())
        target = p if os.path.isabs(p) else os.path.join(self.output_dir, p)
        if not self._validate_path(target):
            return None
        return target

    def _next_filename(self, base_dir: str, base_name: str, ext: str, separator: str, use_counter: bool) -> str:
        """Возвращает свободный полный путь. Счётчик — по папке (сканируем существующие файлы)."""
        if not use_counter:
            ts = datetime.now().strftime("%H%M%S")
            name_part = "image" if not base_name else base_name
            filename = f"{name_part}{separator}{ts}.{ext}"
            full = os.path.join(base_dir, filename)
            n = 1
            while os.path.exists(full):
                filename = f"{name_part}{separator}{ts}_{n}.{ext}"
                full = os.path.join(base_dir, filename)
                n += 1
            return full

        # Режим счётчика: ищем максимальный номер по шаблону prefix_sep_NNNN.ext
        if base_name:
            pattern = re.compile(rf"^{re.escape(base_name)}{re.escape(separator)}(\d+)\.{re.escape(ext)}$")
            scan_key = f"{base_name}{separator}"
        else:
            # Пустой префикс: имя — только 4-значный счётчик (защита от ложных срабатываний на другие файлы)
            pattern = re.compile(rf"^(\d{{4}})\.{re.escape(ext)}$")
            scan_key = separator  # уникальная метка «без префикса» в этой папке

        highest = 0
        try:
            for entry in os.scandir(base_dir):
                if entry.is_file():
                    m = pattern.match(entry.name)
                    if m and len(m.group(1)) < 6:  # 6+ цифр — считаем таймстампом, не счётчиком
                        highest = max(highest, int(m.group(1)))
        except FileNotFoundError:
            pass

        counter = self._counters.get(scan_key, 0)
        counter = max(counter, highest + 1)

        while True:
            if base_name:
                filename = f"{base_name}{separator}{counter:04d}.{ext}"
            else:
                filename = f"{counter:04d}.{ext}"
            full = os.path.join(base_dir, filename)
            if not os.path.exists(full):
                self._counters[scan_key] = counter + 1
                return full
            counter += 1

    def _save_workflow_json(self, image_path: str, prompt, extra_pnginfo) -> None:
        """Сохраняет соседний .json с рабочим процессом (как встроенный workflow ComfyUI)."""
        try:
            data = {}
            if extra_pnginfo and "workflow" in extra_pnginfo:
                data = dict(extra_pnginfo["workflow"])
                if "prompt" not in data:
                    data["prompt"] = prompt
            else:
                data = {"id": str(hash(str(prompt)))[:36] if prompt else "", "prompt": prompt}
            with open(os.path.splitext(image_path)[0] + ".json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ImageSave] Не удалось сохранить workflow JSON: {e}")

    # ------------------------------------------------------------------ #
    #  Основная функция нода
    # ------------------------------------------------------------------ #
    def save_image(self, active, output_path, create_date_folder, create_processed_folder,
                   prefix_1, prefix_2, separator, use_counter, embed_workflow, image_format, quality,
                   images, prompt=None, extra_pnginfo=None, unique_id=None):

        if not active:
            return {"ui": {"images": []}, "result": (images, "", "")}

        base_dir = self._resolve_target_dir(output_path)
        if base_dir is None:
            print("[ImageSave] Некорректный output_path — сохранение отменено.")
            return {"ui": {"images": []}, "result": (images, "", "")}

        if create_date_folder:
            base_dir = os.path.join(base_dir, datetime.now().strftime("%Y-%m-%d"))
        if create_processed_folder:
            base_dir = os.path.join(base_dir, "Processed")

        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception as e:
            print(f"[ImageSave] Не удалось создать папку {base_dir}: {e}")
            return {"ui": {"images": []}, "result": (images, "", "")}

        img_arrays = np.clip(255.0 * images.cpu().numpy(), 0, 255).astype(np.uint8)
        parts = [p for p in ((prefix_1 or "").strip(), (prefix_2 or "").strip()) if p]
        base_name = separator.join(parts) if parts else ""

        full_paths = []
        ui_images = []

        for img_array in img_arrays:
            try:
                filepath = self._next_filename(base_dir, base_name, image_format.lower(), separator or "_", use_counter)
                img = Image.fromarray(img_array)

                if image_format.lower() == "png":
                    metadata = PngInfo()
                    if embed_workflow and (prompt or extra_pnginfo):
                        # PIL 12.x: add_text требует str; json.dumps гарантирует строку.
                        # Pillow >= 9.2 кодирует как iTXt — кириллица в значениях безопасна.
                        if prompt is not None:
                            metadata.add_text("prompt", json.dumps(prompt, ensure_ascii=False))
                        if extra_pnginfo:
                            for key, value in (extra_pnginfo or {}).items():
                                v = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                                metadata.add_text(str(key), v)
                        self._save_workflow_json(filepath, prompt, extra_pnginfo)
                    img.save(filepath, pnginfo=metadata, compress_level=4)

                elif image_format.lower() == "jpg":
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(filepath, quality=int(quality), optimize=True)
                    if embed_workflow and (prompt or extra_pnginfo):
                        self._save_workflow_json(filepath, prompt, extra_pnginfo)

                elif image_format.lower() == "webp":
                    img.save(filepath, quality=int(quality), method=4)
                    if embed_workflow and (prompt or extra_pnginfo):
                        self._save_workflow_json(filepath, prompt, extra_pnginfo)

                else:
                    print(f"[ImageSave] Неизвестный формат '{image_format}', пропуск.")
                    continue

                full_paths.append(filepath)

                # Превью в UI ComfyUI доступно только для файлов внутри output/ —
                # если путь внешний, subfolder пустой (картинка сохранится на диск).
                try:
                    rel = os.path.relpath(filepath, self.output_dir)
                    subfolder = "" if rel.startswith("..") else os.path.dirname(rel).replace(os.sep, "/")
                except ValueError:
                    subfolder = ""

                ui_images.append({"filename": os.path.basename(filepath), "subfolder": subfolder, "type": "output"})

            except Exception as e:
                print(f"[ImageSave] Ошибка сохранения: {e}")
                full_paths.append("")

        first = next((p for p in full_paths if p), "")
        filename_no_ext = os.path.splitext(os.path.basename(first))[0] if first else ""

        return {
            "ui": {"images": ui_images},
            "result": (images, first, filename_no_ext),
        }


NODE_CLASS_MAPPINGS = {"SimpleImageSave": SimpleImageSave}
NODE_DISPLAY_NAME_MAPPINGS = {"SimpleImageSave": "💾 Simple Image Save"}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
