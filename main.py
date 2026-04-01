# main.py
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.api import api_router
from core.config import settings

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title='TaskFlow API',
    description='TaskFlow - система мониторинга задач и управления ими',
    version='1.0.0',
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Подключаем роутеры
app.include_router(api_router)


@app.get('/')
async def root():
    return {
        'message': 'TaskFlow API',
        'docs': '/docs',
        'redoc': '/redoc',
    }


@app.get('/health')
async def health_check():
    return {'status': 'healthy'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host=settings.API_HOST, port=settings.API_PORT, reload=True)
