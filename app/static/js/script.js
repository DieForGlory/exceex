// static/js/script.js

document.addEventListener('DOMContentLoaded', function() {

    // --- Инициализация Socket.IO ---
    var socket = null;
    try {
        socket = io();
        console.log('Socket.IO подключен.');
    } catch (e) {
        console.error('Не удалось подключиться к Socket.IO', e);
    }

    // --- НОВЫЕ СЛУШАТЕЛИ SOCKET.IO ---

    if (socket) {
        // 1. Слушатель для промежуточных обновлений статуса
        socket.on('status_update', function(data) {
            console.log('Socket event (status_update):', data);
            updateProgress(data.status, data.progress);
        });

        // 2. Слушатель для финального события (успех или ошибка)
        socket.on('task_complete', function(data) {
            console.log('Socket event (task_complete):', data);
            updateProgress(data.status, 100);

            // --- ОБРАБОТКА ПРЕДУПРЕЖДЕНИЙ ---
            if (data.warnings && data.warnings.length > 0) {
                const warningContainer = document.getElementById('warning-container');
                const warningList = document.getElementById('warning-list');

                if (warningContainer && warningList) {
                    warningList.innerHTML = ''; // Очищаем старые

                    const maxWarningsToShow = 50;
                    data.warnings.slice(0, maxWarningsToShow).forEach(msg => {
                        const li = document.createElement('li');
                        li.textContent = msg;
                        warningList.appendChild(li);
                    });

                    if (data.warnings.length > maxWarningsToShow) {
                         const li = document.createElement('li');
                         li.style.fontWeight = 'bold';
                         li.textContent = `... и еще ${data.warnings.length - maxWarningsToShow} замечаний.`;
                         warningList.appendChild(li);
                    }

                    warningContainer.style.display = 'block';
                }
            }
            // --- КОНЕЦ ОБРАБОТКИ ПРЕДУПРЕЖДЕНИЙ ---


            if (data.result_ready) {
                // Успех
                const downloadLink = document.getElementById('download-link');
                downloadLink.href = `/download/${data.task_id}`;
                downloadLink.style.display = 'inline-block';
                document.getElementById('status-text').textContent = 'Готово! Ваш файл можно скачать.';
            } else if (data.status && data.status.startsWith('Ошибка')) {
                // Ошибка
                const statusBar = document.getElementById('progress-bar');
                if(statusBar) statusBar.style.backgroundColor = 'var(--error-color)';
            }
        });
    }


    // --- Общая функция обновления UI Прогресс-бара ---
    function updateProgress(status, progress) {
        const statusBar = document.getElementById('progress-bar');
        const statusText = document.getElementById('status-text');

        if (statusBar && statusText) {
            statusText.textContent = status || 'Обработка...';
            const progressVal = progress || 0;
            statusBar.style.width = `${progressVal}%`;
            statusBar.textContent = `${progressVal}%`;
        }
    }


    // --- Логика для главной страницы (index.html) ---
    const form = document.getElementById('process-form');
    const savedTemplateSelect = document.getElementById('saved_template');
    const newTemplateFields = document.getElementById('new-template-fields');

    // Показываем/скрываем поля для ручной настройки
    if (savedTemplateSelect) {
        savedTemplateSelect.addEventListener('change', function() {
            newTemplateFields.style.display = this.value ? 'none' : 'block';
        });
        // Проверяем состояние при загрузке страницы
        newTemplateFields.style.display = savedTemplateSelect.value ? 'none' : 'block';
    }

    // Обработка отправки главной формы (ЗАПУСК ПАРСИНГА)
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(form);
            const errorContainer = document.getElementById('error-messages');
            const progressContainer = document.getElementById('progress-container');
            const downloadLink = document.getElementById('download-link');

            // Находим и сбрасываем контейнер ошибок
            const warningContainer = document.getElementById('warning-container');
            const warningList = document.getElementById('warning-list');


            // Сбрасываем UI перед новым запуском
            errorContainer.style.display = 'none';
            progressContainer.style.display = 'block';
            downloadLink.style.display = 'none';

            // Сбрасываем UI ошибок
            if (warningContainer && warningList) {
                warningContainer.style.display = 'none';
                warningList.innerHTML = '';
            }


            // Сброс прогресс-бара
            const statusBar = document.getElementById('progress-bar');
            if (statusBar) {
                statusBar.style.width = `0%`;
                statusBar.textContent = `0%`;
                statusBar.style.backgroundColor = 'var(--success-color)';
            }
            updateProgress('Загрузка файлов на сервер...', 0);

            // Отправляем файлы на /process
            fetch(form.action, { method: 'POST', body: formData })
                .then(response => response.json())
                .then(data => {
                    if (data.error) { throw new Error(data.error); }

                    if (socket && data.task_id) {
                        console.log('Подписка на комнату:', data.task_id);
                        socket.emit('join_task_room', {'task_id': data.task_id});
                    } else {
                        throw new Error('Не удалось подключиться к WebSocket для отслеживания задачи.');
                    }
                })
                .catch(error => {
                    progressContainer.style.display = 'none';
                    errorContainer.textContent = `Произошла ошибка: ${error.message}`;
                    errorContainer.style.display = 'block';
                });
        });
    }

    // --- Логика для страниц создания/редактирования шаблонов ---

    // Кнопка для НАСТРОЕК ЛИСТОВ
    document.getElementById('add-sheet-setting')?.addEventListener('click', function() {
        const container = document.getElementById('sheet-settings-container');
        const ruleRow = document.createElement('div');
        ruleRow.className = 'rule-row';
        ruleRow.innerHTML = `
            <div class="rule-input-group">
                <label>Имя листа в источнике</label>
                <input type="text" name="setting_sheet_name" placeholder="Лист1" required>
            </div>
            <div class="rule-input-group">
                <label>Начальная ячейка заголовков</label>
                <input type="text" name="setting_start_cell" placeholder="A5" required>
            </div>
            <button type="button" class="btn btn-danger btn-sm remove-rule-btn" style="align-self: center; margin-top: 1rem;">Удалить</button>`;
        container.appendChild(ruleRow);
    });

    // Кнопка для правил ЯЧЕЕК
    document.getElementById('add-cell-mapping')?.addEventListener('click', function() {
        const container = document.getElementById('cell-mappings-container');
        const ruleRow = document.createElement('div');
        ruleRow.className = 'rule-row';
        ruleRow.innerHTML = `
            <div class="rule-input-group"><label>Из листа</label><input type="text" name="source_sheet_cell" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-input-group"><label>Из ячейки</label><input type="text" name="source_cell_cell" placeholder="A1" required></div>
            <div class="rule-arrow">→</div>
            <div class="rule-input-group"><label>В ячейку</label><input type="text" name="dest_cell_cell" placeholder="B5" required></div>
            <button type="button" class="btn btn-danger btn-sm remove-rule-btn" style="align-self: center; margin-top: 1rem;">Удалить</button>`;
        container.appendChild(ruleRow);
    });

    // Кнопка для правил КОЛОНОК
    document.getElementById('add-manual-rule')?.addEventListener('click', function() {
        const container = document.getElementById('manual-rules-container');
        const ruleRow = document.createElement('div');
        ruleRow.className = 'rule-row';
        ruleRow.innerHTML = `
            <div class="rule-input-group"><label>Из листа</label><input type="text" name="source_sheet" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-input-group"><label>Из ячейки</label><input type="text" name="source_cell" placeholder="A1" required></div>
            <div class="rule-arrow">→</div>
            <div class="rule-input-group"><label>В колонку</label><input type="text" name="template_col" placeholder="B" required></div>
            <button type="button" class="btn btn-danger btn-sm remove-rule-btn" style="align-self: center; margin-top: 1rem;">Удалить</button>`;
        container.appendChild(ruleRow);
    });

    // Кнопка для СТАТИЧНЫХ ЗНАЧЕНИЙ
    document.getElementById('add-static-value-rule')?.addEventListener('click', function() {
        const container = document.getElementById('static-value-rules-container');
        const ruleRow = document.createElement('div');
        ruleRow.className = 'rule-row';
        ruleRow.innerHTML = `
            <div class="rule-input-group"><label>На лист шаблона</label><input type="text" name="target_sheet_static" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-input-group" style="flex-grow: 0.5;"><label>В колонку</label><input type="text" name="target_col_static" placeholder="D" required></div>
            <div class="rule-arrow">=</div>
            <div class="rule-input-group" style="flex-grow: 2;"><label>Вставить значение</label><input type="text" name="static_value" placeholder="Готово" required></div>
            <button type="button" class="btn btn-danger btn-sm remove-rule-btn" style="align-self: center; margin-top: 1rem;">Удалить</button>`;
        container.appendChild(ruleRow);
    });

    // Кнопка для ЗАПОЛНЕНИЯ ИЗ ЯЧЕЙКИ
    document.getElementById('add-source-fill-rule')?.addEventListener('click', function() {
        const container = document.getElementById('source-cell-fill-rules-container');
        const ruleRow = document.createElement('div');
        ruleRow.className = 'rule-row';
        ruleRow.innerHTML = `
            <div class="rule-input-group"><label>Из листа источника</label><input type="text" name="source_sheet_fill" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-input-group"><label>Из ячейки источника</label><input type="text" name="source_cell_fill" placeholder="A2" required></div>
            <div class="rule-arrow">→</div>
            <div class="rule-input-group"><label>На лист шаблона</label><input type="text" name="target_sheet_fill" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-input-group"><label>В колонку шаблона</fabel><input type="text" name="target_col_fill" placeholder="C" required></div>
            <button type="button" class="btn btn-danger btn-sm remove-rule-btn" style="align-self: center; margin-top: 1rem;">Удалить</button>`;
        container.appendChild(ruleRow);
    });

    // Кнопка для правил ФОРМУЛ
    document.getElementById('add-formula-rule')?.addEventListener('click', function() {
        const container = document.getElementById('formula-rules-container');
        const ruleRow = document.createElement('div');
        ruleRow.className = 'rule-row';
        ruleRow.innerHTML = `
            <div class="rule-input-group"><label>Из листа источника</label><input type="text" name="source_sheet_formula" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-arrow">→</div>
            <div class="rule-input-group"><label>На лист шаблона</label><input type="text" name="target_sheet_formula" placeholder="Лист1" value="Лист1" required></div>
            <div class="rule-input-group" style="flex-grow: 0.5;"><label>В колонку</label><input type="text" name="target_col_formula" placeholder="C" required></div>
            <div class="rule-arrow">=</div>
            <div class="rule-input-group" style="flex-grow: 2;"><label>Вычислить по формуле</label><input type="text" name="formula_string" placeholder="=A{row}*1.2" required></div>
            <button type="button" class="btn btn-danger btn-sm remove-rule-btn" style="align-self: center; margin-top: 1rem;">Удалить</button>`;
        container.appendChild(ruleRow);
    });

    // Общая логика для УДАЛЕНИЯ правил из любого контейнера
    const allContainers = [
        document.getElementById('manual-rules-container'),
        document.getElementById('cell-mappings-container'),
        document.getElementById('formula-rules-container'),
        document.getElementById('static-value-rules-container'),
        document.getElementById('sheet-settings-container'),
        document.getElementById('source-cell-fill-rules-container')
    ];
    allContainers.forEach(container => {
        if (container) {
            container.addEventListener('click', function(e) {
                if (e.target?.classList.contains('remove-rule-btn')) {
                    e.target.closest('.rule-row').remove();
                }
            });
        }
    });

    // Логика для кнопок "Редактировать" на страницах словарей
    document.querySelectorAll('.edit-btn').forEach(button => {
        button.addEventListener('click', function() {
            const canonical = this.dataset.canonical;
            const synonyms = this.dataset.synonyms;

            const form = this.closest('.container').querySelector('form');
            if(form) {
                form.querySelector('input[name*="canonical_"]').value = canonical;
                form.querySelector('input[name*="synonyms"], input[name*="find_words"]').value = synonyms;
                form.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    });

}); // <-- ЭТО ЗАКРЫВАЕТ 'DOMContentLoaded'. Лишней '}' НЕТ.