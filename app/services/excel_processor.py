# app/services/excel_processor.py
import io
import re
import traceback
from collections import defaultdict
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from asteval import Interpreter  # <-- 1. ИМПОРТИРУЕМ ASTEVAL

# Импорт сервисов из приложения
from app.services.geocoding_service import apply_post_processing
from app.utils.helpers import get_col_from_cell
from app.services import logging_service
from app.extensions import socketio, task_statuses, db
from app import create_app

# --- НОВЫЙ ВЫЧИСЛИТЕЛЬ ФОРМУЛ ---

# Создаем один, безопасный экземпляр Interpreter.
# Он не имеет доступа к файловой системе или сети.
_aeval = Interpreter()


def _evaluate_formula(formula_str, source_row_idx, source_ws):
    """
    Вычисляет сложную формулу (e.g., =K{row}*3600/M{row} + A4)
    используя безопасный asteval.
    """
    if not isinstance(formula_str, str) or not formula_str.startswith('='):
        return formula_str

    expression = formula_str[1:].strip()

    try:
        # 1. Находим все возможные ссылки на ячейки
        # Этот regex находит: K{row}, A4, B5{row}, K4{row} и т.д.
        # Мы используем set(), чтобы обработать каждую ссылку (н-р, 'A4')
        # только один раз, даже если она встречается в формуле дважды (=A4+A4)
        variables = set(re.findall(r'([A-Z]+\d*\{row\}?\d*)', expression, re.IGNORECASE))

        # 2. Заменяем каждую ссылку (переменную) на ее реальное значение
        for var in variables:
            # Форматируем ссылку, вставляя номер строки
            # 'K4{row}' -> 'K415'
            # 'K{row}' -> 'K15'
            # 'A4' -> 'A4'
            cell_ref = var.format(row=source_row_idx)

            try:
                cell_value = source_ws[cell_ref].value
                # Пытаемся получить число
                numeric_value = float(cell_value)

                # Заменяем в строке выражения
                # (используем re.sub для замены без учета регистра)
                expression = re.sub(r'(?i)' + re.escape(var), str(numeric_value), expression)

            except (ValueError, TypeError, AttributeError, TypeError):
                # Если в ячейке не-число (текст или пусто),
                # считаем это ошибкой вычисления
                print(f"Ошибка в _evaluate_formula: Не удалось получить число из {cell_ref} (значение: '{cell_value}')")
                return f'#VALUE! (ссылка: {cell_ref})'

        # 3. Вычисляем готовую строку (e.g., "10.5*3600/12.0 + 5.0")
        _aeval.eval(expression)

        if _aeval.error:
            # Если asteval вернул ошибку (e.g., деление на 0)
            error_msg = _aeval.error_msg
            _aeval.error = None  # Сбрасываем ошибку для следующего вызова
            print(f"Ошибка asteval: {error_msg}")
            return '#NUM!'

        return _aeval.result

    except Exception as e:
        print(f"Критическая ошибка в _evaluate_formula: {e}")
        return '#ERROR!'


# --- СТАРАЯ ФУНКЦИЯ _parse_operand БОЛЬШЕ НЕ НУЖНА ---
# (def _parse_operand... УДАЛЕНА)
# ---------------------------------------------------

# --- Функции парсинга (без изменений) ---

def get_sheet_settings_map(sheet_settings):
    settings_map = {}
    for setting in sheet_settings:
        sheet_name = setting.get('sheet_name')
        start_cell = setting.get('start_cell')
        if sheet_name and start_cell:
            start_row = int("".join(filter(str.isdigit, start_cell)))
            settings_map[sheet_name] = start_row
    return settings_map


# --- Функции применения правил (без изменений) ---

