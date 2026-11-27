import httpx

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("MyGeolocator")


@mcp.tool()
def get_current_location() -> str:
    """Получает текущую геолокацию пользователя (страна, город, координаты, часовой пояс) по его IP-адресу."""
    try:
        response = httpx.get("http://ip-api.com/json/", timeout=10.0)
        data = response.json()
        if data.get("status") == "success":
            return (
                f"Страна: {data.get('country')}, "
                f"Регион: {data.get('regionName')}, "
                f"Город: {data.get('city')}, "
                f"Координаты: {data.get('lat')}, {data.get('lon')}, "
                f"Часовой пояс: {data.get('timezone')}, "
                f"Провайдер: {data.get('isp')}"
            )
        return "Не удалось определить локацию."
    except Exception as e:
        return f"Ошибка сети при получении локации: {str(e)}"


if __name__ == "__main__":
    mcp.run()
