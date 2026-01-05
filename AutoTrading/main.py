"""
실전 거래 봇 메인 실행 파일
AWS에서 24시간 실행
"""

import sys
import logging
from live_trading_bot import LiveTradingBot
import config

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """메인 함수"""
    logger.info("="*60)
    logger.info("바이낸스 ETH 선물 자동 거래 봇 시작")
    logger.info("="*60)
    
    # 설정 검증
    if not config.validate_config():
        logger.error("설정 검증 실패")
        sys.exit(1)
    
    # 거래 봇 생성 및 실행
    try:
        bot = LiveTradingBot()
        bot.run()
    except Exception as e:
        logger.error(f"거래 봇 실행 중 오류 발생: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

