"""
설정 파일
환경 변수에서 설정값을 읽어옴
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 로그 디렉토리
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# API 설정 (환경 변수에서 읽기)
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')
BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

# 거래 설정
SYMBOL = 'ETH/USDT:USDT'
TIMEFRAME = '15m'  # 15분봉
LEVERAGE = 3
INITIAL_CAPITAL = float(os.getenv('INITIAL_CAPITAL', '30.0'))

# 리스크 관리
MAX_DAILY_LOSS_PCT = float(os.getenv('MAX_DAILY_LOSS_PCT', '10.0'))  # 일일 최대 손실 %
MAX_DRAWDOWN_PCT = float(os.getenv('MAX_DRAWDOWN_PCT', '20.0'))  # 최대 드로우다운 %
MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', '10'))  # 일일 최대 거래 횟수

# 안전장치
ENABLE_TRADING = os.getenv('ENABLE_TRADING', 'false').lower() == 'true'  # 실제 거래 활성화 여부
MIN_BALANCE = float(os.getenv('MIN_BALANCE', '10.0'))  # 최소 잔고 (이하일 경우 거래 중단)

# 로깅
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = LOG_DIR / 'trading_bot.log'

# 알림 (선택사항)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')


def validate_config() -> bool:
    """설정값 검증"""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        print("오류: BINANCE_API_KEY와 BINANCE_API_SECRET 환경 변수를 설정해주세요.")
        return False
    
    if ENABLE_TRADING:
        print("⚠️  경고: 실제 거래 모드가 활성화되어 있습니다!")
    else:
        print("ℹ️  정보: 모의 거래 모드입니다 (ENABLE_TRADING=false)")
    
    return True