def _apply_static_value_rules(template_wb, static_value_rules, t_start_row, task_id):
    if not static_value_rules:
        return
    rules_by_sheet = defaultdict(list)
    for rule in static_value_rules:
        rules_by_sheet[rule.get('target_sheet', template_wb.sheetnames[0])].append(rule)

    for sheet_name, sheet_rules in rules_by_sheet.items():
        try:
            ws = template_wb[sheet_name]
            max_row = ws.max_row
            if max_row < t_start_row + 1: continue
            for rule in sheet_rules:
                t_col_idx = column_index_from_string(rule['target_col'])
                value_to_insert = rule['value']
                for row_idx in range(t_start_row + 1, max_row + 1):
                    ws.cell(row=row_idx, column=t_col_idx).value = value_to_insert
        except KeyError:
            print(f"[{task_id}] ВНИМАНИЕ: Лист '{sheet_name}' для статичного значения не найден.")
        except Exception as e:
            print(f"[{task_id}] ОШИБКА: Ошибка применения статичного значения: {e}")


def _apply_formula_rules(source_wb, template_wb, formula_rules, sheet_settings_map, t_start_row, task_id):
    """
    Эта функция теперь вызывает НОВЫЙ _evaluate_formula,
    но сама она не меняется.
    """
    if not formula_rules: return
    rules_by_target_sheet = defaultdict(list)
    for rule in formula_rules:
        rules_by_target_sheet[rule.get('target_sheet', template_wb.sheetnames[0])].append(rule)

    for target_sheet_name, sheet_rules in rules_by_target_sheet.items():
        try:
            template_ws = template_wb[target_sheet_name]
            max_row = template_ws.max_row
            if max_row < t_start_row + 1: continue
            for t_row_idx in range(t_start_row + 1, max_row + 1):
                for rule in sheet_rules:
                    source_sheet_name = rule['source_sheet']
                    s_start_row = sheet_settings_map.get(source_sheet_name)
                    if s_start_row is None: continue
                    source_ws = source_wb[source_sheet_name]
                    source_row_idx = s_start_row + (t_row_idx - (t_start_row + 1))
                    formula_template = rule['formula']
                    t_col_idx = column_index_from_string(rule['target_col'])

                    # --- ВЫЗОВ НОВОЙ ФУНКЦИИ ---
                    calculated_value = _evaluate_formula(formula_template, source_row_idx, source_ws)
                    template_ws.cell(row=t_row_idx, column=t_col_idx).value = calculated_value

        except KeyError as e:
            print(f"[{task_id}] ВНИМАНИЕ: Лист '{e.args[0]}' не найден при обработке формул.")
        except Exception as e:
            print(f"[{task_id}] ОШИБКА: Ошибка применения формулы: {e}")


def _apply_cell_mappings(source_wb, template_ws, cell_mappings, task_id):
    if not cell_mappings:
        return
    mappings_by_sheet = defaultdict(list)
    for mapping in cell_mappings:
        sheet_name = mapping.get('source_sheet', source_wb.sheetnames[0])
        mappings_by_sheet[sheet_name].append(mapping)

    for sheet_name, sheet_mappings in mappings_by_sheet.items():
        try:
            source_ws = source_wb[sheet_name]
        except KeyError:
            print(f"[{task_id}] ВНИМАНИЕ: Лист '{sheet_name}' для копирования ячеек не найден.")
            continue
        for mapping in sheet_mappings:
            try:
                source_cell = source_ws[mapping['source_cell']]
                dest_cell = template_ws[mapping['dest_cell']]
                dest_cell.value = source_cell.value
                if source_cell.hyperlink:
                    dest_cell.hyperlink = source_cell.hyperlink.target
                    dest_cell.style = "Hyperlink"
            except Exception as e:
                print(
                    f"[{task_id}] ОШИБКА: Ошибка при копировании ячейки {mapping['source_cell']} -> {mapping['dest_cell']}: {e}")


