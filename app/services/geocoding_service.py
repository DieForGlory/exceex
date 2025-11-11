# app/services/geocoding_service.py
import csv
import os
import re
from threading import Lock
import numpy as np
from scipy.spatial import cKDTree
from thefuzz import process as fuzz_process
from flask import current_app

from app.utils.helpers import find_column_indices


def _normalize_address_string(s):
    """
    Удаляет из строки все знаки препинания, пробелы и приводит к нижнему регистру.
    """
    if not isinstance(s, str):
        return ""
    return re.sub(r'[\W_]+', '', s).lower()


class LocalAddressService:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        # Реализуем Singleton, чтобы kdtree и словари загружались один раз
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LocalAddressService, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            # Данные для поиска "Адрес -> Координаты"
            self.normalized_address_to_coords = {}
            self.address_choices = {}

            # Данные для поиска "Координаты -> Адрес"
            self.kdtree = None
            self.kdtree_data = []

            self._initialized = True
            # Загрузка данных будет вызвана при первом обращении,
            # когда будет доступен current_app
            self._data_loaded = False

    def _load_data(self):
        """Ленивая загрузка данных, требующая контекста приложения."""
        if self._data_loaded:
            return

        with self._lock:
            if self._data_loaded:
                return

            csv_file_path = current_app.config['ADDRESS_CSV_FILE']
            if not os.path.exists(csv_file_path):
                current_app.logger.warning(f"Внимание: Файл с адресами не найден: {csv_file_path}")
                self._data_loaded = True  # Считаем "загруженным", чтобы не пытаться снова
                return

            points = []
            try:
                with open(csv_file_path, mode='r', encoding='utf-8') as infile:
                    reader = csv.reader(infile)
                    for row in reader:
                        if len(row) == 3:
                            address, lat_str, lon_str = row
                            try:
                                original_address = address.strip()
                                normalized_addr = _normalize_address_string(original_address)
                                lat, lon = float(lat_str), float(lon_str)

                                self.normalized_address_to_coords[normalized_addr] = (lat_str.strip(), lon_str.strip())
                                self.address_choices[normalized_addr] = original_address

                                points.append((lat, lon))
                                self.kdtree_data.append(original_address)
                            except (ValueError, TypeError):
                                continue
                if points:
                    self.kdtree = cKDTree(np.array(points))

                self._data_loaded = True
                current_app.logger.info(f"Служба геокодинга успешно загрузила {len(points)} адресов.")

            except Exception as e:
                current_app.logger.error(f"Ошибка при загрузке файла с адресами: {e}")

    def get_coords(self, address):
        """Ищет координаты по адресу."""
        self._load_data()  # Гарантируем, что данные загружены
        if not address: return None, None

        normalized_query = _normalize_address_string(address)
        exact_match = self.normalized_address_to_coords.get(normalized_query)
        if exact_match:
            return exact_match

        if not self.address_choices: return None, None

        best_match_normalized, score = fuzz_process.extractOne(normalized_query, self.address_choices.keys())
        if score > 85:
            return self.normalized_address_to_coords.get(best_match_normalized)

        return None, None

    def get_address(self, lat, lon):
        """Ищет ближайший адрес по координатам."""
        self._load_data()  # Гарантируем, что данные загружены
        if self.kdtree is None: return None
        if lat is None or lon is None: return None
        try:
            distance, index = self.kdtree.query(np.array([float(lat), float(lon)]))
            return self.kdtree_data[index]
        except (ValueError, TypeError):
            return None


# --- Глобальный экземпляр Singleton ---
address_service = LocalAddressService()


# --- Функции, которые будут вызываться из других модулей ---
def get_coordinates(address):
    return address_service.get_coords(address)


def get_address_by_coords(lat, lon):
    return address_service.get_address(lat, lon)


def apply_post_processing(task_id, workbook, start_row, function_name, task_statuses):
    """
    Применяет функции пост-обработки (геокодинга).
    """
    if function_name not in ['address_to_coords', 'coords_to_address']:
        current_app.logger.info(f"[{task_id}] Пост-обработка не требуется (function_name: {function_name}).")
        return

    ROUNDING_PRECISION = 4
    worksheet = workbook.active
    cols = find_column_indices(worksheet, start_row, {'lat': 'Широта', 'lon': 'Долгота', 'addr': 'Адрес'})

    if not all(k in cols for k in ['lat', 'lon', 'addr']):
        msg = "Ошибка: не найдены все обязательные колонки ('Широта', 'Долгота', 'Адрес'). Геокодинг пропущен."
        current_app.logger.error(f"[{task_id}] {msg}")
        task_statuses[task_id]['status'] = msg
        return

    rows_processed = 0
    total_rows = worksheet.max_row - start_row

    if function_name == 'address_to_coords':
        current_app.logger.info(f"[{task_id}] Запущен геокодинг 'Адрес -> Координаты'.")
        for i, row_cells in enumerate(worksheet.iter_rows(min_row=start_row + 1, max_row=worksheet.max_row)):
            address_cell = row_cells[cols['addr'] - 1]
            address_value = address_cell.value

            if address_value and isinstance(address_value, str):
                lat, lon = get_coordinates(address_value)
                if lat and lon:
                    try:
                        rounded_lat = round(float(lat), ROUNDING_PRECISION)
                        rounded_lon = round(float(lon), ROUNDING_PRECISION)

                        worksheet.cell(row=start_row + 1 + i, column=cols['lat']).value = rounded_lat
                        worksheet.cell(row=start_row + 1 + i, column=cols['lon']).value = rounded_lon
                        rows_processed += 1
                    except ValueError:
                        current_app.logger.warning(f"[{task_id}] Не удалось записать lat/lon: {lat}, {lon}")

            if (i + 1) % 100 == 0:
                print(f'Геокодинг: обработано {i + 1}/{total_rows} строк...')
                pass

    elif function_name == 'coords_to_address':
        current_app.logger.info(f"[{task_id}] Запущен геокодинг 'Координаты -> Адрес'.")
        # (Логика не была реализована в исходном файле, оставлено пустым)
        pass

    msg = f"Геокодинг '{function_name}' завершен: {rows_processed} записей."
    current_app.logger.info(f"[{task_id}] {msg}")
    task_statuses[task_id]['status'] = msg