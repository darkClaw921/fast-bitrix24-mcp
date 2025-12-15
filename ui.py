from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
from dotenv import load_dotenv
from loguru import logger
import json
import asyncio
import inspect
import time
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

app = FastAPI(title="Bitrix24 MCP Tools Tester", version="1.0.0")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройка логирования
logger.add("logs/ui_{time}.log", rotation="1 day", retention="7 days", level="INFO")

# Конфигурация MCP сервера
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable_http")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

if not AUTH_TOKEN:
    raise RuntimeError("AUTH_TOKEN не задан в окружении (.env)")

# Инициализация MCP клиента
mcp_client: Optional[MultiServerMCPClient] = None

async def get_mcp_client() -> MultiServerMCPClient:
    """Получение или создание MCP клиента"""
    global mcp_client
    if mcp_client is None:
        config = {
            "bitrix24-main": {
                "url": MCP_SERVER_URL,
                "transport": MCP_TRANSPORT,
            }
        }
        # Добавляем заголовки авторизации для streamable_http и sse транспортов
        if MCP_TRANSPORT in ("streamable_http", "sse", "http"):
            config["bitrix24-main"]["headers"] = {
                "Authorization": f"Bearer {AUTH_TOKEN}"
            }
        mcp_client = MultiServerMCPClient(config)
    return mcp_client


class ToolCallRequest(BaseModel):
    """Модель запроса для вызова tool"""
    arguments: Dict[str, Any] = {}


@app.on_event("startup")
async def startup_event():
    """Инициализация при старте приложения"""
    logger.info("Запуск FastAPI UI приложения")
    logger.info(f"MCP_SERVER_URL: {MCP_SERVER_URL}")
    logger.info(f"MCP_TRANSPORT: {MCP_TRANSPORT}")
    try:
        client = await get_mcp_client()
        tools = await client.get_tools()
        logger.info(f"Подключение к MCP серверу успешно. Доступно tools: {len(tools)}")
    except Exception as e:
        logger.error(f"Ошибка подключения к MCP серверу: {e}", exc_info=True)
        logger.warning("Приложение продолжит работу, но tools могут быть недоступны")


