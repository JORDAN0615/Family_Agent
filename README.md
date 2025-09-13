# Family Agent

一個基於 FastAPI 構建的家庭管理系統 API 服務。

## 技術棧

- Python 3.11
- FastAPI
- uv (Python 依賴管理)
- Docker & Docker Compose
- uvicorn (ASGI 服務器)

## 環境設置

1. 複製範例環境檔案：

```bash
cp .env.example .env
```

2. 編輯 .env 檔案，填入您的實際設定：

```
LINE_ACCESS_TOKEN=您的LINE_Channel_Access_Token
LINE_CHANNEL_SECRET=您的LINE_Channel_Secret
```

## LINE Bot 設定

### 前置需求

1. 在 [LINE Developers Console](https://developers.line.biz/) 創建一個 Provider 和 Channel
2. 取得 Channel Access Token 和 Channel Secret
3. 將這些資訊添加到環境變數檔案中

### 環境變數設定

在專案根目錄創建 `.env` 檔案：

```bash
LINE_ACCESS_TOKEN=你的Channel_Access_Token
LINE_CHANNEL_SECRET=你的Channel_Secret
```

### 本地開發設定

1. 啟動本地服務：

```bash
uvicorn app.main:app --reload
```

2. 使用 ngrok 建立公開網址：

```bash
# 安裝 ngrok
brew install ngrok  # 使用 Homebrew
# 或從 https://ngrok.com/download 下載

# 啟動 ngrok
ngrok http http://127.0.0.1:8000
```

3. 設定 Webhook URL：
   - 複製 ngrok 提供的 HTTPS URL（例如：`https://xxxx-xxxx-xxxx-xxxx.ngrok-free.app`）
   - 在 LINE Developers Console 中設定 Webhook URL：
     `https://[你的ngrok網址]/line/webhook`
   - 記得開啟 "Use webhook" 選項
   - 點擊 "Verify" 測試連接

### 群組 ID 獲取

1. 將 Bot 加入 LINE 群組
2. 在群組中發送任何訊息
3. 檢查終端機輸出，會看到群組 ID（格式如：Cxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx）

### 測試 Bot 功能

1. 基本命令：
   - `!help` - 顯示幫助訊息
   - `!echo [文字]` - 回傳相同的文字
2. Bot 會自動回應：
   - 文字訊息
   - 貼圖
   - 圖片

注意：每次重新啟動 ngrok 都會產生新的 URL，需要在 LINE Developers Console 更新 Webhook URL。

## 開發環境設置

### 使用 uv（推薦）

1. 安裝 uv（如果尚未安裝）:

```bash
# MacOS 和 Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. 安裝依賴:

```bash
uv pip install -e .
```

3. 運行開發服務器:

```bash
uvicorn app.main:app --reload
```

### 使用 Docker

1. 安裝 Rancher Desktop

   - 下載並安裝 [Rancher Desktop](https://rancherdesktop.io/)
   - Rancher Desktop 提供了完整的容器運行環境，包含了 Docker CLI 和 Docker Compose
   - 安裝完成後不需要額外的環境配置

2. 構建和運行:

```bash
# 構建映像
docker-compose build

# 運行容器
docker-compose up

# 或在背景運行
docker-compose up -d
```

## API 文檔

啟動服務後，可以訪問以下地址查看 API 文檔：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 專案結構

```
family-agent/
├── app/                  # 應用程序主目錄
│   ├── __init__.py
│   ├── main.py          # 主應用入口
│   ├── dependencies.py   # 依賴注入
│   ├── routers/         # API 路由
│   │   ├── __init__.py
│   │   ├── items.py
│   │   └── users.py
│   ├── services/        # 服務層
│   │   └── line/       # LINE 相關服務
│   │       ├── __init__.py
│   │       ├── client.py
│   │       ├── config.py
│   │       └── schemas.py
│   └── internal/        # 內部模塊
│       ├── __init__.py
│       └── admin.py
├── Dockerfile           # Docker 配置
├── docker-compose.yml   # Docker Compose 配置
├── .env.example         # 環境變數範例
└── .gitignore          # Git 忽略文件
```

## 開發指南

1. 添加新的依賴:

```bash
uv pip install package_name
```

2. 環境變量:

   - 開發環境: 複製 `.env.example` 到 `.env` 並填入實際值
   - 生產環境: 確保環境變數在部署環境中正確設置

3. 數據庫遷移:
   - TODO: 添加數據庫遷移說明

## 測試

TODO: 添加測試說明

## 部署

1. 生產環境部署:

```bash
docker-compose -f docker-compose.prod.yml up -d
```

2. 查看日誌:

```bash
docker-compose logs -f
```

## 貢獻指南

1. Fork 本專案
2. 創建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

## 授權

MIT License