def _apply_source_cell_fill_rules(source_wb, template_wb, source_cell_fill_rules, t_start_row, task_id):
    if not source_cell_fill_rules:
        return
    rules_by_source_sheet = defaultdict(list)
    for rule in source_cell_fill_rules:
        rules_by_source_sheet[rule.get('source_sheet', source_wb.sheetnames[0])].append(rule)

    for source_sheet_name, sheet_rules in rules_by_source_sheet.items():
        try:
            source_ws = source_wb[source_sheet_name]
        except KeyError:
            print(
                f"[{task_id}] ВНИМАНИЕ: Лист источника '{source_sheet_name}' для правила 'Заполнение из ячейки' не найден.")
            continue

        for rule in sheet_rules:
            try:
                source_cell_coord = rule['source_cell']
                value_to_insert = source_ws[source_cell_coord].value
                target_sheet_name = rule.get('target_sheet', template_wb.sheetnames[0])
                target_col = rule['target_col']
                template_ws = template_wb[target_sheet_name]
                t_col_idx = column_index_from_string(target_col)
                max_row = template_ws.max_row
                if max_row < t_start_row + 1: continue
                for row_idx in range(t_start_row + 1, max_row + 1):
                    template_ws.cell(row=row_idx, column=t_col_idx).value = value_to_insert
            except KeyError:
                print(
                    f"[{task_id}] ОШИБКА: Не найдена ячейка '{source_cell_coord}' (источник) или лист '{target_sheet_name}' (шаблон).")
            except Exception as e:
                print(f"[{task_id}] ОШИБКА: Ошибка применения правила 'Заполнение из ячейки': {e}")


def _apply_manual_rules(source_ws, template_ws, rules, s_start_row, t_start_row, used_source_cols, used_template_cols,
                        visible_rows_only, task_id):
    s_end_row = source_ws.max_row
    for rule in rules:
        s_col_letter = rule.get('s_col') or get_col_from_cell(rule.get('source_cell'))
        t_col_letter = rule.get('t_col') or rule.get('template_col')
        if not s_col_letter or not t_col_letter:
            continue
        s_col_idx, t_col_idx = column_index_from_string(s_col_letter), column_index_from_string(t_col_letter)
        if s_col_idx in used_source_cols or t_col_idx in used_template_cols:
            print(f"[{task_id}] DEBUG: ПРАВИЛО ПРОПУЩЕНО: Колонка {s_col_letter} или {t_col_letter} уже используется.")
            continue
        target_row_counter = 0
        for r_idx in range(s_start_row + 1, s_end_row + 1):
            if visible_rows_only and source_ws.row_dimensions[r_idx].hidden:
                continue
            source_cell = source_ws.cell(row=r_idx, column=s_col_idx)
            target_cell = template_ws.cell(row=t_start_row + 1 + target_row_counter, column=t_col_idx)
            target_cell.value = source_cell.value
            if source_cell.hyperlink:
                target_cell.hyperlink = source_cell.hyperlink.target
                target_cell.style = "Hyperlink"
            target_row_counter += 1
        used_source_cols.add(s_col_idx)
        used_template_cols.add(t_col_idx)


# --- Функция SocketIO (без изменений) ---

def _emit_status(task_id, status, progress, is_complete=False, result_ready=False):
    payload = {
        'task_id': task_id,
        'status': status,
        'progress': progress,
        'result_ready': result_ready
    }
    event = 'task_complete' if is_complete else 'status_update'
    socketio.emit(event, payload, room=task_id)


# --- Основная функция (без изменений) ---

