import logging
import sys
from fastapi import FastAPI
from .routers import line

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)  # 將日誌輸出到標準輸出，確保 Heroku 能捕捉
    ],
)

# 獲取根日誌記錄器
logger = logging.getLogger()

app = FastAPI()

# Include routers
app.include_router(line.router)


@app.get("/")
def read_root():
    logger.info("Root endpoint accessed")
    return {"Hello": "World"}
