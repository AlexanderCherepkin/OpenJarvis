from duckduckgo_search import DDGS


def search_internet(query, max_results=5):
    """
    Функция ищет информацию в DuckDuckGo и возвращает список результатов.
    Ключи API и регистрация не требуются.
    """
    try:
        with DDGS() as ddgs:
            # Делаем текстовый поиск
            # rsd = region='wt-wt' (мировой поиск), safesearch='moderate'
            results = ddgs.text(query, max_results=max_results)

            # Превращаем результаты в удобный список словарей
            search_data = []
            for r in results:
                search_data.append(
                    {
                        "title": r.get("title"),  # Заголовок сайта
                        "url": r.get("href"),  # Ссылка
                        "snippet": r.get("body"),  # Краткое описание/текст
                    }
                )
            return search_data

    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return []


# --- Пример использования ---
if __name__ == "__main__":
    my_query = "Последние новости Python 2026"
    print(f"Ищем: '{my_query}'...\n")

    found_pages = search_internet(my_query, max_results=3)

    for i, page in enumerate(found_pages, 1):
        print(f"{i}. {page['title']}")
        print(f"   Ссылка: {page['url']}")
        print(f"   Текст: {page['snippet']}\n")
