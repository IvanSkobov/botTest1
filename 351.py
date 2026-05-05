def receive_email_mail(arguments):
    """
    Получение Email сообщений через IMAP сервер mail.ru.
    Исправленная и улучшенная версия: корректная обработка заголовка From (имя + email),
    безопасное использование переменных (unread_only и др.), декодирование Subject и From.
    """
    import imaplib
    import email
    from email.header import decode_header, make_header
    from email.utils import parsedate_to_datetime, parseaddr
    import re
    import json
    import html
    from datetime import datetime, timedelta

    # Параметры Mail.ru
    HOST = "imap.mail.ru"
    PORT = 993
    DEFAULT_FOLDER = 'INBOX'

    def _parse_period(period_str):
        """Парсинг строкового описания периода в даты начала и окончания."""
        now = datetime.now()
        start_date = None
        end_date = None

        period_str_lower = period_str.lower().strip()

        if period_str_lower == "сегодня":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif period_str_lower == "неделя" or period_str_lower == "последняя неделя":
            start_date = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif " - " in period_str_lower:
            parts = period_str.split(" - ")
            if len(parts) != 2:
                raise ValueError("Неверный формат периода. Используйте 'YYYY-MM-DD - YYYY-MM-DD' или 'DD.MM.YYYY - DD.MM.YYYY'.")
            start_date_str = parts[0].strip()
            end_date_str = parts[1].strip()

            # Попытка парсинга YYYY-MM-DD, иначе DD.MM.YYYY
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError:
                start_date = datetime.strptime(start_date_str, "%d.%m.%Y").replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = datetime.strptime(end_date_str, "%d.%m.%Y").replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            raise ValueError("Неподдерживаемый формат периода. Используйте 'сегодня', 'неделя', 'YYYY-MM-DD - YYYY-MM-DD' или 'DD.MM.YYYY - DD.MM.YYYY'.")

        return start_date, end_date

    def _strip_html_tags(html_string):
        """Удаление HTML-тегов, включая блоки <style>...</style>, и декодирование HTML-сущностей."""
        clean = re.sub(r'<style[^>]*>.*?</style>', '', html_string, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', '', clean)
        clean = html.unescape(clean)
        return clean

    def _clean_text_body(text_string):
        """Общая очистка текстового тела письма."""
        clean = text_string.replace('\r', '')
        clean = re.sub(r'[\xa0\u2000-\u200A\u202F\u205F\u3000]', ' ', clean)
        clean = re.sub(r'^\s*(?:@import[^;]*;?|@media[^{]*\{[^{}]*[^}]*\})\s*', '', clean, flags=re.MULTILINE | re.DOTALL)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    emails_data = []
    skipped_emails_by_date_filter = 0
    skipped_emails_by_keyword_filter = 0

    start_dt, end_dt = None, None
    period_requested_formatted = arguments.get('period', "N/A")
    final_message_warning = None

    try:
        # Проверяем обязательные аргументы (без использования необъявленных переменных)
        required_args = ["email_account", "password"]
        # безопасные значения, используемые в сообщениях об ошибках
        safe_unread_only = arguments.get('unread_only', False)
        safe_keywords = arguments.get('keywords', [])
        safe_period = arguments.get('period', None)

        for arg in required_args:
            if arg not in arguments:
                result = {
                    "status": "error",
                    "message": f"Отсутствует обязательный аргумент: '{arg}'",
                    "emails_count": 0,
                    "period_requested": safe_period or "N/A",
                    "keywords_requested": safe_keywords,
                    "emails_skipped_by_date_filter": 0,
                    "emails_skipped_by_keyword_filter": 0,
                    "unread_only_requested": safe_unread_only,
                }
                return json.dumps(result, ensure_ascii=False, indent=2)

        # Извлекаем параметры (теперь безопасно)
        email_account = arguments['email_account']
        password = arguments['password']
        last_n_emails = arguments.get('last_n_emails', 1)
        keywords = arguments.get('keywords', [])
        max_debug_output_emails = arguments.get('max_debug_output_emails', 10)
        max_uids_to_fetch = arguments.get('max_uids_to_fetch', 100)
        debug = arguments.get('debug', False)
        period = arguments.get('period')
        unread_only = arguments.get('unread_only', False)
        mark_as_read = arguments.get('mark_as_read', False)

        # Валидация last_n_emails
        if not isinstance(last_n_emails, int):
            result = {
                "status": "error",
                "message": "Значение 'last_n_emails' должно быть целым числом.",
                "emails_count": 0,
                "period_requested": period_requested_formatted,
                "keywords_requested": keywords,
                "emails_skipped_by_date_filter": 0,
                "emails_skipped_by_keyword_filter": 0,
                "unread_only_requested": unread_only,
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        if last_n_emails < 1:
            result = {
                "status": "error",
                "message": "Значение 'last_n_emails' должно быть целым числом не менее 1.",
                "emails_count": 0,
                "period_requested": period_requested_formatted,
                "keywords_requested": keywords,
                "emails_skipped_by_date_filter": 0,
                "emails_skipped_by_keyword_filter": 0,
                "unread_only_requested": unread_only,
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        # Корректировка last_n_emails относительно max_uids_to_fetch
        applied_last_n_emails = last_n_emails
        if last_n_emails > max_uids_to_fetch:
            if debug:
                print(f"Предупреждение: Значение 'last_n_emails' ({last_n_emails}) превышает 'max_uids_to_fetch' ({max_uids_to_fetch}). Используется значение {max_uids_to_fetch}.")
            applied_last_n_emails = max_uids_to_fetch
            final_message_warning = (
                f"Значение 'last_n_emails' ({last_n_emails}) превышает 'max_uids_to_fetch' ({max_uids_to_fetch}). Обрабатывается только {max_uids_to_fetch} последних писем."
            )

        # Парсинг периода
        if period:
            try:
                start_dt, end_dt = _parse_period(period)
                if period.lower() == "сегодня":
                    period_requested_formatted = start_dt.strftime("%Y-%m-%d")
                elif period.lower() in ("неделя", "последняя неделя"):
                    period_requested_formatted = "последняя неделя"
                elif start_dt and end_dt:
                    period_requested_formatted = f"{start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}"
            except ValueError as ve:
                result = {
                    "status": "error",
                    "message": f"{ve} Проверка формата.",
                    "emails_count": 0,
                    "period_requested": period,
                    "keywords_requested": keywords,
                    "emails_skipped_by_date_filter": 0,
                    "emails_skipped_by_keyword_filter": 0,
                    "unread_only_requested": unread_only,
                }
                return json.dumps(result, ensure_ascii=False, indent=2)

        # Подключение к IMAP серверу через SSL
        if debug:
            print(f"Подключение к IMAP серверу: {HOST}:{PORT}")
        mail = imaplib.IMAP4_SSL(HOST, PORT)
        mail.debug = 4 if debug else 0

        # Авторизация
        if debug:
            print(f"Авторизация под логином: {email_account}")
        try:
            mail.login(email_account, password)
        except Exception as e:
            error_msg = str(e)
            if "AUTHENTICATIONFAILED" in error_msg.upper():
                error_msg = "Неверный логин или пароль. Убедитесь, что используется пароль приложения, если это требуется почтовым сервисом."
            result = {
                "status": "error",
                "message": f"Ошибка подключения/авторизации: {error_msg}",
                "emails_count": 0,
                "period_requested": period_requested_formatted,
                "keywords_requested": keywords,
                "emails_skipped_by_date_filter": 0,
                "emails_skipped_by_keyword_filter": 0,
                "unread_only_requested": unread_only,
            }
            try:
                mail.logout()
            except Exception:
                pass
            return json.dumps(result, ensure_ascii=False, indent=2)

        # Выбор папки (всегда INBOX)
        if debug:
            print(f"Выбор папки: {DEFAULT_FOLDER}")
        status, messages = mail.select(DEFAULT_FOLDER)
        if status != 'OK':
            error_details = ""
            if messages and isinstance(messages, list) and messages[0]:
                try:
                    error_details = messages[0].decode('utf-8', errors='ignore')
                    if b'[NONEXISTENT]' in messages[0] or b'NONEXISTENT' in messages[0]:
                        error_details = "Указанная папка не существует или недоступна."
                    else:
                        error_details = f"Сервер ответил: {error_details}"
                except Exception:
                    error_details = "Неизвестная ошибка при выборе папки."

            result = {
                "status": "error",
                "message": (f"Не удалось выбрать папку '{DEFAULT_FOLDER}'. Причина: {error_details} Возможно, IMAP-сервер недоступен или настроен необычным образом."),
                "emails_count": 0,
                "period_requested": period_requested_formatted,
                "keywords_requested": keywords,
                "emails_skipped_by_date_filter": 0,
                "emails_skipped_by_keyword_filter": 0,
                "unread_only_requested": unread_only,
            }
            try:
                mail.logout()
            except Exception:
                pass
            return json.dumps(result, ensure_ascii=False, indent=2)

        # Поиск писем (по дате или все)
        list_email_ids = []
        search_criteria_list = []

        if period and start_dt and end_dt:
            search_criteria_list.append('SENTSINCE')
            search_criteria_list.append(start_dt.strftime("%d-%b-%Y"))
            search_criteria_list.append('SENTBEFORE')
            search_criteria_list.append((end_dt + timedelta(days=1)).strftime("%d-%b-%Y"))
        if unread_only:
            search_criteria_list.append('UNSEEN')

        if debug:
            original_mail_debug_level = mail.debug
            mail.debug = 0

        if search_criteria_list:
            if debug:
                print(f"Поиск писем на сервере по дате: {' '.join(search_criteria_list)}")
            status, email_ids_response = mail.search(None, *search_criteria_list)
        else:
            if debug:
                print("Поиск всех писем на сервере (без критериев даты).")
            status, email_ids_response = mail.search(None, 'ALL')

        if debug:
            mail.debug = original_mail_debug_level

        if status != 'OK':
            raise Exception(f"Не удалось найти письма на сервере: {email_ids_response}")

        list_email_ids = email_ids_response[0].split()

        if debug:
            print(f"Найдено писем на сервере (до локальной фильтрации): {len(list_email_ids)}")
            if len(list_email_ids) > 10:
                first_uids = [uid.decode() for uid in list_email_ids[:5]]
                last_uids = [uid.decode() for uid in list_email_ids[-5:]]
                print(f"    UIDs, полученные от сервера: {', '.join(first_uids)} ... {', '.join(last_uids)}")
            elif list_email_ids:
                all_uids = [uid.decode() for uid in list_email_ids]
                print(f"    UIDs, полученные от сервера: {', '.join(all_uids)}")
            else:
                print("    UIDs, полученные от сервера: Нет (список пуст).")

        # Применение ограничения last_n_emails
        if not period and not keywords:
            if len(list_email_ids) > applied_last_n_emails:
                if not final_message_warning:
                    final_message_warning = (f"На сервере обнаружено {len(list_email_ids)} писем. Получено {applied_last_n_emails} последних письма в соответствии с параметром 'last_n_emails'.")
            list_email_ids = list_email_ids[-applied_last_n_emails:]
            if debug:
                print(f"После применения 'last_n_emails': {len(list_email_ids)} писем для обработки.")

        # Ограничение max_uids_to_fetch
        if len(list_email_ids) > max_uids_to_fetch:
            if not final_message_warning:
                final_message_warning = (f"Обнаружено {len(list_email_ids)} писем, что превышает установленный лимит ({max_uids_to_fetch}) для обработки. Обработаны только {max_uids_to_fetch} последних писем.")
            list_email_ids = list_email_ids[-max_uids_to_fetch:]

        if not list_email_ids:
            message_info = "Непрочитанные письма отсутствуют в папке" if unread_only else "Письма отсутствуют в папке"
            if period:
                message_info += " за указанный период"
            if keywords:
                message_info += " по указанным ключевым словам"
            result = {
                "status": "ok",
                "message": message_info,
                "emails_count": 0,
                "period_requested": period_requested_formatted,
                "keywords_requested": keywords,
                "emails_skipped_by_date_filter": 0,
                "emails_skipped_by_keyword_filter": 0,
                "unread_only_requested": unread_only,
            }
            try:
                mail.logout()
            except Exception:
                pass
            return json.dumps(result, ensure_ascii=False, indent=2)

        # Обработка найденных UID
        processed_emails_count_for_debug = 0
        processed_uids = []

        for uid_bytes in list_email_ids:
            processed_emails_count_for_debug += 1

            if debug and processed_emails_count_for_debug > max_debug_output_emails:
                if mail.debug != 0:
                    mail.debug = 0
                    if debug:
                        print(f"ℹ️ Детальный отладочный вывод IMAPlib подавлен после {max_debug_output_emails} писем.")

            status, msg_data = mail.fetch(uid_bytes, '(RFC822)')
            if status != 'OK':
                original_mail_debug = mail.debug
                mail.debug = 4 if debug else 0
                print(f"❌ Ошибка при получении письма с UID {uid_bytes.decode()}: {msg_data}")
                mail.debug = original_mail_debug
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Локальная фильтрация по дате
            if period and (start_dt and end_dt):
                try:
                    email_date_obj = parsedate_to_datetime(msg['Date'])
                    if not (start_dt.date() <= email_date_obj.date() <= end_dt.date()):
                        skipped_emails_by_date_filter += 1
                        if debug and processed_emails_count_for_debug <= max_debug_output_emails:
                            print(f"    [UID {uid_bytes.decode()}] Пропуск: не соответствует диапазону дат (локальная фильтрация).")
                        continue
                except Exception as date_parse_error:
                    if debug and processed_emails_count_for_debug <= max_debug_output_emails:
                        print(f"    [UID {uid_bytes.decode()}] Предупреждение: Не удалось разобрать дату ({msg.get('Date', 'N/A')}): {date_parse_error}. Письмо будет обработано.")
                    pass

            # Извлечение тела письма
            email_body = ""
            html_body_content = ""

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))
                    if ctype == 'text/plain' and 'attachment' not in cdispo:
                        try:
                            email_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                            break
                        except (UnicodeDecodeError, LookupError):
                            email_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            break
                    elif ctype == 'text/html' and 'attachment' not in cdispo:
                        try:
                            html_body_content = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                        except (UnicodeDecodeError, LookupError):
                            html_body_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            else:
                ctype = msg.get_content_type()
                if ctype == 'text/plain':
                    try:
                        email_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='ignore')
                    except (UnicodeDecodeError, LookupError):
                        email_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                elif ctype == 'text/html':
                    try:
                        html_body_content = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='ignore')
                    except (UnicodeDecodeError, LookupError):
                        html_body_content = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

            if not email_body and html_body_content:
                email_body = _strip_html_tags(html_body_content)

            email_body = _clean_text_body(email_body)

            # Локальная фильтрация по ключевым словам (логика И)
            matched_keywords_for_current_email = []
            if keywords:
                found_all_keywords = True
                # Декодируем Subject для поиска ключевых слов
                decoded_subject = ""
                if msg['Subject']:
                    try:
                        decoded_subject = str(make_header(decode_header(msg['Subject'])))
                    except Exception:
                        decoded_subject = str(msg['Subject'])
                full_text_content = decoded_subject + " " + email_body
                for keyword in keywords:
                    if keyword.lower() in full_text_content.lower():
                        matched_keywords_for_current_email.append(keyword)
                    else:
                        found_all_keywords = False
                        break

                if keywords and not found_all_keywords:
                    skipped_emails_by_keyword_filter += 1
                    if debug and processed_emails_count_for_debug <= max_debug_output_emails:
                        print(f"    [UID {uid_bytes.decode()}] Пропуск: не все ключевые слова найдены (локальная фильтрация).")
                    continue

            # Декодируем тему письма
            if msg['Subject']:
                try:
                    subject = str(make_header(decode_header(msg['Subject'])))
                except Exception:
                    subject = msg['Subject']
            else:
                subject = ""

            # Декодируем From и извлекаем email через parseaddr
            sender_header = msg.get('From', '')
            if sender_header:
                try:
                    decoded_from = str(make_header(decode_header(sender_header)))
                except Exception:
                    decoded_from = sender_header
            else:
                decoded_from = "Unknown Sender"

            from_name, from_email = parseaddr(decoded_from)
            # Если parseaddr не нашёл email, пробуем простую регекспроверку как запасной вариант
            if not from_email and decoded_from and '@' in decoded_from:
                m = re.search(r'[\w\.-]+@[\w\.-]+', decoded_from)
                if m:
                    from_email = m.group(0)
                else:
                    from_email = decoded_from

            date = msg['Date']

            email_entry = {
                "uid": uid_bytes.decode(),
                "from": decoded_from,
                "from_name": from_name,
                "from_email": from_email,
                "subject": subject,
                "date": date,
                "body": email_body
            }
            if keywords:
                email_entry["matched_keywords"] = matched_keywords_for_current_email

            emails_data.append(email_entry)
            processed_uids.append(uid_bytes)

            if debug and processed_emails_count_for_debug <= max_debug_output_emails:
                print(f"--- Письмо UID: {uid_bytes.decode()} (OK) ---")
                print(f"От: {decoded_from}")
                print(f"Тема: {subject}")
                print(f"Дата: {date}")
                print(f"Тело (часть): {email_body[:200]}...")
                if keywords:
                    print(f"Найденные ключевые слова: {matched_keywords_for_current_email}")
                print("---------------------")

        # Выход из почтового ящика
        try:
            mail.logout()
        except Exception:
            pass

        # Восстановление mail.debug для финального вывода, если он был подавлен
        if debug and mail.debug == 0:
            mail.debug = 4

        # Формирование финального сообщения
        final_message = "Письма успешно получены."
        if final_message_warning:
            final_message = final_message_warning

        if skipped_emails_by_date_filter > 0:
            final_message += f" Пропущено {skipped_emails_by_date_filter} писем локальной фильтрацией по дате."
        if skipped_emails_by_keyword_filter > 0:
            final_message += f" Пропущено {skipped_emails_by_keyword_filter} писем локальной фильтрацией по ключевым словам."

        result = {
            "status": "ok",
            "message": final_message,
            "emails_count": len(emails_data),
            "period_requested": period_requested_formatted,
            "keywords_requested": keywords,
            "emails_skipped_by_date_filter": skipped_emails_by_date_filter,
            "emails_skipped_by_keyword_filter": skipped_emails_by_keyword_filter,
            "unread_only_requested": unread_only,
            "emails": emails_data
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        # Универсальная обработка ошибок с "человеческим" объяснением
        print(f"❌ Ошибка получения: {str(e)}")
        error_msg = str(e)
        if "AUTHENTICATIONFAILED" in error_msg.upper():
            error_msg = "Неверный логин или пароль. Убедитесь, что используется пароль приложения, если это требуется почтовым сервисом."
        elif "connection timed out" in error_msg.lower():
            error_msg = "Время ожидания соединения истекло. Проверьте подключение к интернету или настройки хоста/порта."
        elif "name or service not known" in error_msg.lower() or "nodename nor servname provided" in error_msg.lower():
            error_msg = "Неизвестный хост. Проверьте правильность адреса IMAP-сервера."
        elif "could not parse command" in error_msg.lower():
            error_msg = f"Ошибка при выполнении команды поиска на сервере: {error_msg}. Возможно, сервер не поддерживает запрошенные критерии поиска или формат запроса."

        result = {
            "status": "error",
            "message": f"Ошибка получения: {error_msg}",
            "emails_count": 0,
            "period_requested": period_requested_formatted,
            "keywords_requested": arguments.get('keywords', []),
            "emails_skipped_by_date_filter": skipped_emails_by_date_filter,
            "emails_skipped_by_keyword_filter": skipped_emails_by_keyword_filter,
            "unread_only_requested": arguments.get('unread_only', False),
        }
        try:
            if 'mail' in locals() and getattr(mail, 'state', None) == 'SELECTED':
                mail.logout()
        except Exception:
            pass
        return json.dumps(result, ensure_ascii=False, indent=2)