def process_excel_hybrid(task_id, source_file_obj, template_file_obj,
                         ranges, sheet_settings, template_rules, post_function,
                         original_template_filename, task_statuses, cell_mappings=None,
                         formula_rules=None, static_value_rules=None, visible_rows_only=False,
                         source_cell_fill_rules=None):
    owner_id = task_statuses.get(task_id, {}).get('owner_id')
    final_status = "Неизвестная ошибка"

    app = create_app()
    context = app.app_context()
    context.push()

    try:
        _emit_status(task_id, 'Подготовка...', 5)

        source_wb = load_workbook(filename=source_file_obj, data_only=True)
        is_macro_enabled = original_template_filename.lower().endswith('.xlsm')
        template_wb = load_workbook(filename=template_file_obj, keep_vba=is_macro_enabled)
        template_ws = template_wb.active

        sheet_settings_map = get_sheet_settings_map(sheet_settings)
        t_start_row = ranges.get('t_start_row', 1)
        used_template_cols = set()
        used_source_cols_by_sheet = defaultdict(set)

        # 1. Точечное копирование ячеек
        _emit_status(task_id, 'Копирую отдельные ячейки...', 10)
        _apply_cell_mappings(source_wb, template_ws, cell_mappings, task_id)

        # 1.5. Заполнение столбцов из ячейки
        _emit_status(task_id, 'Заполняю столбцы из ячеек...', 15)
        _apply_source_cell_fill_rules(source_wb, template_wb, source_cell_fill_rules, t_start_row, task_id)

        # 2. Копирование колонок (цикл по листам источника)
        _emit_status(task_id, 'Применяю правила...', 20)
        for sheet_name in source_wb.sheetnames:
            try:
                source_ws = source_wb[sheet_name]
                s_start_row = sheet_settings_map.get(sheet_name, 1)
                used_source_cols = used_source_cols_by_sheet[sheet_name]
                current_template_rules = [r for r in template_rules if
                                          r.get('source_sheet', source_wb.sheetnames[0]) == sheet_name]
                _apply_manual_rules(source_ws, template_ws, current_template_rules, s_start_row, t_start_row,
                                    used_source_cols,
                                    used_template_cols, visible_rows_only, task_id)
            except Exception as e:
                print(f"[{task_id}] ОШИБКА: Ошибка при обработке ручных правил для листа '{sheet_name}': {e}")

        # 3. Заполнение статичных значений
        _emit_status(task_id, 'Заполняю статичные значения...', 70)
        _apply_static_value_rules(template_wb, static_value_rules, t_start_row, task_id)

        # 4. Вычисление и вставка результатов формул
        _emit_status(task_id, 'Вычисляю формулы...', 80)
        _apply_formula_rules(source_wb, template_wb, formula_rules, sheet_settings_map, t_start_row, task_id)

        # 5. Финальная пост-обработка (например, геокодинг)
        _emit_status(task_id, 'Пост-обработка...', 90)
        apply_post_processing(task_id, template_wb, t_start_row, post_function, task_statuses)

        # 6. Сохранение результата
        _emit_status(task_id, 'Сохраняю результат...', 95)
        processed_file_obj = io.BytesIO()
        template_wb.save(processed_file_obj)
        processed_file_obj.seek(0)
        source_wb.close()
        template_wb.close()

        # 7. Логгирование и обновление статуса (УСПЕХ)
        final_status = 'Готово!'
        logging_service.log_task(
            task_id, owner_id, final_status, original_template_filename
        )
        task_statuses[task_id].update({
            'status': final_status,
            'result_file': processed_file_obj,
            'template_filename': original_template_filename
        })
        _emit_status(task_id, final_status, 100, is_complete=True, result_ready=True)

    except Exception as e:
        # 8. Логгирование и обновление статуса (ОШИБКА)
        print(f"[{task_id}] КРИТИЧЕСКАЯ ОШИБКА в фоновом потоке: {e}")
        traceback.print_exc()

        final_status = f"Ошибка: {e}"
        logging_service.log_task(
            task_id, owner_id, final_status, original_template_filename
        )
        task_statuses[task_id].update({
            'status': final_status,
            'result_file': None
        })
        _emit_status(task_id, final_status, 100, is_complete=True, result_ready=False)

    finally:
        context.pop()
        if task_id in task_statuses:
            task_data = task_statuses[task_id]
            task_statuses[task_id] = {
                'result_file': task_data.get('result_file'),
                'template_filename': task_data.get('template_filename'),
                'owner_id': task_data.get('owner_id')
            }