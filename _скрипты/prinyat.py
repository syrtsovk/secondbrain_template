#!/usr/bin/env python3
"""Принять существующую папку в базу: шаблон кладётся рядом с файлами человека, его файлы остаются на месте.

Запускается из свежей копии шаблона во временной папке (базы ещё нет):
  python3 <шаблон>/_скрипты/prinyat.py <папка>          аудит: только читает, ничего не меняет
  python3 <шаблон>/_скрипты/prinyat.py <папка> --da     после «ок»: резервная копия → шаблон рядом

Что делает --da:
  1. Полная копия папки в ~/Бэкап второго мозга/<папка>-до-приёма-<время>/ и сверка числа файлов.
  2. Отдельные файлы в корне человека (не папки) → в папку «Мои файлы/» (ссылки Obsidian по имени не ломаются).
  3. Файлы шаблона — туда, где их нет. Существующее не перезаписывается:
     AGENTS.md человека остаётся, шаблонный кладётся рядом как AGENTS.шаблон.md (сливает агент);
     .gitignore — дописываются недостающие строки; README.md шаблона не нужен — не кладётся.
  4. Нет git → git init. Чужое облако (remote) человека не трогается.
Коды: 0 — готово · 2 — конфликт имён папок с шаблоном, стоп · 3 — не та папка.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # Windows: консоль не utf-8
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TEMPLATE = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("BACKUP_HOME") or Path.home())  # BACKUP_HOME — только для проверки на подставной папке
LOOSE_DIR = "Мои файлы"
PRIVATE = {"_личное", "_private"}  # уже убранное человеком: не «свои папки», в облако не идёт, не проверяем
TEMPLATE_SKIP = {".git", "README.md"}  # README шаблона — про сам шаблон, человеку в базе не нужен
BIG = 50_000_000  # GitHub не примет файл больше 100 МБ, предупреждаем заранее
SECRET_NAME = re.compile(r"secret|credential|token|password|пароль|^\.env|\.pem$|\.key$|id_rsa", re.I)
PD = [
    (re.compile(r"\b\d{2}\s?\d{2}\s?\d{6}\b"), "похоже на паспорт"),
    (re.compile(r"\b\d{3}-\d{3}-\d{3}[ -]\d{2}\b"), "похоже на СНИЛС"),
    (re.compile(r"(?i)(?:пароль|password)\s*[:=]\s*\S{4,}"), "похоже на пароль"),
    (re.compile(r"\b(?:sk|ghp|gho|xox[bp])[-_][A-Za-z0-9_-]{16,}"), "похоже на ключ"),
]


def template_entries() -> list[str]:
    return sorted(p.name for p in TEMPLATE.iterdir() if p.name not in TEMPLATE_SKIP)


def files_in(folder: Path) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        out += [Path(dirpath) / f for f in filenames]
    return out


def audit(target: Path) -> dict:
    top = sorted(p for p in target.iterdir() if p.name != ".git")
    dirs = [p for p in top if p.is_dir() and not p.name.startswith(".") and p.name not in PRIVATE]
    loose = [p for p in top if p.is_file() and not p.name.startswith(".") and p.name not in {"AGENTS.md", "CLAUDE.md", "README.md"}]
    names = set(template_entries())
    clash = [p.name for p in top if p.is_dir() and p.name in names and not p.name.startswith(".")]
    all_files = [f for f in files_in(target) if f.relative_to(target).parts[0] not in PRIVATE]
    big, secret_names, pd_hits = [], [], []
    for f in all_files:
        try:
            if f.stat().st_size > BIG:
                big.append(f)
        except OSError:
            continue
        if SECRET_NAME.search(f.name):
            secret_names.append(f)
        if f.suffix in (".md", ".txt") and f.stat().st_size < 2_000_000:
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for rx, what in PD:
                if rx.search(text):
                    pd_hits.append((f, what))
                    break
    git = (target / ".git").exists()
    remote = subprocess.run(["git", "remote", "-v"], cwd=target, capture_output=True, text=True).stdout.strip() if git else ""
    return {"dirs": dirs, "loose": loose, "clash": clash, "files": len(all_files),
            "md": sum(f.suffix == ".md" for f in all_files), "big": big, "secret_names": secret_names, "pd": pd_hits,
            "obsidian": (target / ".obsidian").is_dir(), "git": git, "remote": remote,
            "own_rules": [n for n in ("AGENTS.md", "CLAUDE.md", "README.md", ".gitignore") if (target / n).exists()]}


def show(a: dict, target: Path) -> None:
    r = lambda p: str(Path(p).relative_to(target))
    print(f"АУДИТ (ничего не менял): {target}")
    print(f"  файлов: {a['files']}, из них заметок .md: {a['md']} · Obsidian: {'да' if a['obsidian'] else 'нет'} · "
          f"git: {'да' if a['git'] else 'нет'}{' (облако: ' + a['remote'].split()[1] + ')' if a['remote'] else ''}")
    print("  твои папки — останутся на месте, ИИ будет их читать, но не переписывать:")
    for d in a["dirs"]:
        print(f"    {d.name}/ — {sum(1 for _ in files_in(d))} файлов")
    if a["loose"]:
        print(f"  файлы прямо в корне — переедут в «{LOOSE_DIR}/»: " + ", ".join(p.name for p in a["loose"][:15]) +
              (" …" if len(a["loose"]) > 15 else ""))
    if a["own_rules"]:
        print("  уже есть свои файлы правил/настроек — не перезапишу, сольём вместе: " + ", ".join(a["own_rules"]))
    if a["clash"]:
        print("  КОНФЛИКТ: папки с такими же именами, как в шаблоне: " + ", ".join(a["clash"]) +
              " — переименуй их (например «<имя> (моё)»), потом повтори")
    if a["secret_names"] or a["pd"]:
        print("  ЛИЧНОЕ/ДОСТУПЫ — до облака убрать в _личное/ (в облако не уходит):")
        for f in a["secret_names"][:10]:
            print(f"    {r(f)} — по имени похоже на доступы")
        for f, what in a["pd"][:10]:
            print(f"    {r(f)} — {what}")
    if a["big"]:
        print("  БОЛЬШИЕ файлы (>50 МБ, облако их не примет) — в _личное/ или вне базы: " + ", ".join(r(f) for f in a["big"][:10]))


def backup(target: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = HOME / "Бэкап второго мозга" / f"{target.name}-до-приёма-{stamp}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(target, dest, symlinks=True)
    before, after = len(files_in(target)), len(files_in(dest))
    if before != after:
        sys.exit(f"СТОП: в копии {after} файлов, в папке {before}. Ничего не менял, копия: {dest}")
    print(f"Резервная копия: {dest} — {after} файлов, совпадает ✓")
    return dest


def apply(target: Path, a: dict) -> None:
    backup(target)
    if a["loose"]:
        (target / LOOSE_DIR).mkdir(exist_ok=True)
        for p in a["loose"]:
            shutil.move(str(p), str(target / LOOSE_DIR / p.name))
        print(f"Файлы из корня → «{LOOSE_DIR}/»: {len(a['loose'])}")
    added, side = 0, []
    for name in template_entries():
        src, dst = TEMPLATE / name, target / name
        if name == ".gitignore" and dst.exists():
            have = set(dst.read_text(encoding="utf-8").splitlines())
            extra = [l for l in src.read_text(encoding="utf-8").splitlines() if l and l not in have]
            if extra:
                with dst.open("a", encoding="utf-8") as fh:
                    fh.write("\n# — из шаблона второго мозга —\n" + "\n".join(extra) + "\n")
            continue
        if dst.exists() and src.is_dir() and name.startswith("."):
            for f in files_in(src):  # .claude/.codex человека: добавить недостающее, своё не трогать
                d = dst / f.relative_to(src)
                if not d.exists():
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, d)
                    added += 1
                elif d.read_bytes() != f.read_bytes():
                    side_path = d.with_name(f"{d.stem}.шаблон{d.suffix}")
                    shutil.copy2(f, side_path)
                    side.append(f"{d.relative_to(target)} (шаблонный рядом: {side_path.name})")
            continue
        if dst.exists():
            if src.is_file():
                shutil.copy2(src, target / f"{dst.stem}.шаблон{dst.suffix}")
                side.append(f"{name} (шаблонный рядом: {dst.stem}.шаблон{dst.suffix})")
            continue
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)
        added += 1
    print(f"Шаблон добавлен рядом: {added} элементов, твои файлы не тронуты.")
    if side:
        print("Есть свои версии — слить вместе (шаг 5 инструкции): " + "; ".join(side))
    if not a["git"]:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target)
        print("История изменений (git) включена.")
    ver = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=TEMPLATE, capture_output=True, text=True).stdout.strip()
    print(f"Версия шаблона: {ver or 'неизвестна'} — запиши в УСТАНОВКА.md → template_version")
    print("Свои папки для строки в AGENTS.md: " + ", ".join(f"`{d.name}/`" for d in a["dirs"]) +
          (f", `{LOOSE_DIR}/`" if a["loose"] else ""))


def main() -> int:
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not args:
        print(__doc__)
        return 3
    target = Path(args[0]).expanduser().resolve()
    if not target.is_dir() or target == TEMPLATE or TEMPLATE in target.parents:
        print(f"Не та папка: {target}")
        return 3
    if (target / "УСТАНОВКА.md").exists() and (target / "_скрипты").exists():
        print("Здесь уже стоит второй мозг — принимать нечего.")
        return 3
    a = audit(target)
    show(a, target)
    if a["clash"]:
        return 2
    if "--da" in sys.argv:
        print()
        apply(target, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
