#!/usr/bin/env python3
"""Бэкап настроек ИИ в базу — чтобы на новом компьютере всё вернулось одной фразой.

Сама база и так уходит в облако. Этот скрипт добавляет к ней то, что живёт ВНЕ папки базы,
в системных папках агента: личные правила, свои умения и команды, память ИИ о тебе,
список подключённых сервисов. Кладёт всё в `_настройки-ИИ/` внутри базы — дальше оно уходит
в облако вместе с базой.

Запуск из любого места:
  python3 _скрипты/backup.py                  собрать копию (на Windows: python _скрипты\\backup.py)
  python3 _скрипты/backup.py --arhiv          + архив всей базы сейчас (сам он делается раз в 30 дней)
  python3 _скрипты/backup.py --eto-ne-pdn     человек проверил находку: это не личные данные — не останавливаться
  python3 _скрипты/backup.py --vosstanovit    показать, что вернётся на место (ничего не пишет)
  python3 _скрипты/backup.py --vosstanovit --da   вернуть на место

  python3 _скрипты/backup.py --oblako-privatnoe  человек подтвердил: облако закрыто (когда проверить само не вышло)
  python3 _скрипты/backup.py --proverit-oblako  перед отправкой в облако: можно ли туда копию настроек (коды 0 / 4 / 6)

Коды: 0 — готово · 1 — нашлось похожее на паспорт/ключ, стоп (печатает файл и строку, без значения) ·
4 — облако открыто всем (публичный репозиторий), настройки не кладём · 5 — восстанавливать нечего ·
6 — не удалось проверить, закрыто ли облако, настройки не кладём (подтверждение — флаг выше, запоминается).
Значения ключей скрипт не печатает и в копию не кладёт: заменяет заглушкой.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # Windows: консоль не utf-8
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "_настройки-ИИ"
HOME = Path(os.environ.get("BACKUP_HOME") or Path.home())  # BACKUP_HOME — только для проверки на подставной папке
TODAY = dt.date.today().isoformat()
STUB = "<УБРАНО: взять из менеджера паролей>"
SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", ".DS_Store", ".trash", ".system", "cache"}
MAX_BYTES = 5_000_000
# файлы с доступами по имени не берём вовсе (как и .gitignore базы): secret_*, *credential*, *token*, .env
SECRET_NAME = re.compile(r"secret|credential|token|^\.env", re.I)

# что копируем: (откуда, куда внутри _настройки-ИИ)
CLAUDE, CODEX = HOME / ".claude", HOME / ".codex"
SOURCES = [
    (CLAUDE / "CLAUDE.md", "claude/CLAUDE.md"),
    (CLAUDE / "settings.json", "claude/settings.json"),
    (CLAUDE / "skills", "claude/skills"),
    (CLAUDE / "commands", "claude/commands"),
    (CLAUDE / "agents", "claude/agents"),
    (CLAUDE / "hooks", "claude/hooks"),
    (CODEX / "AGENTS.md", "codex/AGENTS.md"),
    (CODEX / "skills", "codex/skills"),
    (CODEX / "prompts", "codex/prompts"),
]

SECRET_KEY = re.compile(r"key|token|secret|passw|auth|bearer|cookie|credential", re.I)
LONG_MIXED = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9_\-.]{24,}$")
QUOTED = re.compile(r"""((?:key|token|secret|passw\w*|api_?key)\w*["']?\s*[:=]\s*)(["'])([^"'\s]{8,})\2""", re.I)
HARD = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w+|xox[bap]-[\w-]+|AIza[0-9A-Za-z_-]{20,}"
    r"|AKIA[0-9A-Z]{12,}|\b\d{8,10}:[A-Za-z0-9_-]{35}\b|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\S*"
    r"|(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"
)
PD = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"), "закрытый ключ"),
    (re.compile(r"\b\d{2} \d{2} \d{6}\b|(?i:паспорт)\D{0,30}\d{2}\s?\d{2}\s?\d{6}\b"), "похоже на серию и номер паспорта"),
    (re.compile(r"\b\d{3}-\d{3}-\d{3}[ -]\d{2}\b"), "похоже на СНИЛС"),
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "похоже на номер карты"),
    (re.compile(r"(?i)(?:пароль|password)\s*[:=]\s*(?!<)\S{4,}"), "похоже на пароль"),
]


def slug(path: str) -> str:
    """Как Claude Code называет папку проекта: всё, кроме латиницы и цифр, — дефис."""
    return re.sub(r"[^A-Za-z0-9-]", "-", path)


def scrub_text(text: str) -> str:
    text = QUOTED.sub(lambda m: m.group(0) if m.group(3).startswith("<") else f"{m.group(1)}{m.group(2)}{STUB}{m.group(2)}", text)
    return HARD.sub(STUB, text)


def copy_tree(src: Path, dst: Path, skipped: list[str]) -> int:
    n = 0
    for item in sorted(src.iterdir()) if src.is_dir() else [src]:
        if item.name in SKIP or item.name.endswith((".pyc", ".log")):
            continue
        if item.is_file() and SECRET_NAME.search(item.name):
            skipped.append(f"{item.name} — по имени похоже на доступы, не беру (храни в менеджере паролей)")
            continue
        target = dst / item.name if src.is_dir() else dst
        try:
            real = item.resolve()  # ссылки (symlink) — копируем то, на что они указывают
            if real == ROOT or ROOT in real.parents:
                continue  # умения самой базы уже в базе
            if real.is_dir():
                n += copy_tree(real, target, skipped)
            elif real.is_file():
                if real.stat().st_size > MAX_BYTES:
                    skipped.append(f"{item} — больше 5 МБ")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    target.write_text(scrub_text(real.read_text(encoding="utf-8")), encoding="utf-8")
                except UnicodeDecodeError:
                    shutil.copy2(real, target)
                n += 1
        except OSError as e:
            skipped.append(f"{item} — не прочитался ({e.__class__.__name__})")
    return n


def clean_server(s: dict) -> dict:
    s = dict(s)
    for k in ("env", "headers", "http_headers"):
        if isinstance(s.get(k), dict):
            s[k] = {name: STUB for name in s[k]}
    if isinstance(s.get("url"), str) and "?" in s["url"]:
        s["url"] = s["url"].split("?", 1)[0] + "?" + STUB
    if isinstance(s.get("args"), list):
        out, hide = [], False
        for a in map(str, s["args"]):
            name = a.split("=", 1)[0]
            if hide or LONG_MIXED.match(a):
                a = STUB
            elif "=" in a and SECRET_KEY.search(name):
                a = f"{name}={STUB}"
            hide = a.startswith("-") and "=" not in a and bool(SECRET_KEY.search(a))
            out.append(a)
        s["args"] = out
    return s


def mcp_claude() -> dict:
    p = HOME / ".claude.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    out = {"для_всех_проектов": {n: clean_server(s) for n, s in (d.get("mcpServers") or {}).items()}}
    for path, proj in (d.get("projects") or {}).items():
        if proj.get("mcpServers"):
            out[path] = {n: clean_server(s) for n, s in proj["mcpServers"].items()}
    return out


def mcp_codex() -> str:
    p = CODEX / "config.toml"
    if not p.exists():
        return ""
    lines, table = [], ""
    for line in p.read_text(encoding="utf-8").splitlines():
        head = re.match(r"\s*\[+([^\]]+)\]+", line)
        if head:
            table = head.group(1)
        kv = re.match(r"(\s*)([\w\"'.-]+)(\s*=\s*)(.+)", line)
        if kv and not head:
            secret_table = re.search(r"(^|\.)(env|headers|http_headers)$", table)
            if secret_table or SECRET_KEY.search(kv.group(2)) or LONG_MIXED.match(kv.group(4).strip().strip("\"'")):
                line = f'{kv.group(1)}{kv.group(2)}{kv.group(3)}"{STUB}"'
        lines.append(line)
    return "\n".join(lines) + "\n"


def remote_url() -> str:
    r = subprocess.run(["git", "remote"], cwd=ROOT, capture_output=True, text=True)
    names = r.stdout.split()
    if not names:
        return ""
    name = "origin" if "origin" in names else names[0]
    return subprocess.run(["git", "remote", "get-url", name], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def repo_is_public(url: str) -> bool | None:
    """True — открыт всем, False — закрыт, None — не узнать. Сначала gh, потом GitHub без входа."""
    try:
        r = subprocess.run(["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"],
                           cwd=ROOT, capture_output=True, text=True, timeout=20)
        v = {"PUBLIC": True, "PRIVATE": False, "INTERNAL": False}.get(r.stdout.strip().upper())
        if v is not None:
            return v
    except (OSError, subprocess.TimeoutExpired):
        pass
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    if not m:
        return None  # не GitHub — проверить нечем
    try:  # без входа GitHub отдаёт только открытые репозитории; закрытый для чужих — «нет такого»
        urllib.request.urlopen(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}", timeout=10)
        return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def scan(folder: Path) -> list[str]:
    found = []
    for f in ([folder] if folder.is_file() else folder.rglob("*")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for rx, what in PD:
                if rx.search(line):
                    found.append(f"  {f.relative_to(ROOT)}:{i} — {what}")
    return found


def cloud_check(privatnoe: bool) -> tuple[int, str, str]:
    """0 — можно, 4 — облако открыто всем, 6 — не узнать и не подтверждено. Возвращает (код, облако, подтверждение)."""
    url = remote_url()
    confirmed = ""
    try:
        confirmed = json.loads((DEST / "_откуда.json").read_text(encoding="utf-8")).get("облако_закрыто_подтвердил", "")
    except (OSError, ValueError):
        pass
    public = repo_is_public(url) if url else False
    if public:
        return 4, url, confirmed
    if public is None and not privatnoe and confirmed != url:
        return 6, url, confirmed
    return 0, url, (url if privatnoe else confirmed)


def backup(arhiv: bool, ne_pdn: bool, privatnoe: bool) -> int:
    code, url, confirmed = cloud_check(privatnoe)
    public = code == 4
    if public:
        print("Облако базы открыто всем (публичный репозиторий). Настройки и память ИИ туда не кладу.\n"
              "Сделай репозиторий приватным на github.com (Settings → Danger Zone → Change visibility) и повтори.")
        return 4
    if code == 6:
        print("Не смог проверить, закрыто ли облако базы (нет программы gh, нет сети или это не GitHub). "
              "Настройки и память ИИ пока не кладу.\nСпроси человека: облако закрыто (Private)? Да → "
              "`backup.py --oblako-privatnoe` — запомню и больше не спрошу для этого облака.")
        return 6
    if DEST.exists():
        shutil.rmtree(DEST)  # собираем заново: удалённое у тебя пропадёт и из копии
    DEST.mkdir()
    skipped, counts = [], {}
    for src, rel in SOURCES:
        if src.exists():
            counts[rel] = copy_tree(src, DEST / rel, skipped)

    # память ИИ по проектам (Claude Code): ~/.claude/projects/<папка>/memory
    paths = {}
    if (CLAUDE / "projects").is_dir():
        for mem in sorted((CLAUDE / "projects").glob("*/memory")):
            files = [f for f in mem.resolve().glob("*.md")] if mem.resolve().is_dir() else []
            if not files:
                continue
            name = mem.parent.name
            n = copy_tree(mem.resolve(), DEST / "claude/memory" / name, skipped)
            counts["claude/memory"] = counts.get("claude/memory", 0) + n
            paths[name] = "ЭТА_БАЗА" if name == slug(str(ROOT)) else name
    mcp = mcp_claude()
    if mcp:
        (DEST / "claude").mkdir(exist_ok=True)
        (DEST / "claude/подключения.json").write_text(json.dumps(mcp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    codex = mcp_codex()
    if codex:
        (DEST / "codex").mkdir(exist_ok=True)
        (DEST / "codex/подключения.toml").write_text(codex, encoding="utf-8")

    meta = {"дата": TODAY, "дом": str(HOME), "база": str(ROOT), "память": paths}
    if confirmed:
        meta["облако_закрыто_подтвердил"] = confirmed
    (DEST / "_откуда.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    keys = sorted({k for servers in mcp.values() for s in servers.values() for k in (s.get("env") or s.get("headers") or {})})
    keys += sorted(set(re.findall(r'^\s*([\w-]+)\s*=\s*"' + re.escape(STUB), codex, re.M)))
    write_opis(counts, mcp, keys, skipped)

    # личные данные ищем там, где ИИ пишет о человеке; в коде умений ключи уже заменены заглушкой
    found = [x for part in ("claude/memory", "claude/CLAUDE.md", "codex/AGENTS.md") for x in scan(DEST / part)]
    if found and not ne_pdn:
        print("СТОП: в копии нашлось похожее на личные данные или ключ. В облако не отправляю.")
        print("\n".join(found[:20]))
        print("Реши: убрать это из оригинала (в менеджер паролей или папку _личное) — или, если это не ПДн "
              "(номер заказа, ID), так и скажи, и копию можно отправить.")
        shutil.rmtree(DEST)  # копию с находкой не оставляем: иначе её унесёт следующее «заверши сессию»
        subprocess.run(["git", "checkout", "HEAD", "--", DEST.name], cwd=ROOT, capture_output=True)
        return 1
    print(f"Готово: копия настроек ИИ — {sum(counts.values())} файлов, дата {TODAY}.")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    if skipped:
        print("Не взято:\n  " + "\n  ".join(skipped[:10]))
    zips = own_zips()
    last = dt.date.fromisoformat(zips[-1].stem[-10:]) if zips else None
    if arhiv or not last or (dt.date.today() - last).days > 30:
        make_arhiv()
    return 0


def write_opis(counts: dict, mcp: dict, keys: list[str], skipped: list[str]) -> None:
    rows = "\n".join(f"| `{k}` | {v} |" for k, v in counts.items()) or "| — | 0 |"
    servers = sorted({n for s in mcp.values() for n in s})
    text = f"""---
