from mcp.server.mcpserver import MCPServer

# Инициализация сервера
mcp = MCPServer("geolocator")


# Пример инструмента (Tool)
@mcp.tool()
def get_city_coordinates(city_name: str) -> dict:
    """Возвращает координаты указанного города."""
    # Здесь должна быть ваша логика геокодинга
    return {"lat": 0.0, "lon": 0.0, "message": f"Coords for {city_name}"}


if __name__ == "__main__":
    # mcp.run() по умолчанию использует stdio, как и требовалось для MCP [[23]]
    mcp.run()
