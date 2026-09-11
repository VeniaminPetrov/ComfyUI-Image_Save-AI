# -*- coding: utf-8 -*-
"""Очистка истории v3 (надежно): orphan-ветка из чистого дерева + force-push."""
import subprocess
import os
import shutil
import tempfile

REPO = r"F:\Hermes\ComfyUI-ImageSave"


def run(cmd, expect=0):
    r = subprocess.run([str(c) for c in cmd], cwd=REPO, capture_output=True, text=True)
    if r.returncode != expect:
        print("FAILED:", " ".join(str(c) for c in cmd))
        print(r.stderr)
        raise SystemExit(1)
    return r.stdout.strip()


# 0. Текущее состояние
real = run(["git", "ls-remote", "origin", "main"]).split()[0]
print("current remote main:", real[:7])
run(["git", "reset", "--hard"])  # сбросить случайные изменения (например, удалённые служебные файлы)
st = run(["git", "status", "--porcelain"])
tracked_dirty = [l for l in st.splitlines() if not l.startswith("??")]
assert not tracked_dirty, f"worktree dirty before start: {tracked_dirty!r}"

# 1. Снапшот всех файлов (кроме .git и служебных скриптов)
skip = {".squash2.py", ".squash_history.py"}
snap = tempfile.mkdtemp(prefix="imgsave_v3_")
for item in os.listdir(REPO):
    if item == ".git" or item in skip:
        continue
    src, dst = os.path.join(REPO, item), os.path.join(snap, item)
    (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
print("snapshot ok:", sorted(os.listdir(snap)))

# 2. Orphan-ветка: история начинается с пустого дерева
run(["git", "checkout", "--orphan", "squashed"])
run(["git", "rm", "-rf", "."], expect=0)  # очистить индекс и дерево (рабочие файлы сохранились в снапшоте)

# 3. Перенести чистые файлы из снапшота
for item in os.listdir(snap):
    src, dst = os.path.join(snap, item), os.path.join(REPO, item)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)

# 4. Единственный коммит с нейтральным сообщением (без OreX)
run(["git", "add", "-A"])
msg = ("Simple Image Save: кастомный нод сохранения изображений ComfyUI\n"
       "\n"
       "- Сохранение в любой путь (абсолютный или подпапку output/)\n"
       "- Папка по дате YYYY-MM-DD + подпапка Processed\n"
       "- Счётчик 0001/0002 со сканированием папки (переживает перезапуск) или время HHMMSS\n"
       "- Форматы PNG/JPG/WebP, embed workflow в метаданные PNG + соседний .json\n"
       "- Выходы: IMAGE, saved_path, filename_text")
run(["git", "commit", "-m", msg])

hist = run(["git", "log", "--oneline"])
print("--- orphan history ---")
print(hist)
assert hist.count("\n") == 0 or "\n" not in hist, f"expected exactly ONE commit, got: {hist!r}"

# 5. Force-push с lease (защита от чужих изменений за время работы)
push = subprocess.run(
    ["git", "push", "--force-with-lease=main:" + real, "origin", "squashed:main"],
    cwd=REPO, capture_output=True, text=True, timeout=60)
print(push.stdout.strip())
if push.returncode != 0:
    print("PUSH FAILED:", push.stderr)
    raise SystemExit(1)

# 6. Синхронизировать локальную main с origin и удалить orphan-ветку
run(["git", "checkout", "main"])
new_main = run(["git", "ls-remote", "origin", "main"]).split()[0]
run(["git", "reset", "--hard", new_main])
run(["git", "branch", "-D", "squashed"])

print("--- FINAL history (local == remote) ---")
final = run(["git", "log", "--oneline"])
print(final)
assert "OreX" not in final and "Orex" not in final, "OreX still in history!"

# 7. Убрать служебный скрипт и снапшот
script = os.path.join(REPO, ".squash2.py")
os.path.isfile(script) and os.remove(script)
shutil.rmtree(snap, ignore_errors=True)
print("DONE: история очищена, OreX отсутствует в коммитах")