title: Опись бэкапа настроек ИИ
type: служебное
created: {TODAY}
updated: {TODAY}
tags: [служебное, бэкап]
author: ии
---
# Опись бэкапа — {TODAY}

Эта папка — копия того, что живёт вне базы, в системных папках агента. Собирает `_скрипты/backup.py`,
возвращает на место умение «восстанови меня». Руками не править: при следующем бэкапе перезапишется.

| Что | Файлов |
|---|---|
{rows}

**Подключённые сервисы (MCP):** {", ".join(servers) or "нет"}.
**Ключи, которые на новом компьютере вводятся заново** (значений здесь нет): {", ".join(keys) or "нет"}.

## Чего здесь нет и не будет

- Ключей и паролей — вместо них заглушка. Храни их в менеджере паролей.
- Папки `_личное/` — она в облако не уходит. Её копия — архив на флешке (`backup.py --arhiv`).
- Истории чатов, входа в аккаунты, установленных программ — ставятся заново по `0-Начало/1-что-поставить.md`.
{("- Не взято: " + "; ".join(skipped[:10])) if skipped else ""}
"""
    (DEST / "ОПИСЬ.md").write_text(text, encoding="utf-8")


def own_zips() -> list[Path]:
    """Только наши архивы: «<имя базы>-ГГГГ-ММ-ДД.zip». Чужие файлы в папке не трогаем и не читаем."""
    rx = re.compile(re.escape(ROOT.name) + r"-\d{4}-\d{2}-\d{2}\.zip")
    folder = HOME / "Бэкап второго мозга"
    return sorted(f for f in folder.glob("*.zip") if rx.fullmatch(f.name)) if folder.is_dir() else []


def make_arhiv() -> None:
    folder = HOME / "Бэкап второго мозга"
    folder.mkdir(exist_ok=True)
    out = folder / f"{ROOT.name}-{TODAY}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ROOT.rglob("*"):
            if f.is_file() and ".git" not in f.relative_to(ROOT).parts:
                z.write(f, f.relative_to(ROOT))
    old = own_zips()[:-3]  # храним три последних своих
    for f in old:
        f.unlink()
    print(f"Архив всей базы (с папкой _личное): {out} — {out.stat().st_size // 1024} КБ. Скопируй на флешку или диск.")


def restore(apply: bool) -> int:
    meta_file = DEST / "_откуда.json"
    if not meta_file.exists():
        print("В базе нет копии настроек ИИ — восстанавливать нечего. Базу саму по себе можно продолжать как есть.")
        return 5
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    old_home = meta.get("дом", "")
    plan = [(DEST / rel, src) for src, rel in SOURCES if (DEST / rel).exists()]
    for name, kind in (meta.get("память") or {}).items():
        new = slug(str(ROOT)) if kind == "ЭТА_БАЗА" else name.replace(slug(old_home), slug(str(HOME)), 1)
        plan.append((DEST / "claude/memory" / name, CLAUDE / "projects" / new / "memory"))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    keep = HOME / f".до-восстановления-{stamp}"
    print(("ВОССТАНАВЛИВАЮ" if apply else "ПОКАЖУ, ЧТО ВЕРНЁТСЯ (ничего не пишу; чтобы вернуть — добавь --da)") + f"\n  копия от {meta.get('дата')}")
    moved = 0
    for src, dst in plan:
        files = [src] if src.is_file() else [f for f in src.rglob("*") if f.is_file()]
        for f in files:
            target = dst if src.is_file() else dst / f.relative_to(src)
            if target.exists() and target.read_bytes() == f.read_bytes():
                continue
            moved += 1
            if apply:
                if target.exists() or target.is_symlink():
                    (keep / target.relative_to(HOME)).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), keep / target.relative_to(HOME))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
        print(f"  {src.relative_to(ROOT)} → {str(dst).replace(str(HOME), '~')}")
    print(f"Файлов {'возвращено' if apply else 'вернётся'}: {moved}.")
    if apply and keep.exists():
        print(f"То, что было на компьютере до этого, сохранено в {keep}.")
    if old_home and old_home != str(HOME) and (DEST / "claude/settings.json").exists():
        print(f"Внимание: на старом компьютере домашняя папка была {old_home}, сейчас {HOME}. "
              "В настройках (settings.json) старые пути — агент поправит их по просьбе «поправь пути после восстановления».")
    print("Дальше — подключить сервисы и ввести ключи по списку в _настройки-ИИ/ОПИСЬ.md.")
    return 0


if __name__ == "__main__":
    if "--proverit-oblako" in sys.argv:
        if not (DEST / "_откуда.json").exists():
            sys.exit(0)  # копии настроек нет — отправлять нечего опасного
        c = cloud_check("--oblako-privatnoe" in sys.argv)[0]
        print({0: "Можно отправлять: облако закрыто.", 4: "НЕ ОТПРАВЛЯТЬ: облако открыто всем, а в базе копия настроек и памяти ИИ.",
               6: "НЕ ОТПРАВЛЯТЬ: не смог проверить, закрыто ли облако. Спроси человека и запусти с --oblako-privatnoe."}[c])
        sys.exit(c)
    if "--vosstanovit" in sys.argv:
        sys.exit(restore("--da" in sys.argv))
    sys.exit(backup("--arhiv" in sys.argv, "--eto-ne-pdn" in sys.argv, "--oblako-privatnoe" in sys.argv))
