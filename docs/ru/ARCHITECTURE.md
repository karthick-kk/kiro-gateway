# Архитектурный Обзор: Kiro OpenAI Gateway

## 1. Назначение и Цели Системы

Проект представляет собой высокоуровневый прокси-шлюз, реализующий структурный паттерн проектирования **"Адаптер" (Adapter)**.

Основная цель системы — обеспечить прозрачную совместимость между двумя гетерогенными интерфейсами:
1.  **Target Interface (Клиент):** Стандартный протокол OpenAI API (эндпоинты `/v1/models`, `/v1/chat/completions`).
2.  **Adaptee (Поставщик):** Внутренний API Kiro IDE (AWS CodeWhisperer), обнаруженный в экосистеме Amazon Kiro.

Система выступает в роли "переводчика", позволяя использовать любые инструменты, библиотеки и IDE-плагины, разработанные для экосистемы OpenAI, с моделями Claude через Kiro API.

## 2. Структура Проекта

Проект организован в виде модульного Python-пакета `kiro_gateway/`:

```
kiro-openai-gateway/
├── main.py                    # Точка входа, создание FastAPI приложения
├── config.py                  # Legacy конфиг (для обратной совместимости)
├── debug_logger.py            # Отладочное логирование запросов
├── requirements.txt           # Зависимости Python
│
├── kiro_gateway/              # Основной пакет
│   ├── __init__.py            # Экспорты пакета
│   ├── config.py              # Конфигурация и константы
│   ├── models.py              # Pydantic модели OpenAI API
│   ├── auth.py                # KiroAuthManager - управление токенами
│   ├── cache.py               # ModelInfoCache - кэш моделей
│   ├── utils.py               # Вспомогательные утилиты
│   ├── converters.py          # Конвертация OpenAI <-> Kiro
│   ├── parsers.py             # Парсеры AWS SSE потоков
│   ├── streaming.py           # Логика стриминга ответов
│   ├── http_client.py         # HTTP клиент с retry логикой
│   └── routes.py              # FastAPI роуты
│
├── tests/                     # Тесты
│   ├── unit/                  # Юнит-тесты
│   └── integration/           # Интеграционные тесты
│
└── debug_logs/                # Отладочные логи (генерируются)
```

## 3. Архитектурная Топология и Компоненты

Система построена на базе асинхронного фреймворка `FastAPI` и использует событийную модель управления жизненным циклом (`Lifespan Events`).

### 3.1. Модуль конфигурации (`kiro_gateway/config.py`)

Централизованное хранение всех настроек:

| Параметр | Описание | Значение по умолчанию |
|----------|----------|----------------------|
| `PROXY_API_KEY` | API ключ для доступа к прокси | `changeme_proxy_secret` |
| `REFRESH_TOKEN` | Refresh token Kiro | из `.env` |
| `REGION` | Регион AWS | `us-east-1` |
| `TOKEN_REFRESH_THRESHOLD` | Время до обновления токена | 600 сек (10 мин) |
| `MAX_RETRIES` | Макс. количество повторов | 3 |
| `MODEL_CACHE_TTL` | TTL кэша моделей | 3600 сек (1 час) |

### 3.2. Управление Состоянием (State Management Layer)

#### KiroAuthManager (`kiro_gateway/auth.py`)

**Роль:** Stateful-синглтон, инкапсулирующий логику управления токенами Kiro.

**Возможности:**
- Загрузка credentials из `.env` или JSON файла
- Поддержка `expiresAt` для проверки времени истечения токена
- Автоматическое обновление токена за 10 минут до истечения
- Сохранение обновлённых токенов обратно в JSON файл
- Поддержка разных регионов AWS
- Генерация уникального fingerprint для User-Agent

**Concurrency Control:** Использует `asyncio.Lock` для защиты от состояния гонки.

```python
# Пример использования
auth_manager = KiroAuthManager(
    refresh_token="your_token",
    region="us-east-1"
)
token = await auth_manager.get_access_token()
```

#### ModelInfoCache (`kiro_gateway/cache.py`)

**Роль:** Потокобезопасное хранилище конфигураций моделей.

**Стратегия Заполнения:** 
- Lazy Loading через `/ListAvailableModels`
- TTL кэша: 1 час
- Fallback на статический список моделей

### 3.3. Слой Конвертации (`kiro_gateway/converters.py`)

#### Конвертация сообщений

OpenAI messages преобразуются в Kiro conversationState:

1. **System prompt** — добавляется к первому user сообщению
2. **История сообщений** — полностью передаётся в `history` array
3. **Объединение соседних сообщений** — сообщения с одинаковой ролью мерджатся
4. **Tool calls** — поддержка OpenAI tools формата
5. **Tool results** — корректная передача результатов вызова инструментов

#### Маппинг моделей

Внешние имена моделей преобразуются во внутренние ID Kiro:

| Внешнее имя | Внутренний ID Kiro |
|-------------|-------------------|
| `claude-opus-4-5` | `claude-opus-4.5` |
| `claude-opus-4-5-20251101` | `claude-opus-4.5` |
| `claude-haiku-4-5` | `claude-haiku-4.5` |
| `claude-sonnet-4-5` | `CLAUDE_SONNET_4_5_20250929_V1_0` |
| `claude-sonnet-4-5-20250929` | `CLAUDE_SONNET_4_5_20250929_V1_0` |
| `claude-sonnet-4` | `CLAUDE_SONNET_4_20250514_V1_0` |
| `claude-sonnet-4-20250514` | `CLAUDE_SONNET_4_20250514_V1_0` |
| `claude-3-7-sonnet-20250219` | `CLAUDE_3_7_SONNET_20250219_V1_0` |

