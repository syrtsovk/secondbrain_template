#!/usr/bin/env python3
"""Проверка порядка в базе. Только читает, ничего не меняет.

Запуск из любого места:  python3 _скрипты/proverka.py   (на Windows: python _скрипты\\proverka.py)
Печатает три группы: 🔴 красное (чинить сразу), 🟡 жёлтое (за один заход), ℹ️ для сведения.
Код возврата всегда 0 — это отчёт, а не блокировка.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TODAY = dt.date.today()

# Что не проверяем на шапки/оглавление: инструкции людям, заготовки, умения, скрипты, личное.
SKIP_DIRS = {".git", ".obsidian", ".agents", ".claude", "_скрипты", "_шаблоны", "0-Начало", "_личное", "_private", "__pycache__", "node_modules"}
SKIP_FILES = {"README.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"}
SERVICE = {"СЕЙЧАС.md", "ЖУРНАЛ.md", "ОГЛАВЛЕНИЕ.md", "УСТАНОВКА.md", "МЕТОДОЛОГИЯ.md"}
TEMPLATES = {"_шаблон-карточки.md", "карточка.md"}  # шаблоны с заглушками {{…}} — не страницы
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINK = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|[^\]]*)?\]\]")
FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`\n]*`")
PD_PATTERNS = [
    (re.compile(r"\b\d{2}\s?\d{2}\s?\d{6}\b"), "похоже на серию и номер паспорта"),
    (re.compile(r"\b\d{3}-\d{3}-\d{3}[ -]\d{2}\b"), "похоже на СНИЛС"),
    (re.compile(r"\b(?:sk|ghp|gho|xox[bp])[-_][A-Za-z0-9_-]{16,}"), "похоже на ключ доступа"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "похоже на ключ AWS"),
    (re.compile(r"(?i)(?:пароль|password)\s*[:=]\s*\S{4,}"), "похоже на пароль"),
]

red: list[str] = []
yellow: list[str] = []
info: list[str] = []


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT)


def git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=ROOT, capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            return None
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def walk_md() -> list[str]:
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".md"):
                files.append(os.path.join(dirpath, f))
    return files


def read(p: str) -> str:
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def frontmatter(text: str) -> dict[str, str] | None:
    t = text.lstrip("﻿")
    if not t.startswith("---"):
        return None
    end = t.find("\n---", 3)
    if end == -1:
        return None
    fm: dict[str, str] = {}
    for line in t[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    return fm


def main() -> int:
    if not os.path.isfile(os.path.join(ROOT, "AGENTS.md")):
        print(f"Не похоже на базу: нет AGENTS.md в {ROOT}")
        return 0

    all_md = walk_md()
    pages = [p for p in all_md if os.path.basename(p) not in SKIP_FILES and os.path.basename(p) not in TEMPLATES]
    names: dict[str, list[str]] = {}
    for p in all_md:
        names.setdefault(os.path.splitext(os.path.basename(p))[0].lower(), []).append(p)
    # ссылки могут вести и на заготовки/пример — их имена тоже считаем существующими
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if any(part in dirpath.split(os.sep) for part in ("_шаблоны", "0-Начало")):
            for f in filenames:
                if f.endswith(".md"):
                    names.setdefault(os.path.splitext(f)[0].lower(), []).append(os.path.join(dirpath, f))

    toc_text = read(os.path.join(ROOT, "ОГЛАВЛЕНИЕ.md")) if os.path.isfile(os.path.join(ROOT, "ОГЛАВЛЕНИЕ.md")) else ""
    journal_text = read(os.path.join(ROOT, "ЖУРНАЛ.md")) if os.path.isfile(os.path.join(ROOT, "ЖУРНАЛ.md")) else ""

    # 1. Шапки и даты
    for p in pages:
        r = rel(p)
        text = read(p)
        if "{{ДАТА}}" in text or "{{ВРЕМЯ}}" in text:
            red.append(f"{r}: осталась заглушка {{{{ДАТА}}}} — установка не подставила дату")
        fm = frontmatter(text)
        if fm is None:
            red.append(f"{r}: нет шапки `---` в начале файла")
            continue
        for field in ("created", "updated"):
            v = fm.get(field, "")
            if not v:
                red.append(f"{r}: в шапке нет поля `{field}`")
            elif not ISO.match(v):
                red.append(f"{r}: `{field}: {v}` — дата не в формате ГГГГ-ММ-ДД")
        if "author" not in fm:
            yellow.append(f"{r}: в шапке нет `author` (ии / человек / ии+проверено)")
        if r.startswith("Сырьё" + os.sep) and fm.get("author") == "ии":
            yellow.append(f"{r}: сырьё помечено `author: ии` — сырьё пишет не ИИ")

    # 2. Битые ссылки
    for p in pages:
        text = INLINE.sub("", FENCE.sub("", read(p)))
        for m in LINK.finditer(text):
            target = m.group(1).strip()
            key = os.path.basename(target).lower()
            if key.endswith(".md"):
                key = key[:-3]
            if key in names:
                continue
            if os.path.exists(os.path.join(ROOT, target)) or os.path.exists(os.path.join(ROOT, target + ".md")):
                continue
            yellow.append(f"{rel(p)}: битая ссылка [[{target}]] — такой страницы нет")

    # 3–4. Оглавление и журнал
    content_pages = [p for p in pages if os.path.basename(p) not in SERVICE and not rel(p).startswith("Сырьё" + os.sep)
                     and os.path.basename(p) != "_правила.md"]
    recent: set[str] | None = None
    added = git("log", "--since=30 days ago", "--diff-filter=A", "--name-only", "--format=", "--", "*.md")
    untracked = git("ls-files", "--others", "--exclude-standard", "--", "*.md")
    if added is not None:
        recent = {line.strip() for line in (added + (untracked or "")).splitlines() if line.strip()}
    for p in content_pages:
        r = rel(p)
        base = os.path.splitext(os.path.basename(p))[0]
        if base not in toc_text and r not in toc_text:
            yellow.append(f"{r}: нет в ОГЛАВЛЕНИЕ.md — для поиска страницы не существует")
        is_recent = recent is None or r.replace(os.sep, "/") in recent
        if is_recent and base not in journal_text and r not in journal_text:
            yellow.append(f"{r}: нет в ЖУРНАЛ.md — неизвестно, когда и откуда появилась")

    # 5. Сырьё редактировалось
    dirty = git("status", "--porcelain", "--", "Сырьё")
    if dirty:
        for line in dirty.splitlines():
            if line[:2].strip() in ("M", "MM", "AM"):
                red.append(f"{line[3:].strip()}: сырьё изменено после сохранения — оригинал портить нельзя")
    modified = git("log", "--since=30 days ago", "--diff-filter=M", "--name-only", "--format=", "--", "Сырьё/Источники", "Сырьё/Входящее")
    if modified:
        for f in sorted({l.strip() for l in modified.splitlines() if l.strip()}):
            yellow.append(f"{f}: сырьё правилось за последний месяц — проверь, что оригинал цел")

    # 6. Давно не сохранялись
    last = git("log", "-1", "--format=%cs")
    if last is None:
        info.append("Git не подключён — история изменений не ведётся, откатиться будет не к чему")
    elif last.strip():
        d = dt.date.fromisoformat(last.strip())
        days = (TODAY - d).days
        if days > 7:
            yellow.append(f"Последнее сохранение {days} дн. назад ({d}) — скажи «заверши сессию»")
        remote = git("remote")
        if remote is not None and not remote.strip():
            info.append("Облако не подключено — база живёт только на этом компьютере (шаг 5 установки)")
        else:
            ahead = git("rev-list", "--count", "@{u}..HEAD")
            if ahead and ahead.strip().isdigit() and int(ahead.strip()) > 0:
                yellow.append(f"{ahead.strip()} сохранений не отправлено в облако")

    # 7. Давность проверки
    checks = re.findall(r"\[(\d{4}-\d{2}-\d{2})[^\]]*\]\s*проверка", journal_text)
    if checks:
        d = dt.date.fromisoformat(max(checks))
        if (TODAY - d).days > 30:
            yellow.append(f"Последняя проверка порядка была {d} — больше месяца назад")
    else:
        info.append("Это первая проверка порядка — после неё ИИ запишет её в журнал")

    # 8. Персональные данные и ключи
    for p in pages + [os.path.join(ROOT, f) for f in SKIP_FILES if os.path.isfile(os.path.join(ROOT, f))]:
        text = read(p)
        for rx, why in PD_PATTERNS:
            if rx.search(text):
                red.append(f"{rel(p)}: {why} — персональным данным и ключам здесь не место (0-Начало/4)")
                break

    # 9. Установка
    ust = os.path.join(ROOT, "УСТАНОВКА.md")
    if os.path.isfile(ust):
        fm = frontmatter(read(ust)) or {}
        if fm.get("status", "") != "завершена":
            info.append(f"Установка не завершена (шаг {fm.get('step', '?')}) — скажи «продолжим установку»")

    # 10. Дубли карточек
    seen: dict[str, list[str]] = {}
    for p in content_pages:
        key = re.sub(r"[\s\-_«»\"']", "", os.path.splitext(os.path.basename(p))[0].lower())
        seen.setdefault(key, []).append(rel(p))
    for key, lst in seen.items():
        if len(lst) > 1:
            yellow.append("Похоже на дубль: " + " · ".join(lst))

    # Отчёт
    print(f"Проверка порядка — {TODAY}, страниц проверено: {len(pages)}\n")
    for title, items in (("🔴 Красное — чинить сразу", red), ("🟡 Жёлтое — за один заход", yellow), ("ℹ️ Для сведения", info)):
        print(f"{title}: {len(items)}")
        for it in items:
            print(f"  - {it}")
        print()
    if not red and not yellow:
        print("Порядок. Ничего чинить не нужно.")
    print(f"Итого: {len(red)} красных, {len(yellow)} жёлтых, {len(info)} заметок.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
