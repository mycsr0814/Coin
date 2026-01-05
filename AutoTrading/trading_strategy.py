"""
공통 거래 전략 모듈
백테스트와 실전 거래에서 공통으로 사용하는 전략 로직
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict
import warnings

warnings.filterwarnings('ignore')

# ================================
# 전략 파라미터
# ================================
LEVERAGE = 3.0
FEE_RATE = 0.0004  # 0.04% (바이낸스 선물 taker 수수료)

# 추세 강도 판별 파라미터
ADX_PERIOD = 14
ADX_STRONG_THRESHOLD = 30.0
ADX_WEAK_THRESHOLD = 23.0
VOLUME_MA_PERIOD = 20
VOLUME_STRONG_MULT = 1.50
VOLUME_MIN_THRESHOLD = 1.12

# 물량 조절 파라미터
STRONG_TREND_POSITION_RATIO = 0.24
WEAK_TREND_POSITION_RATIO = 0.13
MAX_POSITION_RATIO = 0.29

# 진입 조건 파라미터
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_LONG_MIN = 54.0
RSI_SHORT_MAX = 46.0

# 손절/익절 파라미터
ATR_PERIOD = 14
STOP_LOSS_ATR_MULT = 0.72
TAKE_PROFIT_ATR_MULT = 16.0
PARTIAL_TAKE_PROFIT_ATR_MULT = 8.0
PARTIAL_TAKE_PROFIT_RATIO = 0.5


class TradingStrategy:
    """거래 전략 클래스 - 지표 계산 및 신호 확인"""
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 계산"""
        df = df.copy()
        
        # EMA
        df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift(1))
        low_close = np.abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=ATR_PERIOD).mean()
        
        # ADX 계산
        df = self._calculate_adx(df)
        
        # 거래량 비율
        df['volume_ma'] = df['volume'].rolling(window=VOLUME_MA_PERIOD).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        return df
    
    def _calculate_adx(self, df: pd.DataFrame) -> pd.DataFrame:
        """ADX 계산 (Average Directional Index)"""
        # True Range
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift(1))
        low_close = np.abs(df['low'] - df['close'].shift(1))
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        tr = np.max(ranges, axis=1)
        
        # +DM, -DM 계산
        up_move = df['high'] - df['high'].shift(1)
        down_move = df['low'].shift(1) - df['low']
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Wilder's smoothing
        period = ADX_PERIOD
        atr_smooth = tr.rolling(window=period).mean()
        plus_dm_series = pd.Series(plus_dm, index=df.index)
        minus_dm_series = pd.Series(minus_dm, index=df.index)
        plus_dm_smooth = plus_dm_series.rolling(window=period).mean()
        minus_dm_smooth = minus_dm_series.rolling(window=period).mean()
        
        # +DI, -DI 계산
        plus_di = np.where(atr_smooth.values > 0, 100 * (plus_dm_smooth.values / atr_smooth.values), 0)
        minus_di = np.where(atr_smooth.values > 0, 100 * (minus_dm_smooth.values / atr_smooth.values), 0)
        plus_di = pd.Series(plus_di, index=df.index)
        minus_di = pd.Series(minus_di, index=df.index)
        
        # DX 및 ADX
        di_sum = plus_di + minus_di
        dx = np.where(di_sum.values > 0, 100 * np.abs(plus_di.values - minus_di.values) / di_sum.values, 0)
        adx = pd.Series(dx, index=df.index).rolling(window=period).mean()
        
        df['adx'] = adx
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        
        return df
    
    def get_trend_strength(self, row: pd.Series) -> Tuple[str, float]:
        """
        추세 강도 판별 (ADX와 거래량 필수 동반 확인)
        Returns: (trend_strength, volume_ratio)
        """
        adx = row.get('adx', np.nan)
        volume_ratio = row.get('volume_ratio', np.nan)
        
        if not np.isfinite(adx) or not np.isfinite(volume_ratio):
            return "NONE", 0.0
        
        if volume_ratio < VOLUME_MIN_THRESHOLD:
            return "NONE", volume_ratio
        
        if adx >= ADX_STRONG_THRESHOLD and volume_ratio >= VOLUME_STRONG_MULT:
            return "STRONG", volume_ratio
        
        elif adx >= ADX_WEAK_THRESHOLD and volume_ratio >= VOLUME_MIN_THRESHOLD:
            return "WEAK", volume_ratio
        
        return "NONE", volume_ratio
    
    def calculate_position_size(self, price: float, trend_strength: str, available_capital: float) -> Tuple[float, float]:
        """
        추세 강도에 따른 포지션 크기 계산
        Returns: (quantity, capital_used)
        """
        if trend_strength == "STRONG":
            capital_ratio = STRONG_TREND_POSITION_RATIO
        elif trend_strength == "WEAK":
            capital_ratio = WEAK_TREND_POSITION_RATIO
        else:
            return 0.0, 0.0
        
        capital_ratio = min(capital_ratio, MAX_POSITION_RATIO)
        available_capital_amount = available_capital * capital_ratio
        leveraged_capital = available_capital_amount * LEVERAGE
        quantity = leveraged_capital / price
        
        return quantity, available_capital_amount
    
    def check_entry_signal(self, row: pd.Series, prev_row: pd.Series) -> Tuple[bool, str]:
        """
        진입 신호 확인
        Returns: (should_enter, direction)
        """
        trend_strength, volume_ratio = self.get_trend_strength(row)
        
        if trend_strength == "NONE":
            return False, ""
        
        if not np.isfinite(volume_ratio) or volume_ratio < VOLUME_MIN_THRESHOLD:
            return False, ""
        
        # EMA 교차 확인
        ema_fast = row.get('ema_fast', np.nan)
        ema_slow = row.get('ema_slow', np.nan)
        prev_ema_fast = prev_row.get('ema_fast', np.nan)
        prev_ema_slow = prev_row.get('ema_slow', np.nan)
        
        if not all(np.isfinite([ema_fast, ema_slow, prev_ema_fast, prev_ema_slow])):
            return False, ""
        
        rsi = row.get('rsi', np.nan)
        if not np.isfinite(rsi):
            return False, ""
        
        # ADX 방향성 확인
        plus_di = row.get('plus_di', np.nan)
        minus_di = row.get('minus_di', np.nan)
        if not all(np.isfinite([plus_di, minus_di])):
            return False, ""
        
        # 롱 신호
        ema_cross_up = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
        price_above_ema = row['close'] > ema_fast
        bullish_adx = plus_di > minus_di
        if ema_cross_up and rsi >= RSI_LONG_MIN and price_above_ema and bullish_adx:
            return True, "long"
        
        # 숏 신호
        ema_cross_down = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow
        price_below_ema = row['close'] < ema_fast
        bearish_adx = minus_di > plus_di
        if ema_cross_down and rsi <= RSI_SHORT_MAX and price_below_ema and bearish_adx:
            return True, "short"
        
        return False, ""
    
    def calculate_stop_loss_take_profit(self, entry_price: float, atr: float, side: str) -> Tuple[float, float, float]:
        """
        손절/익절 가격 계산
        Returns: (stop_loss, take_profit, partial_take_profit)
        """
        if side == "long":
            stop_loss = entry_price - (atr * STOP_LOSS_ATR_MULT)
            take_profit = entry_price + (atr * TAKE_PROFIT_ATR_MULT)
            partial_take_profit = entry_price + (atr * PARTIAL_TAKE_PROFIT_ATR_MULT)
        else:
            stop_loss = entry_price + (atr * STOP_LOSS_ATR_MULT)
            take_profit = entry_price - (atr * TAKE_PROFIT_ATR_MULT)
            partial_take_profit = entry_price - (atr * PARTIAL_TAKE_PROFIT_ATR_MULT)
        
        return stop_loss, take_profit, partial_take_profit

