# Модели, параметры и площадки — срез 27.10.2026

Этот файл устаревает быстрее правил. Перед api-mode для конкретной модели сверяй строку с документацией вендора.
Статус сверки: **✓** — сверено с первоисточником при обновлении v4.0; **P** — собрано из официальных документов через ресерч, первоисточник напрямую не открывался.

## 1. Актуальные модели

| Вендор | Модель — API ID | Роль | Контекст / вывод | Сверка |
|---|---|---|---|---|
| Anthropic | Claude Fable 5.1 — `claude-fable-5-1` | максимум возможностей | 1M / 128K | ✓ |
| Anthropic | Claude Opus 5.5 — `claude-opus-5-5` | основной флагман | 1M / 128K | ✓ |
| Anthropic | Claude Sonnet 5.5 — `claude-sonnet-5-5` | баланс | 1M / 128K | ✓ |
| Anthropic | Claude Haiku 5.5 — `claude-haiku-5-5` | быстрый, дешёвый | 1M / 128K | ✓ |
| OpenAI | GPT-6 Astra — `gpt-6-astra` | максимум возможностей | 1,05M / 128K | P |
| OpenAI | GPT-6.1 Sol — `gpt-6.1-sol` | доступный reasoning-флагман | 1,05M / 128K | P |
| OpenAI | GPT-6.1 Terra — `gpt-6.1-terra` | быстрый средний | 1,05M / 128K | P |
| OpenAI | GPT-6 Luna — `gpt-6-luna` | массовый, дешёвый | 1,05M / 128K | P |
| Google | Gemini 4 Argon — `gemini-4-argon` | флагман | 1 048 576 общее окно (вход + рассуждения + вывод) | P |
| Google | Gemini 3.8 Flash — `gemini-3.8-flash` | быстрый основной | 1M / 65 536 | P |
| Google | Gemini 3.5 Flash-Lite — `gemini-3.5-flash-lite` | самый дешёвый | 1M / 65 536 | P |
| xAI | Grok 4.7 — `grok-4.7` | флагман | 500K | P |
| xAI | Grok 4.3 — `grok-4.3` | быстрый | 1M | P |
| DeepSeek | V4-Pro — `deepseek-v4-pro` | флагман | 1M / 384K | P |
| DeepSeek | V4.1-Flash — `deepseek-flash` | быстрый | 1M / 384K | P |
| Alibaba | Qwen3.8-Max — `qwen3.8-max` | флагман | 1M / ответ 131K + рассуждения до 262K | P |
| Alibaba | Qwen3.8-Flash — `qwen3.8-flash` | быстрый | 1M | P |
| Moonshot | Kimi K3.1 Pro — `kimi-k3.1-pro` | флагман | 1M | P |
| Mistral | Mistral Large 4 — `mistral-large-4` (preview) | флагман | 1M | P |
| Mistral | Mistral Small 4 — `mistral-small-2603` | быстрый | 256K | P |
| Meta | Llama 4 Maverick / Scout (open-weight) | открытые веса | 1M / 10M по model card | P |

## 2. Глубина рассуждений

| Модели | Параметр | Значения и default | Важно |
|---|---|---|---|
| Claude Fable 5.1, Opus 5.5 | `output_config.effort` + `thinking.type: "adaptive"` | low · medium · high · xhigh · max; Fable — high, Opus 5.5 — medium | thinking не отключается ✓. Opus 5.5: начинать с medium, xhigh/max — только при измеренном выигрыше ✓ |
| Claude Sonnet 5.5 | то же | default high | `between_tools` — только до high |
| Claude Haiku 5.5 | то же | default medium | `disabled` — только до high |
| GPT-6 Astra, 6.1 Sol | `reasoning.effort` (Responses) / `reasoning_effort` (Chat) | low · medium · high · xhigh · max; `none` нет | `reasoning.mode: standard/pro` |
| GPT-6.1 Terra, GPT-6 Luna | то же | none · low · medium · high · xhigh · max; default medium | `minimal` не перечислен |
| Gemini 4 Argon, 3.8 Flash | `thinking_level` | low · medium · high; default medium | thinking у Argon не отключается; temperature/top_p/top_k игнорируются |
| Gemini 3.5 Flash-Lite | `thinking_level` | minimal · low · medium · high | |
| Grok 4.7 | `reasoning.effort` | low · medium · high · xhigh; default high | не отключается; xAI советует temperature 0.7, top_p 0.95 |
| DeepSeek V4 | `reasoning_effort` / `thinking.type` | none · low · high · max; default high | medium и xhigh → high; в thinking sampling-поля не действуют |
| Qwen3.8 | `reasoning.effort` (Responses) / `reasoning_effort` | none · low · medium · xhigh | high/max → xhigh; `enable_thinking` уходит в deprecated |
| Kimi K3.1 Pro | `reasoning_effort` | low · high · max; default max | thinking всегда включён |
| Mistral Large 4 / Small 4 | `reasoning_effort` | none · high | |

