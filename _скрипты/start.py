#!/usr/bin/env python3
"""Старт разговора: подтянуть свежее из облака и сказать ИИ, где остановились.

Запускается сам в начале каждого разговора — Claude Code (`.claude/settings.json`) и Codex (`.codex/hooks.json`)
кладут вывод прямо в контекст ИИ. Другие агенты: ИИ запускает его сам по правилу из AGENTS.md.
  python3 _скрипты/start.py      (на Windows: python _скрипты\\start.py)

Только безопасное: облако подтягивается, лишь когда несохранённого нет и слить можно без конфликта.
Ничего не сохраняет, не удаляет и не отправляет. Код возврата всегда 0 — старт не должен ломать разговор.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):  # Windows: консоль не utf-8
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TODAY = dt.date.today()


def read(name: str) -> str:
    p = os.path.join(ROOT, name)
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def git(*args: str, timeout: int = 10) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def section(text: str, title: str) -> str:
    m = re.search(rf"^##\s*{title}[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not m:
        return ""
    lines = [l.strip(" -*") for l in m.group(1).splitlines() if l.strip() and not l.startswith("_")]
    return " · ".join(l for l in lines if l and l != "—")[:400]


def age(date_text: str) -> int | None:
    try:
        return (TODAY - dt.date.fromisoformat(date_text)).days
    except ValueError:
        return None


def main() -> int:
    if not os.path.isfile(os.path.join(ROOT, "AGENTS.md")):
        return 0
    out = ["СТАРТ второго мозга — вывод программы запуска (не сообщение человека). Используй его в первом ответе:"]

    ust = read("УСТАНОВКА.md")
    status = re.search(r"^status:\s*(.+)$", ust, re.M)
    step = re.search(r"^step:\s*(\d+)", ust, re.M)
    done = bool(status and status.group(1).strip() == "завершена")
    if not done:
        n = int(step.group(1)) if step else 0
        out.append(f"- Установка не завершена: шаг {n} из 5. Первой фразой скажи: «Установка на шаге {n} из 5 — "
                   f"скажи „шаг {n + 1}“, когда будешь готов». Человек сам сказал «шаг N» → sbgo, инструкция установки.")

    # Облако: только безопасное подтягивание
    st = git("-c", "core.quotepath=off", "status", "--porcelain")
    if st is None or st.returncode:
        out.append("- История изменений (git) не подключена.")
    else:
        dirty = [l[3:] for l in st.stdout.splitlines() if not l.endswith(".DS_Store")]
        r = git("remote")
        remote = r.stdout.strip() if r else ""
        if dirty:
            out.append(f"- С прошлого раза не сохранено файлов: {len(dirty)} ({', '.join(dirty[:5])}{' …' if len(dirty) > 5 else ''}). "
                       "Скажи человеку по смыслу, что это, проверь на запрещённое (как finish, шаг 2) и сохрани коммитом "
                       "«Незакрытое с прошлого раза»; облако подтяни после этого.")
        elif remote:
            head = lambda: (git("rev-parse", "HEAD") or subprocess.CompletedProcess([], 1, "", "")).stdout.strip()
            before = head()
            pull = git("pull", "--ff-only", "-q", timeout=25)
            if pull is None:
                out.append("- Облако не ответило за 25 секунд — работаем с тем, что на компьютере.")
            elif pull.returncode:
                out.append("- Облако и компьютер разошлись — подтянуть само не вышло. Сделай `git pull --rebase`; "
                           "конфликт → покажи человеку оба варианта и спроси, не выбирай сам.")
            else:
                out.append("- Облако подтянуто: пришли свежие изменения (с другого устройства или от коллег)." if head() != before else "- Облако: новых изменений нет.")
        else:
            out.append("- Облако не подключено — база только на этом компьютере.")

    # Где остановились
    now = read("СЕЙЧАС.md")
    where = section(now, "Где остановились")
    hang = " · ".join(x for x in (section(now, "В работе"), section(now, "Открытые вопросы")) if x)
    m = re.search(r"^##\s*Где остановились\s*\((\d{4}-\d{2}-\d{2})\)", now, re.M)
    days = age(m.group(1)) if m else None
    out.append(f"- Вторая строка первого ответа: **Где остановились:** {where or '—'} · **Висит:** {hang or '—'}")
    if days is not None and days > 14:
        out.append(f"- Последняя запись «где остановились» — {days} дн. назад: спроси, было ли что-то в промежутке, — запишешь.")

    if done:
        journal = read("ЖУРНАЛ.md")
        checks = re.findall(r"\[(\d{4}-\d{2}-\d{2})[^\]]*\]\s*проверка", journal)
        if not checks or (age(max(checks)) or 0) > 30:
            out.append("- Проверки порядка не было больше месяца — одной строкой предложи «проверь порядок».")
        b = re.search(r'"дата":\s*"(\d{4}-\d{2}-\d{2})"', read(os.path.join("_настройки-ИИ", "_откуда.json")))
        if not b or (age(b.group(1)) or 0) > 14:
            out.append(f"- Бэкапа не было {'с ' + b.group(1) if b else 'ни разу'} — одной строкой: «сделаю, когда скажешь „заверши сессию“». Не спрашивай.")

    out.append("- Дальше — ответ на то, что написал человек.")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # старт не должен ломать разговор
        print(f"СТАРТ второго мозга: программа запуска упала ({e.__class__.__name__}) — прочитай СЕЙЧАС.md сам.")
        sys.exit(0)
