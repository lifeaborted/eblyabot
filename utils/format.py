import re
import html


def format_caption(uploader: str, title: str, description: str, tags: list = None) -> str:
    raw_text = description if description else title

    # 1. Собираем теги
    text_hashtags = re.findall(r'#\w+', raw_text)
    explicit_tags = [f"#{t}" for t in (tags or [])]

    all_tags = text_hashtags + explicit_tags
    seen = set()
    unique_tags = [x for x in all_tags if not (x in seen or seen.add(x))]

    # 2. Очищаем описание от хэштегов
    clean_desc = re.sub(r'#\w+', '', raw_text).strip()

    # 3. Экранируем спецсимволы для HTML
    safe_uploader = html.escape(uploader) if uploader and uploader != "Unknown" else "Неизвестный автор"
    safe_desc = html.escape(clean_desc)
    safe_tags = html.escape(" ".join(unique_tags))

    # Собираем базовые блоки подписи
    header_parts = [f"<b>{safe_uploader}</b>"]
    if safe_tags:
        header_parts.append(safe_tags)

    header_text = "\n".join(header_parts)

    # 4. Жесткий расчет лимита для описания
    # Максимум Телеграма = 1024. Оставим небольшой запас (1000 символов),
    # чтобы HTML-теги оформления точно не переполнили лимит.
    max_total_len = 1000
    allowed_desc_len = max_total_len - len(header_text) - 2  # 2 символа на переносы строк (\n\n)

    if safe_desc and allowed_desc_len > 0:
        if len(safe_desc) > allowed_desc_len:
            # Обрезаем описание ровно по остатку места и добавляем троеточие
            safe_desc = safe_desc[:allowed_desc_len - 3] + "..."
        return f"{header_text}\n\n{safe_desc}"

    return header_text


def strip_html_tags(text: str) -> str:
    if not text: return "Медиа"
    return re.sub(r'<[^>]+>', '', text).replace('\n', ' ').strip()