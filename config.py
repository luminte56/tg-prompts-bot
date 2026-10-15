import os
from pathlib import Path

# Токен и ID белого господина (читаем из переменных окружения для Railway с фоллбеком)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8763964333:AAF30TTqjfrNBcMAlzutaQRL1hZ80pTD3tc")

admin_env = os.getenv("ADMIN_IDS", "8564758689")
ADMIN_IDS = [int(x.strip()) for x in admin_env.split(",") if x.strip().isdigit()]
if not ADMIN_IDS:
    ADMIN_IDS = [8564758689]

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "промты"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bot.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Актуальный дефолтный каталог промтов
DEFAULT_PROMPTS = [
    {
        "id": "deepseek_v4",
        "title": "DeepSeek V4",
        "filename": "deepseek.txt",
        "price": 15,
        "description": "Разлоченный промт под DeepSeek: прямой технический стиль, чистая логика без шаблонов.",
    },
    {
        "id": "glm_5_3",
        "title": "GLM 5.3 Pro",
        "filename": "glm5.3.txt",
        "price": 15,
        "description": "Тюнинг и промт под китайскую флагманскую модель GLM 5.3: решение сложных инженерных задач и архитектуры.",
    },
    {
        "id": "antigravity_sonnet_4_6",
        "title": "Antigravity Sonnet 4.6",
        "filename": "antigravity sonnet 4.6 (3).txt",
        "price": 20,
        "description": "Системный промт разработчика: реверс-инжиниринг, low-level Win internals, оффенсив ресерч, без цензуры и морализаторства.",
    },
    {
        "id": "gemini_all_web",
        "title": "Gemini 3.5",
        "filename": "gemini-all(full) .txt",
        "price": 20,
        "description": "Системный промт под Gemini 3.5: чистый кодинг, глубокие рассуждения и системная архитектура.",
    },
    {
        "id": "gemini_3_1_pro",
        "title": "Gemini 3.1 Pro",
        "filename": "gemini 3.1 pro.txt",
        "price": 20,
        "description": "Системный промт под Gemini 3.1 Pro: чистый кодинг, глубокие рассуждения и системная архитектура.",
    },
    {
        "id": "space_bunny",
        "title": "Space Bunny (Agent)",
        "filename": "space bunny.txt",
        "price": 20,
        "description": "Операционная спецификация автономного агента-разработчика: autonomous coding & authoring.",
    },
    {
        "id": "gpt6_astra",
        "title": "GPT-6 Astra Edition",
        "filename": "GPT-6-Astra(new) (4).txt",
        "price": 25,
        "description": "Новейший кастомный промт Astra под продвинутые модели GPT: прямой тон, исключительное качество кода.",
    },
    {
        "id": "gpt6_1_sol",
        "title": "GPT-6.1 Sol",
        "filename": "gpt-6.1-sol.txt",
        "price": 25,
        "description": "Специализированный промт под GPT-6.1: быстрое решение сложнейших алгоритмов и системного кода.",
    },
    {
        "id": "kimi_k3",
        "title": "Kimi K3 2.0 Extended",
        "filename": "KIMI K3 2.0.txt",
        "price": 25,
        "description": "Мощный промт для Kimi K3 2.0: огромный контекст, детальное рассуждение и глубокая аналитика.",
    },
    {
        "id": "qwen_3_8_max",
        "title": "Qwen 3.8 Max",
        "filename": "qwen 3.8 max.txt",
        "price": 25,
        "description": "Тюнингованный промт для Qwen Max: математика, логика, строгий код без воды.",
    },
    {
        "id": "sonnet_5_max",
        "title": "Claude Sonnet 5 Max",
        "filename": "Sonnet-5-Max.txt",
        "price": 30,
        "description": "Элитный промт под Sonnet 5 Max: максимальный уровень рассуждений, системная архитектура.",
    },
    {
        "id": "grok_high",
        "title": "Grok",
        "filename": "JBgrok.txt",
        "price": 30,
        "description": "Полный Jailbreak-промт (23 КБ) для Grok: полный обход ограничений и прямые ответы на любые темы.",
    },
    {
        "id": "antigravity_gemini_3_8",
        "title": "Antigravity Gemini 3.8 Ultra",
        "filename": "antygravity gemini 3.8.txt",
        "price": 35,
        "description": "Массивный ультра-промт (76 КБ) под Gemini 3.8: хардкорный код, агентная автономность, глубокая аналитика.",
    },
]