**Общее правило:** у reasoning-моделей лимит вывода (`max_tokens`, `max_output_tokens`) обычно включает и рассуждения. Маленький лимит может закончиться раньше видимого ответа: для агентных задач на Claude Opus 5.5 Anthropic ставила 128 000 ✓, Gemini 4 советует не меньше 32 768.

## 3. Куда класть системную инструкцию

| Вендор | Место |
|---|---|
| Anthropic | поле `system` (в середине диалога — system-сообщения по правилам размещения) |
| OpenAI | Responses: `instructions` или сообщение `developer`; `instructions` не переносится через `previous_response_id` — передавать каждый раз |
| Google | `system_instruction` / `systemInstruction` — отдельная настройка, не сообщение в `contents` |
| xAI, DeepSeek, Qwen, Kimi, Mistral | сообщение `role: "system"` |
| Llama | system prompt по шаблону выбранного сервера |

## 4. Кэш промпта

| Провайдер | Что известно |
|---|---|
| Anthropic | явные метки `cache_control`; TTL 5 мин или 1 ч; запись дороже базового входа в 1,25× / 2× ✓. Смена `effort` между запросами сбрасывает кэш; менять посреди диалога — через per-message effort (beta) ✓ |
| OpenAI | автоматический для поддерживаемых моделей; у GPT-5.6+ минимум 1024 токена; есть явные точки разрыва и TTL 30 мин / 12 ч; `prompt_cache_key` для стабильной маршрутизации |
| xAI | постоянный `prompt_cache_key` на разговор; контекст только дописывать, прошлые элементы не править |

## 5. Площадки для готового промпта

| Площадка | Инструкция | Файлы | Как читает файлы | Статус |
|---|---|---|---|---|
| ChatGPT Custom GPTs | ~8 000 символов (по сообществу) | 20 × до 512 МБ | поиск по фрагментам | **закрываются 11.12.2026** (P) → Plugins + Skills |
| ChatGPT Projects | лимит не опубликован | 5–40 по тарифу | поиск, точный алгоритм не раскрыт | работает |
| ChatGPT Plugins / Skills | SKILL.md, лимит не опубликован | references / scripts / assets | по условию из SKILL.md | новый формат |
| Gemini Gems | лимит не опубликован | до 10 за раз, до 100 МБ | поиск | **только чтение с 17.11.2026, удаление 17.12.2026** для личных аккаунтов ✓; Workspace — март 2027 |
| Gemini Skills | SKILL.md | 100 МБ суммарно на skill ✓ | по релевантности, вызов `/имя` | до 100 активных ✓ |
| Gemini Notebook (NotebookLM) | Custom chat ~10 000 (не подтверждено) | 50–600 источников по тарифу | по выбранным источникам | работает |
| Claude Projects | лимит не опубликован | до 30 МБ на файл | целиком, пока влезает; дальше автоматический RAG | работает, новая версия в beta |
| Claude Skills | SKILL.md: лучше до 500 строк; description до 200 символов в приложении (до 1024 в API) | references / scripts | метаданные → SKILL.md → файлы по необходимости | работает |
| Claude Code | CLAUDE.md: лучше до 200 строк | файловая система | при старте и по папкам; skills по вызову | работает |
| Codex | AGENTS.md: 32 KiB по умолчанию | репозиторий | цепочка файлов при старте | работает |

**Перенос GPT/Gem → Skill:** инструкция становится SKILL.md, файлы знаний — references; Custom Actions и выбор модели не переносятся автоматически; у Gemini при превышении 100 МБ удаляются самые большие файлы.

## 6. Снятые и уходящие модели (2026)

Не генерировать промпты и параметры под эти ID:
- Anthropic: Claude 3.x, Sonnet/Opus 4, Opus 4.1 — сняты; `claude-sonnet-4-5-20250929` — снятие 30.11.2026.
- OpenAI: o1, o3-mini, o4-mini, GPT-4 / 4-turbo / 3.5 — отключены 23.10.2026; GPT-5 / 5-mini / 5-nano / 5-pro, o3, o3-pro — отключение 11.12.2026; GPT-4o и GPT-4.1 (снимки 2024–2025) — 14.01.2027. Assistants API закрыт 26.08.2026 → Responses.
- Google: Gemini 2.0 Flash — отключён; 3.5 Flash и 3.7 Flash перенаправляются на новые версии.
- xAI: Grok 3, Grok 4 / 4-fast / 4.1-fast — с 15.05.2026 старые ID ведут на Grok 4.3.
- DeepSeek: `deepseek-chat` / `deepseek-reasoner` заменены на `deepseek-flash` / `deepseek-v4-pro`.
- Kimi: K2.x — недоступны новым пользователям с 31.10.2026, полное снятие до конца декабря.