@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при остановке приложения"""
    logger.info("Остановка FastAPI UI приложения")
    global mcp_client
    if mcp_client:
        mcp_client = None


@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница с UI для тестирования tools"""
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bitrix24 MCP Tools Tester</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .header p {
                opacity: 0.9;
                font-size: 1.1em;
            }
            .content {
                padding: 30px;
            }
            .section {
                margin-bottom: 30px;
            }
            .section-title {
                font-size: 1.5em;
                margin-bottom: 15px;
                color: #333;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }
            .tool-selector {
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: 20px;
                margin-bottom: 20px;
            }
            .tool-list {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 15px;
                max-height: 500px;
                overflow-y: auto;
            }
            .tool-item {
                padding: 12px;
                margin-bottom: 8px;
                background: #f5f5f5;
                border-radius: 6px;
                cursor: pointer;
                transition: all 0.2s;
                border-left: 4px solid transparent;
            }
            .tool-item:hover {
                background: #e8e8e8;
                border-left-color: #667eea;
            }
            .tool-item.active {
                background: #e3e8ff;
                border-left-color: #667eea;
                font-weight: bold;
            }
            .tool-item .tool-name {
                font-weight: 600;
                color: #333;
                margin-bottom: 4px;
            }
            .tool-item .tool-description {
                font-size: 0.9em;
                color: #666;
            }
            .tool-details {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 20px;
            }
            .tool-info {
                margin-bottom: 20px;
            }
            .tool-info h3 {
                color: #667eea;
                margin-bottom: 10px;
            }
            .tool-info p {
                color: #666;
                line-height: 1.6;
            }
            .params-form {
                margin-top: 20px;
            }
            .param-group {
                margin-bottom: 15px;
            }
            .param-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 600;
                color: #333;
            }
            .param-group input,
            .param-group textarea {
                width: 100%;
                padding: 10px;
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                font-size: 14px;
                font-family: 'Courier New', monospace;
            }
            .param-group textarea {
                min-height: 100px;
                resize: vertical;
            }
            .param-group input:focus,
            .param-group textarea:focus {
                outline: none;
                border-color: #667eea;
            }
            .param-group .param-type {
                font-size: 0.85em;
                color: #999;
                margin-top: 4px;
            }
            .button-group {
                display: flex;
                gap: 10px;
                margin-top: 20px;
            }
            button {
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            }
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .btn-secondary {
                background: #f5f5f5;
                color: #333;
            }
            .btn-secondary:hover {
                background: #e8e8e8;
            }
            .result-section {
                margin-top: 30px;
                border-top: 2px solid #e0e0e0;
                padding-top: 20px;
            }
            .result-box {
                background: #f9f9f9;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 20px;
                max-height: 500px;
                overflow-y: auto;
            }
            .result-box pre {
                margin: 0;
                white-space: pre-wrap;
                word-wrap: break-word;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
            .loading {
                display: none;
                text-align: center;
                padding: 20px;
                color: #667eea;
            }
            .loading.active {
                display: block;
            }
            .error {
                background: #fee;
                border-color: #fcc;
                color: #c33;
            }
            .success {
                background: #efe;
                border-color: #cfc;
            }
            .status-badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.85em;
                font-weight: 600;
                margin-left: 10px;
            }
            .status-connected {
                background: #cfc;
                color: #060;
            }
            .status-disconnected {
                background: #fcc;
                color: #600;
            }
            .execution-time {
                margin-top: 10px;
                padding: 8px 12px;
                background: #e3e8ff;
                border-left: 4px solid #667eea;
                border-radius: 4px;
                font-size: 0.9em;
                color: #333;
                font-weight: 500;
            }
            .execution-time strong {
                color: #667eea;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔧 Bitrix24 MCP Tools Tester</h1>
                <p>Интерфейс для тестирования всех tools MCP сервера</p>
                <span id="connectionStatus" class="status-badge status-disconnected">Подключение...</span>
            </div>
            <div class="content">
                <div class="section">
                    <h2 class="section-title">Выберите tool для тестирования</h2>
                    <div class="tool-selector">
                        <div class="tool-list" id="toolList">
                            <div style="text-align: center; padding: 20px; color: #999;">
                                Загрузка tools...
                            </div>
                        </div>
                        <div class="tool-details" id="toolDetails">
                            <div style="text-align: center; padding: 40px; color: #999;">
                                Выберите tool из списка слева
                            </div>
                        </div>
                    </div>
                </div>
                <div class="result-section">
                    <h2 class="section-title">Результат выполнения</h2>
                    <div class="loading" id="loading">⏳ Выполнение запроса...</div>
                    <div class="execution-time" id="executionTime" style="display: none;"></div>
                    <div class="result-box" id="resultBox" style="display: none;">
                        <pre id="resultContent"></pre>
                    </div>
                </div>
            </div>
        </div>
        <script>
            let tools = [];
            let selectedTool = null;

            // Функция экранирования HTML
            function escapeHtml(text) {
                if (text == null) return '';
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Загрузка списка tools
            async function loadTools() {
                try {
                    const response = await fetch('/api/tools');
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const data = await response.json();
                    tools = data.tools || [];
                    console.log('Загружено tools:', tools.length);
                    renderToolList();
                    updateConnectionStatus(true);
                } catch (error) {
                    console.error('Ошибка загрузки tools:', error);
                    updateConnectionStatus(false);
                    document.getElementById('toolList').innerHTML = 
                        '<div style="text-align: center; padding: 20px; color: #c33;">Ошибка загрузки tools: ' + escapeHtml(error.message) + '</div>';
                }
            }

            function updateConnectionStatus(connected) {
                const statusEl = document.getElementById('connectionStatus');
                if (statusEl) {
                    if (connected) {
                        statusEl.textContent = 'Подключено';
                        statusEl.className = 'status-badge status-connected';
                    } else {
                        statusEl.textContent = 'Отключено';
                        statusEl.className = 'status-badge status-disconnected';
                    }
                }
            }

            function renderToolList() {
                const toolList = document.getElementById('toolList');
                if (!toolList) {
                    console.error('Элемент toolList не найден');
                    return;
                }
                
                if (tools.length === 0) {
                    toolList.innerHTML = '<div style="text-align: center; padding: 20px; color: #999;">Tools не найдены</div>';
                    return;
                }
                
                // Очищаем предыдущие обработчики
                toolList.innerHTML = '';
                
                tools.forEach((tool, index) => {
                    const toolItem = document.createElement('div');
                    toolItem.className = `tool-item ${index === 0 ? 'active' : ''}`;
                    toolItem.dataset.index = index;
                    toolItem.style.cursor = 'pointer';
                    
                    const toolName = document.createElement('div');
                    toolName.className = 'tool-name';
                    toolName.textContent = tool.name || 'Без названия';
                    
                    const toolDesc = document.createElement('div');
                    toolDesc.className = 'tool-description';
                    toolDesc.textContent = tool.description || 'Без описания';
                    
                    toolItem.appendChild(toolName);
                    toolItem.appendChild(toolDesc);
                    
                    // Используем addEventListener вместо onclick
                    toolItem.addEventListener('click', function() {
                        selectTool(index);
                    });
                    
                    toolList.appendChild(toolItem);
                });
                
                if (tools.length > 0) {
                    selectTool(0);
                }
            }

            function selectTool(index) {
                if (index < 0 || index >= tools.length) {
                    console.error('Неверный индекс tool:', index);
                    return;
                }
                
                selectedTool = tools[index];
                console.log('Выбран tool:', selectedTool.name);
                
                // Обновляем активный класс
                document.querySelectorAll('.tool-item').forEach((el, i) => {
                    el.classList.toggle('active', i === index);
                });
                
                renderToolDetails();
            }

            function renderToolDetails() {
                if (!selectedTool) {
                    console.error('selectedTool не установлен');
                    return;
                }
                
                const toolDetails = document.getElementById('toolDetails');
                if (!toolDetails) {
                    console.error('Элемент toolDetails не найден');
                    return;
                }
                
                // Логируем структуру параметров для отладки
                console.log('selectedTool:', selectedTool);
                console.log('selectedTool.parameters:', selectedTool.parameters);
                
                // Получаем параметры из разных возможных мест
                let params = {};
                let required = [];
                
                if (selectedTool.parameters) {
                    // Если parameters - объект с properties
                    if (selectedTool.parameters.properties) {
                        params = selectedTool.parameters.properties || {};
                        required = selectedTool.parameters.required || [];
                    } 
                    // Если parameters - объект, но без properties (возможно, это уже properties)
                    else if (typeof selectedTool.parameters === 'object' && !selectedTool.parameters.type) {
                        params = selectedTool.parameters;
                    }
                    // Если parameters - объект с type: "object"
                    else if (selectedTool.parameters.type === 'object' && selectedTool.parameters.properties) {
                        params = selectedTool.parameters.properties || {};
                        required = selectedTool.parameters.required || [];
                    }
                }
                
                console.log('Извлеченные params:', params);
                console.log('Извлеченные required:', required);
                console.log('Количество параметров:', Object.keys(params).length);
                
                // Создаем контейнер для информации о tool
                const toolInfo = document.createElement('div');
                toolInfo.className = 'tool-info';
                
                const toolTitle = document.createElement('h3');
                toolTitle.textContent = selectedTool.name || 'Без названия';
                
                const toolDesc = document.createElement('p');
                toolDesc.textContent = selectedTool.description || 'Без описания';
                
                toolInfo.appendChild(toolTitle);
                toolInfo.appendChild(toolDesc);
                
                // Создаем форму
                const form = document.createElement('form');
                form.className = 'params-form';
                
                // Добавляем поля параметров
                // Проверяем, есть ли реальные параметры (не пустой объект)
                const paramKeys = Object.keys(params || {});
                const hasParams = paramKeys.length > 0 && params && typeof params === 'object';
                
                console.log('hasParams:', hasParams, 'paramKeys:', paramKeys);
                
                if (hasParams) {
                    paramKeys.forEach((paramName) => {
                        const paramInfo = params[paramName];
                        
                        // Пропускаем служебные поля
                        if (paramName === 'type' || paramName === 'properties' || paramName === 'required') {
                            return;
                        }
                        
                        // Если paramInfo - не объект, создаем базовую структуру
                        if (typeof paramInfo !== 'object' || paramInfo === null) {
                            paramInfo = { type: 'string' };
                        }
                        
                        const paramGroup = document.createElement('div');
                        paramGroup.className = 'param-group';
                        
                        const label = document.createElement('label');
                        label.innerHTML = escapeHtml(paramName) + (required.includes(paramName) ? ' <span style="color: red;">*</span>' : '');
                        
                        const paramType = paramInfo.type || 'string';
                        const defaultValue = paramInfo.default !== undefined ? JSON.stringify(paramInfo.default) : '';
                        
                        let input;
                        if (paramType === 'object' || paramType === 'array') {
                            input = document.createElement('textarea');
                            input.id = `param_${paramName}`;
                            input.placeholder = defaultValue || (paramType === 'array' ? '[]' : '{}');
                        } else if (paramType === 'boolean') {
                            input = document.createElement('input');
                            input.type = 'checkbox';
                            input.id = `param_${paramName}`;
                            if (defaultValue === 'true') {
                                input.checked = true;
                            }
                        } else {
                            input = document.createElement('input');
                            input.type = 'text';
                            input.id = `param_${paramName}`;
                            input.placeholder = defaultValue || '';
                            input.value = defaultValue || '';
                        }
                        
                        const paramTypeLabel = document.createElement('div');
                        paramTypeLabel.className = 'param-type';
                        paramTypeLabel.textContent = `Тип: ${paramType}`;
                        
                        if (paramInfo.description) {
                            const paramDesc = document.createElement('div');
                            paramDesc.style.fontSize = '0.85em';
                            paramDesc.style.color = '#666';
                            paramDesc.style.marginTop = '4px';
                            paramDesc.textContent = paramInfo.description;
                            paramGroup.appendChild(paramDesc);
                        }
                        
                        paramGroup.appendChild(label);
                        paramGroup.appendChild(input);
                        paramGroup.appendChild(paramTypeLabel);
                        
                        form.appendChild(paramGroup);
                    });
                    
                    // Если после фильтрации параметров не осталось, показываем сообщение
                    if (form.children.length === 0) {
                        const noParams = document.createElement('p');
                        noParams.style.color = '#999';
                        noParams.textContent = 'Параметры не требуются';
                        form.appendChild(noParams);
                    }
                } else {
                    const noParams = document.createElement('p');
                    noParams.style.color = '#999';
                    noParams.textContent = 'Параметры не требуются';
                    form.appendChild(noParams);
                }
                
                // Кнопки
                const buttonGroup = document.createElement('div');
                buttonGroup.className = 'button-group';
                
                const submitBtn = document.createElement('button');
                submitBtn.type = 'submit';
                submitBtn.className = 'btn-primary';
                submitBtn.textContent = 'Выполнить';
                
                const clearBtn = document.createElement('button');
                clearBtn.type = 'button';
                clearBtn.className = 'btn-secondary';
                clearBtn.textContent = 'Очистить результат';
                clearBtn.addEventListener('click', clearResult);
                
                buttonGroup.appendChild(submitBtn);
                buttonGroup.appendChild(clearBtn);
                form.appendChild(buttonGroup);
                
                // Обработчик отправки формы
                form.addEventListener('submit', callTool);
                
                // Очищаем и заполняем toolDetails
                toolDetails.innerHTML = '';
                toolDetails.appendChild(toolInfo);
                toolDetails.appendChild(form);
            }

            async function callTool(event) {
                event.preventDefault();
                if (!selectedTool) {
                    console.error('selectedTool не установлен');
                    return;
                }
                
                const loading = document.getElementById('loading');
                const resultBox = document.getElementById('resultBox');
                const resultContent = document.getElementById('resultContent');
                const executionTime = document.getElementById('executionTime');
                
                if (!loading || !resultBox || !resultContent || !executionTime) {
                    console.error('Не найдены элементы для отображения результата');
                    return;
                }
                
                loading.classList.add('active');
                resultBox.style.display = 'none';
                executionTime.style.display = 'none';
                
                const startTime = performance.now();
                
                // Сбор параметров
                const arguments_ = {};
                const params = selectedTool.parameters?.properties || {};
                for (const paramName of Object.keys(params)) {
                    const input = document.getElementById(`param_${paramName}`);
                    if (!input) continue;
                    
                    const paramInfo = params[paramName];
                    const paramType = paramInfo.type || 'string';
                    
                    let value = input.value;
                    if (paramType === 'boolean') {
                        value = input.checked;
                    } else if (paramType === 'object' || paramType === 'array') {
                        try {
                            value = value ? JSON.parse(value) : (paramType === 'array' ? [] : {});
                        } catch (e) {
                            alert(`Ошибка парсинга JSON для параметра ${paramName}: ${e.message}`);
                            loading.classList.remove('active');
                            return;
                        }
                    } else if (paramType === 'integer' || paramType === 'number') {
                        value = value ? (paramType === 'integer' ? parseInt(value) : parseFloat(value)) : undefined;
                    }
                    
                    // Добавляем параметр только если он не пустой или если это boolean (может быть false)
                    if (paramType === 'boolean') {
                        arguments_[paramName] = value;
                    } else if (value !== undefined && value !== '' && value !== null) {
                        arguments_[paramName] = value;
                    }
                }
                
                try {
                    const response = await fetch(`/api/tools/${encodeURIComponent(selectedTool.name)}/call`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ arguments: arguments_ })
                    });
                    
                    let data;
                    try {
                        data = await response.json();
                    } catch (e) {
                        // Если не удалось распарсить JSON, читаем текст
                        const text = await response.text();
                        throw new Error(`Ошибка сервера (${response.status}): ${text}`);
                    }
                    
                    loading.classList.remove('active');
                    
                    // Отображение времени выполнения
                    const endTime = performance.now();
                    const clientTime = ((endTime - startTime) / 1000).toFixed(3);
                    const serverTime = data.execution_time ? data.execution_time.toFixed(3) : null;
                    
                    if (serverTime) {
                        executionTime.innerHTML = `<strong>⏱ Время выполнения:</strong> ${serverTime} сек (сервер) / ${clientTime} сек (клиент)`;
                    } else {
                        executionTime.innerHTML = `<strong>⏱ Время выполнения:</strong> ${clientTime} сек (клиент)`;
                    }
                    executionTime.style.display = 'block';
                    
                    if (!response.ok) {
                        // Обработка ошибок HTTP
                        const errorMsg = data.detail || data.error || `HTTP error! status: ${response.status}`;
                        resultBox.className = 'result-box error';
                        resultContent.textContent = `Ошибка: ${errorMsg}\n\n${data.details || ''}`;
                    } else if (data.error) {
                        resultBox.className = 'result-box error';
                        resultContent.textContent = `Ошибка: ${data.error}\n\n${data.details || ''}`;
                    } else {
                        resultBox.className = 'result-box success';
                        resultContent.textContent = typeof data.result === 'string' 
                            ? data.result 
                            : JSON.stringify(data.result, null, 2);
                    }
                    resultBox.style.display = 'block';
                } catch (error) {
                    console.error('Ошибка вызова tool:', error);
                    loading.classList.remove('active');
                    const endTime = performance.now();
                    const clientTime = ((endTime - startTime) / 1000).toFixed(3);
                    executionTime.innerHTML = `<strong>⏱ Время до ошибки:</strong> ${clientTime} сек`;
                    executionTime.style.display = 'block';
                    resultBox.className = 'result-box error';
                    resultContent.textContent = `Ошибка запроса: ${error.message}`;
                    resultBox.style.display = 'block';
                }
            }

            function clearResult() {
                const resultBox = document.getElementById('resultBox');
                const resultContent = document.getElementById('resultContent');
                const executionTime = document.getElementById('executionTime');
                if (resultBox) resultBox.style.display = 'none';
                if (resultContent) resultContent.textContent = '';
                if (executionTime) executionTime.style.display = 'none';
            }

            // Инициализация при загрузке страницы
            document.addEventListener('DOMContentLoaded', function() {
                console.log('DOM загружен, начинаем загрузку tools');
                loadTools();
            });
            
            // На случай, если DOM уже загружен
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', loadTools);
            } else {
                loadTools();
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/tools", response_class=JSONResponse)
async def get_tools():
    """Получение списка всех доступных tools"""
    try:
        logger.info("Запрос списка tools")
        client = await get_mcp_client()
        logger.info("MCP клиент получен, запрашиваем tools")
        tools = await client.get_tools()
        logger.info(f"Получено tools от MCP сервера: {len(tools) if tools else 0}")
        
        tools_list = []
        for tool in tools:
            try:
                tool_name = getattr(tool, 'name', 'unknown')
                tool_info = {
                    "name": tool_name,
                    "description": getattr(tool, 'description', '') or "",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
                
                # Преобразование параметров в формат JSON Schema
                schema = None
                
                # Попытка 1: args_schema (Pydantic схема)
                if hasattr(tool, 'args_schema') and tool.args_schema:
                    try:
                        schema = tool.args_schema.schema() if hasattr(tool.args_schema, 'schema') else {}
                        logger.debug(f"Tool {tool_name}: получена схема из args_schema")
                    except Exception as e:
                        logger.warning(f"Tool {tool_name}: ошибка получения схемы из args_schema: {e}")
                
                # Попытка 2: parameters
                if not schema and hasattr(tool, 'parameters') and tool.parameters:
                    if isinstance(tool.parameters, dict):
                        schema = tool.parameters
                        logger.debug(f"Tool {tool_name}: получена схема из parameters")
                    else:
                        logger.debug(f"Tool {tool_name}: parameters не является dict: {type(tool.parameters)}")
                
                # Попытка 3: args
                if not schema and hasattr(tool, 'args') and tool.args:
                    if isinstance(tool.args, dict):
                        schema = {"type": "object", "properties": tool.args, "required": []}
                        logger.debug(f"Tool {tool_name}: получена схема из args")
                
                # Нормализация схемы
                if schema:
                    # Если схема уже в правильном формате JSON Schema
                    if isinstance(schema, dict):
                        # Убеждаемся, что есть properties
                        if 'properties' in schema:
                            tool_info["parameters"] = schema
                        elif schema.get('type') == 'object' and 'properties' not in schema:
                            # Если type: object, но нет properties, создаем пустые properties
                            tool_info["parameters"] = {"type": "object", "properties": {}, "required": schema.get('required', [])}
                        else:
                            # Если это не JSON Schema формат, пытаемся обернуть
                            tool_info["parameters"] = {
                                "type": "object",
                                "properties": schema if schema else {},
                                "required": []
                            }
                    else:
                        tool_info["parameters"] = {"type": "object", "properties": {}, "required": []}
                    
                    # Логируем информацию о параметрах
                    props = tool_info["parameters"].get("properties", {})
                    req = tool_info["parameters"].get("required", [])
                    logger.info(f"Tool {tool_name}: параметров - {len(props)}, обязательных - {len(req)}")
                    if len(props) > 0:
                        logger.debug(f"Tool {tool_name}: параметры: {list(props.keys())}")
                else:
                    logger.info(f"Tool {tool_name}: схема не найдена, параметры отсутствуют")
                
                tools_list.append(tool_info)
            except Exception as e:
                logger.warning(f"Ошибка обработки tool {getattr(tool, 'name', 'unknown')}: {e}", exc_info=True)
                continue
        
        logger.info(f"Получен список tools: {len(tools_list)}")
        return {"tools": tools_list}
    except Exception as e:
        logger.error(f"Ошибка получения списка tools: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "tools": []}
        )


def _normalize_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализация аргументов перед передачей в инструменты
    
    Преобразует строки 'null', 'None' в None и удаляет параметры со значением None
    из словаря аргументов. Это необходимо для корректной обработки опциональных параметров.
    
    Args:
        arguments: Словарь аргументов для инструмента
    
    Returns:
        Нормализованный словарь аргументов без None-значений
    """
    normalized = {}
    for key, value in arguments.items():
        # Преобразуем строки 'null', 'None' в None
        if isinstance(value, str):
            normalized_value = value.strip().lower()
            if normalized_value in ('null', 'none', ''):
                # Пропускаем параметры со значением None - не передаем их в метод
                continue
        
        # Если значение не None, добавляем его в нормализованный словарь
        if value is not None:
            normalized[key] = value
    
    return normalized


@app.post("/api/tools/{tool_name}/call", response_class=JSONResponse)
async def call_tool(tool_name: str, http_request: Request):
    """Вызов конкретного tool с указанными аргументами"""
    try:
        # Парсим тело запроса вручную
        try:
            body = await http_request.json()
            arguments = body.get('arguments', {}) if isinstance(body, dict) else {}
        except json.JSONDecodeError:
            # Если тело пустое или не JSON, используем пустой словарь
            arguments = {}
        except Exception as e:
            logger.warning(f"Ошибка парсинга тела запроса: {e}, используем пустые аргументы")
            arguments = {}
        
        # Нормализуем аргументы: преобразуем 'null'/'None' в None и удаляем None-параметры
        arguments = _normalize_arguments(arguments)
        
        logger.info(f"Вызов tool '{tool_name}' с аргументами: {arguments}")
        
        # Начало измерения времени выполнения
        start_time = time.perf_counter()
        
        client = await get_mcp_client()
        tools = await client.get_tools()
        
        # Поиск нужного tool
        tool = None
        for t in tools:
            if t.name == tool_name:
                tool = t
                break
        
        if not tool:
            logger.warning(f"Tool '{tool_name}' не найден. Доступные tools: {[t.name for t in tools]}")
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' не найден")
        
        # Вызов tool через invoke/ainvoke
        try:
            result = None
            
            # Сначала пробуем асинхронный вызов (предпочтительно для async функций)
            if hasattr(tool, 'ainvoke'):
                ainvoke_method = getattr(tool, 'ainvoke')
                logger.debug(f"Tool '{tool_name}': найден ainvoke, тип: {type(ainvoke_method)}, callable: {callable(ainvoke_method)}")
                
                # Проверяем, является ли это вызываемым объектом
                if not callable(ainvoke_method):
                    logger.warning(f"Tool '{tool_name}': ainvoke не является вызываемым, пробуем invoke")
                    if hasattr(tool, 'invoke'):
                        invoke_method = getattr(tool, 'invoke')
                        if inspect.iscoroutinefunction(invoke_method):
                            result = await invoke_method(arguments or {})
                        else:
                            loop = asyncio.get_event_loop()
                            result = await loop.run_in_executor(None, invoke_method, arguments or {})
                    else:
                        raise HTTPException(status_code=500, detail="Tool не поддерживает вызов: ainvoke не вызываемый и invoke отсутствует")
                # Проверяем, является ли метод корутиной (async)
                elif inspect.iscoroutinefunction(ainvoke_method):
                    logger.debug(f"Tool '{tool_name}': ainvoke - корутина функция")
                    try:
                        result = await ainvoke_method(arguments or {})
                    except Exception as e:
                        error_msg = str(e)
                        # Проверяем, есть ли в ошибке упоминание о проблеме с await
                        if "can't be used in 'await' expression" in error_msg or "await" in error_msg.lower():
                            # Если внутри ainvoke есть проблема с await, пробуем через invoke
                            logger.warning(f"Tool '{tool_name}': ошибка в ainvoke: {e}, пробуем invoke")
                            if hasattr(tool, 'invoke'):
                                invoke_method = getattr(tool, 'invoke')
                                try:
                                    if inspect.iscoroutinefunction(invoke_method):
                                        result = await invoke_method(arguments or {})
                                    else:
                                        loop = asyncio.get_event_loop()
                                        result = await loop.run_in_executor(None, invoke_method, arguments or {})
                                    logger.info(f"Tool '{tool_name}': успешно вызван через invoke")
                                except Exception as invoke_error:
                                    logger.error(f"Tool '{tool_name}': ошибка при вызове через invoke: {invoke_error}")
                                    raise HTTPException(status_code=500, detail=f"Ошибка выполнения tool через invoke: {str(invoke_error)}")
                            else:
                                raise HTTPException(status_code=500, detail=f"Tool не поддерживает синхронный вызов (invoke отсутствует): {error_msg}")
                        else:
                            # Если это не ошибка с await, пробрасываем дальше
                            raise
                else:
                    # Если ainvoke синхронный, вызываем его в executor
                    logger.debug(f"Tool '{tool_name}': ainvoke - синхронный метод, используем executor")
                    try:
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, ainvoke_method, arguments or {})
                        # Если результат - корутина, await'им её
                        if inspect.iscoroutine(result):
                            logger.debug(f"Tool '{tool_name}': результат ainvoke - корутина, await'им")
                            result = await result
                    except Exception as e:
                        error_msg = str(e)
                        # Проверяем, есть ли в ошибке упоминание о проблеме с await
                        if "can't be used in 'await' expression" in error_msg or "await" in error_msg.lower():
                            # Если проблема с await, пробуем invoke
                            logger.warning(f"Tool '{tool_name}': ошибка в executor для ainvoke: {e}, пробуем invoke")
                            if hasattr(tool, 'invoke'):
                                invoke_method = getattr(tool, 'invoke')
                                try:
                                    if inspect.iscoroutinefunction(invoke_method):
                                        result = await invoke_method(arguments or {})
                                    else:
                                        loop = asyncio.get_event_loop()
                                        result = await loop.run_in_executor(None, invoke_method, arguments or {})
                                    logger.info(f"Tool '{tool_name}': успешно вызван через invoke")
                                except Exception as invoke_error:
                                    logger.error(f"Tool '{tool_name}': ошибка при вызове через invoke: {invoke_error}")
                                    raise HTTPException(status_code=500, detail=f"Ошибка выполнения tool через invoke: {str(invoke_error)}")
                            else:
                                raise HTTPException(status_code=500, detail=f"Tool не поддерживает синхронный вызов (invoke отсутствует): {error_msg}")
                        else:
                            raise
            elif hasattr(tool, 'invoke'):
                # Если есть только синхронный invoke, проверяем, можно ли его вызвать
                invoke_method = getattr(tool, 'invoke')
                logger.debug(f"Tool '{tool_name}': найден метод invoke, тип: {type(invoke_method)}")
                
                # Проверяем, является ли метод корутиной (async)
                if inspect.iscoroutinefunction(invoke_method):
                    logger.debug(f"Tool '{tool_name}': invoke - корутина функция")
                    result = await invoke_method(arguments or {})
                else:
                    # Синхронный вызов в отдельном потоке, чтобы не блокировать event loop
                    logger.debug(f"Tool '{tool_name}': invoke - синхронный метод, используем executor")
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, invoke_method, arguments or {})
            else:
                raise HTTPException(status_code=500, detail="Tool не поддерживает вызов (нет методов invoke/ainvoke)")
            
            if result is None:
                raise HTTPException(status_code=500, detail="Tool вернул None")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка выполнения tool '{tool_name}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка выполнения tool: {str(e)}")
        
        # Конец измерения времени выполнения
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        logger.info(f"Tool '{tool_name}' выполнен успешно за {execution_time:.3f} сек")
        
        # Преобразование результата в строку, если это не строка
        if isinstance(result, (dict, list)):
            # Если результат - словарь или список, возвращаем как есть
            return {"result": result, "execution_time": execution_time}
        elif hasattr(result, 'content'):
            # Если результат имеет атрибут content (например, из langchain)
            return {"result": result.content if hasattr(result.content, '__str__') else str(result.content), "execution_time": execution_time}
        else:
            # Преобразуем в строку
            return {"result": str(result), "execution_time": execution_time}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка вызова tool '{tool_name}': {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "details": f"Ошибка при выполнении tool '{tool_name}'"
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
