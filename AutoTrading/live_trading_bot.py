"""
실전 거래 봇 메인 클래스
"""

import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path

from trading_strategy import TradingStrategy
from binance_client import BinanceFuturesClient
import config

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LiveTradingBot:
    """실전 거래 봇"""
    
    def __init__(self):
        """초기화"""
        self.client = BinanceFuturesClient(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET,
            testnet=config.BINANCE_TESTNET
        )
        self.strategy = TradingStrategy()
        
        # 상태 관리
        self.position = None  # 현재 포지션 정보
        self.last_candle_time = None
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.initial_balance = None
        self.max_equity = None
        
        # 데이터 저장
        self.candle_data = []  # 캔들 데이터 저장
        
        # 레버리지 설정
        if not self.client.set_leverage(config.LEVERAGE):
            logger.error("레버리지 설정 실패")
            raise Exception("레버리지 설정 실패")
    
    def initialize(self) -> bool:
        """초기화 및 검증"""
        logger.info("="*60)
        logger.info("거래 봇 초기화 중...")
        logger.info("="*60)
        
        # 잔고 확인
        balance = self.client.get_balance()
        if balance is None:
            logger.error("잔고 조회 실패")
            return False
        
        if balance < config.MIN_BALANCE:
            logger.error(f"잔고가 최소 금액({config.MIN_BALANCE} USDT)보다 낮습니다: {balance} USDT")
            return False
        
        self.initial_balance = balance
        self.max_equity = balance
        logger.info(f"초기 잔고: {balance:.2f} USDT")
        
        # 기존 포지션 확인
        position = self.client.get_position()
        if position:
            logger.warning(f"기존 포지션 발견: {position}")
            if not config.ENABLE_TRADING:
                logger.warning("모의 거래 모드이므로 기존 포지션을 청산하지 않습니다")
        
        # 과거 캔들 데이터 수집 (지표 계산용)
        logger.info("과거 캔들 데이터 수집 중...")
        klines = self.client.get_klines(config.TIMEFRAME, limit=200)
        if not klines:
            logger.error("캔들 데이터 수집 실패")
            return False
        
        # DataFrame으로 변환
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # 지표 계산
        df = self.strategy.calculate_indicators(df)
        
        # timestamp를 컬럼으로 변환하여 저장
        df = df.reset_index()
        self.candle_data = df.to_dict('records')
        
        logger.info(f"캔들 데이터 {len(df)}개 수집 완료")
        logger.info("="*60)
        
        return True
    
    def check_risk_limits(self) -> bool:
        """리스크 제한 확인"""
        balance = self.client.get_balance()
        if balance is None:
            return False
        
        if balance < config.MIN_BALANCE:
            logger.error(f"잔고가 최소 금액 이하: {balance} USDT")
            return False
        
        # 일일 손실 확인
        daily_loss_pct = (self.initial_balance - balance) / self.initial_balance * 100
        if daily_loss_pct >= config.MAX_DAILY_LOSS_PCT:
            logger.error(f"일일 최대 손실 한도 도달: {daily_loss_pct:.2f}%")
            return False
        
        # 드로우다운 확인
        if self.max_equity:
            drawdown_pct = (self.max_equity - balance) / self.max_equity * 100
            if drawdown_pct >= config.MAX_DRAWDOWN_PCT:
                logger.error(f"최대 드로우다운 한도 도달: {drawdown_pct:.2f}%")
                return False
        
        # 일일 거래 횟수 확인
        if self.daily_trades >= config.MAX_TRADES_PER_DAY:
            logger.warning(f"일일 최대 거래 횟수 도달: {self.daily_trades}")
            return False
        
        return True
    
    def update_candle_data(self, new_candle: Dict) -> bool:
        """캔들 데이터 업데이트"""
        try:
            # 기존 데이터를 DataFrame으로 변환
            if len(self.candle_data) > 0:
                df = pd.DataFrame(self.candle_data)
                # timestamp가 인덱스인 경우 컬럼으로 변환
                if 'timestamp' not in df.columns and df.index.name == 'timestamp':
                    df = df.reset_index()
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
            else:
                df = pd.DataFrame()
            
            # 새 캔들 추가
            new_row = pd.DataFrame([{
                'open': new_candle[1],
                'high': new_candle[2],
                'low': new_candle[3],
                'close': new_candle[4],
                'volume': new_candle[5]
            }], index=[pd.to_datetime(new_candle[0], unit='ms')])
            new_row.index.name = 'timestamp'
            
            df = pd.concat([df, new_row])
            
            # 최근 200개만 유지
            if len(df) > 200:
                df = df.tail(200)
            
            # 지표 재계산
            df = self.strategy.calculate_indicators(df)
            
            # timestamp를 컬럼으로 변환하여 저장
            df = df.reset_index()
            self.candle_data = df.to_dict('records')
            
            return True
        except Exception as e:
            logger.error(f"캔들 데이터 업데이트 실패: {e}", exc_info=True)
            return False
    
    def check_entry_signal(self) -> Optional[str]:
        """진입 신호 확인"""
        if len(self.candle_data) < 2:
            return None
        
        try:
            # 최근 2개 봉 가져오기
            df = pd.DataFrame(self.candle_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            row = df.iloc[-1]
            prev_row = df.iloc[-2]
            
            should_enter, direction = self.strategy.check_entry_signal(row, prev_row)
            
            if should_enter:
                logger.info(f"진입 신호 발견: {direction}")
                return direction
            
            return None
        except Exception as e:
            logger.error(f"진입 신호 확인 실패: {e}")
            return None
    
    def enter_position(self, direction: str) -> bool:
        """포지션 진입"""
        if not config.ENABLE_TRADING:
            logger.info(f"[모의 거래] 진입 신호: {direction}")
            return True
        
        try:
            # 현재 가격 조회
            current_price = self.client.get_current_price()
            if not current_price:
                logger.error("현재 가격 조회 실패")
                return False
            
            # 최근 봉 데이터
            df = pd.DataFrame(self.candle_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            row = df.iloc[-1]
            
            # 추세 강도 확인
            trend_strength, volume_ratio = self.strategy.get_trend_strength(row)
            
            # 잔고 확인
            balance = self.client.get_balance()
            if not balance:
                return False
            
            # 포지션 크기 계산
            quantity, capital_used = self.strategy.calculate_position_size(
                current_price, trend_strength, balance
            )
            
            if quantity <= 0:
                logger.warning("포지션 크기가 0 이하")
                return False
            
            # 주문 실행
            side = 'buy' if direction == 'long' else 'sell'
            order = self.client.place_market_order(side, quantity)
            
            if not order:
                logger.error("주문 실행 실패")
                return False
            
            # 손절/익절 가격 계산
            atr = row.get('atr', np.nan)
            if not np.isfinite(atr) or atr <= 0:
                logger.error("ATR 값이 유효하지 않음")
                return False
            
            stop_loss, take_profit, partial_take_profit = self.strategy.calculate_stop_loss_take_profit(
                current_price, atr, direction
            )
            
            # 손절 주문
            stop_side = 'sell' if direction == 'long' else 'buy'
            self.client.place_stop_loss_order(stop_side, quantity, stop_loss)
            
            # 부분 익절 주문 (50%)
            partial_quantity = quantity * 0.5
            take_side = 'sell' if direction == 'long' else 'buy'
            self.client.place_take_profit_order(take_side, partial_quantity, partial_take_profit)
            
            # 전체 익절 주문 (나머지 50%)
            remaining_quantity = quantity - partial_quantity
            self.client.place_take_profit_order(take_side, remaining_quantity, take_profit)
            
            # 포지션 정보 저장
            self.position = {
                'side': direction,
                'entry_price': current_price,
                'quantity': quantity,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'partial_take_profit': partial_take_profit,
                'entry_time': datetime.now(),
                'trend_strength': trend_strength,
                'volume_ratio': volume_ratio
            }
            
            self.daily_trades += 1
            logger.info(f"포지션 진입 완료: {direction} {quantity:.3f} @ {current_price:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"포지션 진입 실패: {e}")
            return False
    
    def check_exit_conditions(self) -> bool:
        """청산 조건 확인 (주문이 체결되었는지 확인)"""
        if not self.position:
            return False
        
        try:
            position = self.client.get_position()
            
            # 포지션이 없으면 청산된 것
            if not position or position['size'] == 0:
                logger.info("포지션이 청산되었습니다")
                
                # 포지션 정보 로깅
                exit_price = self.client.get_current_price()
                if exit_price:
                    logger.info(f"청산 가격: {exit_price:.2f}")
                
                self.position = None
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"청산 조건 확인 실패: {e}")
            return False
    
    def run(self):
        """메인 루프 실행"""
        logger.info("거래 봇 시작")
        
        if not self.initialize():
            logger.error("초기화 실패")
            return
        
        logger.info("거래 봇 실행 중... (Ctrl+C로 종료)")
        
        try:
            while True:
                # 리스크 제한 확인
                if not self.check_risk_limits():
                    logger.error("리스크 제한 도달. 거래 중단")
                    break
                
                # 최신 캔들 데이터 조회
                klines = self.client.get_klines(config.TIMEFRAME, limit=1)
                if not klines:
                    logger.warning("캔들 데이터 조회 실패")
                    time.sleep(60)
                    continue
                
                latest_candle = klines[-1]
                candle_time = pd.to_datetime(latest_candle[0], unit='ms')
                
                # 새 봉이 완성되었는지 확인
                if self.last_candle_time and candle_time <= self.last_candle_time:
                    # 아직 같은 봉
                    time.sleep(30)
                    continue
                
                # 새 봉 완성
                logger.info(f"새 봉 완성: {candle_time}")
                self.last_candle_time = candle_time
                
                # 캔들 데이터 업데이트
                if not self.update_candle_data(latest_candle):
                    logger.warning("캔들 데이터 업데이트 실패")
                    continue
                
                # 현재 포지션 확인
                current_position = self.client.get_position()
                
                if not current_position:
                    # 포지션이 없으면 진입 신호 확인
                    if not self.position:
                        direction = self.check_entry_signal()
                        if direction:
                            self.enter_position(direction)
                else:
                    # 포지션이 있으면 청산 조건 확인
                    self.check_exit_conditions()
                    
                    # 포지션 정보 업데이트
                    self.position = {
                        'side': current_position['side'],
                        'size': current_position['size'],
                        'entry_price': current_position['entry_price'],
                        'unrealized_pnl': current_position['unrealized_pnl']
                    }
                
                # 잔고 업데이트
                balance = self.client.get_balance()
                if balance:
                    if not self.max_equity or balance > self.max_equity:
                        self.max_equity = balance
                
                # 대기 (다음 봉 완성까지)
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("사용자에 의해 중단됨")
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}", exc_info=True)
        finally:
            logger.info("거래 봇 종료")

