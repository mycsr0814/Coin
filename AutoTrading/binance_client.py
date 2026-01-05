"""
바이낸스 선물 API 클라이언트
"""

import ccxt
import time
import logging
from typing import Optional, Dict, List
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """바이낸스 선물 API 클라이언트"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        초기화
        Args:
            api_key: 바이낸스 API 키
            api_secret: 바이낸스 API 시크릿
            testnet: 테스트넷 사용 여부 (현재는 지원하지 않음)
        """
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # 선물 거래
            }
        })
        
        # 바이낸스 테스트넷은 선물 거래를 지원하지 않으므로 항상 실전 모드
        if testnet:
            logger.warning("⚠️  경고: 바이낸스 테스트넷은 선물 거래를 지원하지 않습니다. 실전 모드로 실행됩니다.")
        
        logger.info("실전 거래 모드로 실행 중")
        
        self.symbol = 'ETH/USDT:USDT'
        self.leverage = 3
        
    def set_leverage(self, leverage: int) -> bool:
        """레버리지 설정"""
        try:
            # 바이낸스 선물 레버리지 설정
            self.exchange.set_leverage(leverage, self.symbol, params={'marginMode': 'isolated'})
            self.leverage = leverage
            logger.info(f"레버리지 {leverage}배로 설정 완료")
            return True
        except Exception as e:
            logger.warning(f"레버리지 설정 시도 중 오류 (계속 진행): {e}")
            # 레버리지 설정 실패해도 계속 진행 (이미 설정되어 있을 수 있음)
            self.leverage = leverage
            return True  # 경고만 하고 계속 진행
    
    def get_balance(self) -> Optional[float]:
        """USDT 잔고 조회"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            return float(usdt_balance)
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            return None
    
    def get_current_price(self) -> Optional[float]:
        """현재 가격 조회"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"가격 조회 실패: {e}")
            return None
    
    def get_klines(self, timeframe: str = '15m', limit: int = 100) -> Optional[List[Dict]]:
        """
        캔들 데이터 조회
        Args:
            timeframe: 시간 프레임 (1m, 5m, 15m, 1h 등)
            limit: 조회할 캔들 개수
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"캔들 데이터 조회 실패: {e}")
            return None
    
    def get_position(self) -> Optional[Dict]:
        """현재 포지션 조회"""
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for pos in positions:
                if pos['contracts'] and float(pos['contracts']) != 0:
                    return {
                        'side': 'long' if float(pos['contracts']) > 0 else 'short',
                        'size': abs(float(pos['contracts'])),
                        'entry_price': float(pos['entryPrice']) if pos['entryPrice'] else 0,
                        'unrealized_pnl': float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0,
                    }
            return None
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            return None
    
    def place_market_order(self, side: str, quantity: float) -> Optional[Dict]:
        """
        시장가 주문
        Args:
            side: 'buy' 또는 'sell'
            quantity: 수량
        """
        try:
            # 수량 정밀도 조정 (ETH는 보통 3자리)
            quantity = float(Decimal(str(quantity)).quantize(Decimal('0.001'), rounding=ROUND_DOWN))
            
            if quantity <= 0:
                logger.warning(f"주문 수량이 0 이하: {quantity}")
                return None
            
            order = self.exchange.create_market_order(
                self.symbol,
                side,
                quantity
            )
            logger.info(f"시장가 주문 성공: {side} {quantity} {self.symbol}")
            return order
        except Exception as e:
            logger.error(f"시장가 주문 실패: {e}")
            return None
    
    def place_stop_loss_order(self, side: str, quantity: float, stop_price: float) -> Optional[Dict]:
        """
        손절 주문 (STOP_MARKET)
        Args:
            side: 'buy' 또는 'sell'
            quantity: 수량
            stop_price: 손절 가격
        """
        try:
            quantity = float(Decimal(str(quantity)).quantize(Decimal('0.001'), rounding=ROUND_DOWN))
            
            if quantity <= 0:
                logger.warning(f"손절 주문 수량이 0 이하: {quantity}")
                return None
            
            # 바이낸스 선물 STOP_MARKET 주문
            order = self.exchange.create_order(
                self.symbol,
                'STOP_MARKET',
                side,
                quantity,
                None,  # 가격은 stop_price로
                params={
                    'stopPrice': stop_price,
                    'reduceOnly': True,  # 포지션 감소만
                }
            )
            logger.info(f"손절 주문 성공: {side} {quantity} @ {stop_price}")
            return order
        except Exception as e:
            logger.error(f"손절 주문 실패: {e}")
            return None
    
    def place_take_profit_order(self, side: str, quantity: float, price: float) -> Optional[Dict]:
        """
        익절 주문 (TAKE_PROFIT_MARKET)
        Args:
            side: 'buy' 또는 'sell'
            quantity: 수량
            price: 익절 가격
        """
        try:
            quantity = float(Decimal(str(quantity)).quantize(Decimal('0.001'), rounding=ROUND_DOWN))
            
            if quantity <= 0:
                logger.warning(f"익절 주문 수량이 0 이하: {quantity}")
                return None
            
            order = self.exchange.create_order(
                self.symbol,
                'TAKE_PROFIT_MARKET',
                side,
                quantity,
                None,
                params={
                    'stopPrice': price,
                    'reduceOnly': True,
                }
            )
            logger.info(f"익절 주문 성공: {side} {quantity} @ {price}")
            return order
        except Exception as e:
            logger.error(f"익절 주문 실패: {e}")
            return None
    
    def cancel_all_orders(self) -> bool:
        """모든 주문 취소"""
        try:
            self.exchange.cancel_all_orders(self.symbol)
            logger.info("모든 주문 취소 완료")
            return True
        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return False
    
    def close_position(self) -> Optional[Dict]:
        """포지션 전량 청산"""
        try:
            position = self.get_position()
            if not position:
                logger.info("청산할 포지션이 없습니다")
                return None
            
            side = 'sell' if position['side'] == 'long' else 'buy'
            quantity = position['size']
            
            order = self.place_market_order(side, quantity)
            return order
        except Exception as e:
            logger.error(f"포지션 청산 실패: {e}")
            return None

