mkdir -p /c/OpenJarvis/skills/fullstack-blueprint

cat << 'EOF' > /c/OpenJarvis/skills/fullstack-blueprint/SKILL.md
---
name: fullstack-blueprint
description: >
  Активируется при создании, рефакторинге или масштабировании агентных систем
  на базе OpenJarvis: локальные LLM через LM Studio, кастомные MCP-серверы
  на Python, оркестрация инструментов и промпт-инжиниринг.
version: 1.0.0
---

# Протокол разработки агентных систем (Agent-First & Verified Build)

При получении задачи на разработку или расширение OpenJarvis выполняй строго 4 фазы:

## Фаза 1: Выбор стека и фиксация контрактов
1. **Модель и движок:** выбери локальную модель под задачу (Gemma 4 12B через LM Studio для общего ассистента; Qwen2.5-Coder для кодогенерации; специализированные GGUF под узкие домены). Зафиксируй `preferred_engine` и `default_model` в `configs/openjarvis/config.toml`.
2. **MCP-инструменты:** определи список необходимых серверов (geolocator, duckduckgo-search, brave_browser, filesystem, git, fetch, memory, github, tavily, context7 и т.д.). Для каждого зафиксируй контракт: имя инструмента, входные параметры (Pydantic-схема), формат JSON-ответа.
3. **Промпт-контракты:** создай единый источник истины для системных промптов в `configs/openjarvis/prompts/` — один файл на агентную роль (code, research, ops).

## Фаза 2: Реализация слоёв
1. **Model Layer:** загрузи модель через `lms get <repo>:<quant>` и проверь инференс через `curl http://127.0.0.1:1234/v1/chat/completions`. Настрой `temperature`, `max_tokens`, `top_p` под задачу в `config.toml`.
2. **Tools Layer:** реализуй каждый кастомный MCP-сервер в `M:\MyMCPTools\` по шаблону:
   ```python
   from mcp.server.mcpserver import MCPServer
   mcp = MCPServer("<имя-сервера>")

   @mcp.tool()
   def instrument_name(param: str) -> dict:
       """Краткое описание для LLM — это то, что видит модель при выборе инструмента."""
       ...
       return {"result": ...}

   if __name__ == "__main__":
       mcp.run()