### 3.4. Слой Парсинга (`kiro_gateway/parsers.py`)

#### AwsEventStreamParser

Продвинутый парсер AWS SSE формата с поддержкой:

- **Bracket counting** — корректный парсинг вложенных JSON объектов
- **Дедупликация контента** — фильтрация повторяющихся событий
- **Tool calls** — парсинг структурированных и bracket-style tool calls
- **Escape-последовательности** — декодирование `\n` и других

#### Типы событий

| Событие | Описание |
|---------|----------|
| `content` | Текстовый контент ответа |
| `tool_start` | Начало tool call (name, toolUseId) |
| `tool_input` | Продолжение input для tool call |
| `tool_stop` | Завершение tool call |
| `usage` | Информация о потреблении кредитов |
| `context_usage` | Процент использования контекста |

### 3.5. HTTP Клиент (`kiro_gateway/http_client.py`)

#### KiroHttpClient

Автоматическая обработка ошибок с exponential backoff:

| Код ошибки | Действие |
|------------|----------|
| `403` | Refresh токена + повтор |
| `429` | Exponential backoff (1s, 2s, 4s) |
| `5xx` | Exponential backoff (до 3 попыток) |
| Timeout | Exponential backoff |

### 3.6. Kiro API Endpoints

Все URL динамически формируются на основе региона:

*   **Token Refresh:** `POST https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
*   **List Models:** `GET https://q.{region}.amazonaws.com/ListAvailableModels`
*   **Generate Response:** `POST https://codewhisperer.{region}.amazonaws.com/generateAssistantResponse`

## 4. Детальный Поток Данных

```
┌─────────────────┐
│  OpenAI Client  │
└────┬────────┘
         │ POST /v1/chat/completions
         ▼
┌─────────────────┐
│  Security Gate  │ ◄── Проверка Bearer токена прокси
│  (routes.py)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ KiroAuthManager │ ◄── Получение/обновление accessToken
│   (auth.py)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Payload Builder │ ◄── Конвертация OpenAI → Kiro формат
│ (converters.py) │     (история, system prompt, tools)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ KiroHttpClient  │ ◄── Retry логика (403, 429, 5xx)
│ (http_client.py)│
└────────┬────────┘
         │ POST /generateAssistantResponse
         ▼
┌─────────────────┐
│   Kiro API      │
└────────┬────────┘
         │ AWS SSE Stream
         ▼
┌─────────────────┐
│ SSE Parser      │ ◄── Парсинг событий, tool calls
│  (parsers.py)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ OpenAI Format   │ ◄── Конвертация в OpenAI SSE
│ (streaming.py)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  OpenAI Client  │
└─────────────────┘
```

## 5. Доступные Модели

| Модель | Описание | Credits |
|--------|----------|---------|
| `claude-opus-4-5` | Топовая модель | ~2.2 |
| `claude-opus-4-5-20251101` | Топовая модель (версия) | ~2.2 |
| `claude-sonnet-4-5` | Улучшенная модель | ~1.3 |
| `claude-sonnet-4-5-20250929` | Улучшенная модель (версия) | ~1.3 |
| `claude-sonnet-4` | Сбалансированная модель | ~1.3 |
| `claude-sonnet-4-20250514` | Сбалансированная (версия) | ~1.3 |
| `claude-haiku-4-5` | Быстрая модель | ~0.4 |
| `claude-3-7-sonnet-20250219` | Legacy модель | ~1.0 |

## 6. Конфигурация

### Переменные окружения (.env)

```env
# Обязательные
REFRESH_TOKEN="your_kiro_refresh_token"
PROXY_API_KEY="your_proxy_secret"

# Опциональные
PROFILE_ARN="arn:aws:codewhisperer:..."
KIRO_REGION="us-east-1"
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"
```

### JSON файл credentials (опционально)

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "profileArn": "arn:aws:codewhisperer:us-east-1:...",
  "region": "us-east-1"
}
```

## 7. API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/` | GET | Health check |
| `/health` | GET | Детальный health check |
| `/v1/models` | GET | Список доступных моделей |
| `/v1/chat/completions` | POST | Chat completions (streaming/non-streaming) |

## 8. Особенности Реализации

### Tool Calling

Поддержка OpenAI-совместимого формата tools:

```json
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get weather for a location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {"type": "string"}
        }
      }
    }
  }]
}
```

### Streaming

Полная поддержка SSE streaming с корректным форматом OpenAI:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

data: [DONE]
```

### Отладка

Все запросы и ответы логируются в `debug_logs/`:
- `request_body.json` — входящий запрос
- `google_request_body.json` — запрос к Kiro API
- `response_stream_raw.txt` — сырой поток от Kiro
- `response_stream_modified.txt` — преобразованный поток

## 9. Расширяемость

### Добавление нового провайдера

Модульная архитектура позволяет легко добавить поддержку других провайдеров:

1. Создать новый модуль `kiro_gateway/providers/new_provider.py`
2. Реализовать классы:
   - `NewProviderAuthManager` — управление токенами
   - `NewProviderConverter` — конвертация форматов
   - `NewProviderParser` — парсинг ответов
3. Добавить роуты в `routes.py` или создать отдельный роутер

### Пример структуры для нового провайдера

```python
# kiro_gateway/providers/gemini.py

class GeminiAuthManager:
    """Управление API ключами Gemini."""
    pass

class GeminiConverter:
    """Конвертация OpenAI -> Gemini формат."""
    pass

class GeminiParser:
    """Парсинг SSE потока Gemini."""
    pass
