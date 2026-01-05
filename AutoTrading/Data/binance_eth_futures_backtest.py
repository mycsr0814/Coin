"""
바이낸스 ETH 선물 자동 거래 봇 백테스팅 시스템

요구사항:
- 자본금: 30 USDT
- 레버리지: 3배
- 강한 추세/약한 추세 구분하여 롱/숏 물량 유동적 조절
- 거래량 지표 필수 참고
- 체계적인 CSV 로그 저장
- 3년 데이터로 백테스트
- 백테스트 오류 방지 (look-ahead bias, 슬리피지, 수수료 등)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import warnings

warnings.filterwarnings('ignore')

# ================================
# 설정
# ================================
INITIAL_CAPITAL = 30.0  # USDT
LEVERAGE = 3.0
FEE_RATE = 0.0004  # 0.04% (바이낸스 선물 taker 수수료)
SLIPPAGE_RATE = 0.0005  # 0.05% 슬리피지
FUNDING_RATE = 0.0001  # 8시간당 평균 펀딩비

# 추세 강도 판별 파라미터 (ADX와 거래량 필수 동반) - 강화
ADX_PERIOD = 14
ADX_STRONG_THRESHOLD = 30.0  # 강한 추세 ADX 기준 (28.0 -> 30.0, 더 강한 추세만)
ADX_WEAK_THRESHOLD = 23.0    # 약한 추세 ADX 기준 (21.0 -> 23.0, 약한 추세 기준 강화)
VOLUME_MA_PERIOD = 20        # 거래량 이동평균 기간
VOLUME_STRONG_MULT = 1.50    # 강한 추세 거래량 배수 (1.45 -> 1.50, 더 높은 거래량 요구)
VOLUME_MIN_THRESHOLD = 1.12  # 최소 거래량 비율 (1.08 -> 1.12, 거래량 조건 강화)

# 물량 조절 파라미터 (자본금 대비 비율) - 극단적으로 보수적
STRONG_TREND_POSITION_RATIO = 0.24  # 강한 추세 시 24% 사용 (미세 증가)
WEAK_TREND_POSITION_RATIO = 0.13   # 약한 추세 시 13% 사용 (미세 증가)
MAX_POSITION_RATIO = 0.29          # 최대 포지션 크기 (미세 증가)

# 진입 조건 파라미터 (승률과 수익률 균형)
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_LONG_MIN = 54.0   # 롱 진입 최소 RSI (55.0 -> 54.0, 조금 완화하여 기회 확대)
RSI_SHORT_MAX = 46.0  # 숏 진입 최대 RSI (45.0 -> 46.0, 조금 완화하여 기회 확대)

# 손절/익절 파라미터 (승률과 수익률 균형 조정)
ATR_PERIOD = 14
STOP_LOSS_ATR_MULT = 0.72   # ATR 배수로 손절 (0.85 -> 0.72, 조금 타이트하게 하여 손실 축소)
TAKE_PROFIT_ATR_MULT = 16.0 # ATR 배수로 익절 (12.0 -> 16.0, 넓혀서 큰 수익 확보, 손익비 약 22:1)
PARTIAL_TAKE_PROFIT_ATR_MULT = 8.0  # 부분 익절 (50%는 빠르게 익절)
PARTIAL_TAKE_PROFIT_RATIO = 0.5     # 부분 익절 비율 (50%)

# 데이터 설정
TEST_MONTHS = 0  # 0이면 전체 데이터 사용 (3년)
CSV_FILE = "ETH_USDT_1m_3Y.csv"
OUTPUT_DIR = Path("backtest_results")


# ================================
# 포지션 정보 클래스
# ================================
class Position:
    def __init__(self, side: str, entry_price: float, entry_time: pd.Timestamp,
                 quantity: float, stop_loss: float, take_profit: float,
                 trend_strength: str, volume_ratio: float, capital_used: float,
                 partial_take_profit: float = None):
        self.side = side  # "long" or "short"
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.quantity = quantity
        self.remaining_quantity = quantity  # 부분 익절 후 남은 수량
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.partial_take_profit = partial_take_profit  # 부분 익절 가격
        self.partial_taken = False  # 부분 익절 여부
        self.trend_strength = trend_strength  # "STRONG" or "WEAK"
        self.volume_ratio = volume_ratio
        self.capital_used = capital_used


# ================================
# 백테스트 클래스
# ================================
class BinanceETHFuturesBacktest:
    def __init__(self):
        self.capital = INITIAL_CAPITAL
        self.position: Optional[Position] = None
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = []
        self.events: List[Dict] = []
        self.total_funding_cost = 0.0
        
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
        
        # +DI, -DI 계산 (0 나누기 방지)
        plus_di = np.where(atr_smooth.values > 0, 100 * (plus_dm_smooth.values / atr_smooth.values), 0)
        minus_di = np.where(atr_smooth.values > 0, 100 * (minus_dm_smooth.values / atr_smooth.values), 0)
        plus_di = pd.Series(plus_di, index=df.index)
        minus_di = pd.Series(minus_di, index=df.index)
        
        # DX 및 ADX (0 나누기 방지)
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
        - "STRONG": ADX >= STRONG_THRESHOLD && volume_ratio >= STRONG_MULT
        - "WEAK": ADX >= WEAK_THRESHOLD && volume_ratio >= MIN_THRESHOLD
        - "NONE": 그 외 (ADX 또는 거래량 조건 불충족)
        """
        adx = row.get('adx', np.nan)
        volume_ratio = row.get('volume_ratio', np.nan)
        
        # ADX와 거래량 모두 필수 확인
        if not np.isfinite(adx) or not np.isfinite(volume_ratio):
            return "NONE", 0.0
        
        # 거래량 최소 기준 확인 (필수)
        if volume_ratio < VOLUME_MIN_THRESHOLD:
            return "NONE", volume_ratio
        
        # 강한 추세: ADX 높고 거래량 많음
        if adx >= ADX_STRONG_THRESHOLD and volume_ratio >= VOLUME_STRONG_MULT:
            return "STRONG", volume_ratio
        
        # 약한 추세: ADX 중간 이상 + 거래량 평균 이상 (둘 다 필수)
        elif adx >= ADX_WEAK_THRESHOLD and volume_ratio >= VOLUME_MIN_THRESHOLD:
            return "WEAK", volume_ratio
        
        # 조건 불충족
        return "NONE", volume_ratio
    
    def calculate_position_size(self, price: float, trend_strength: str) -> Tuple[float, float]:
        """
        추세 강도에 따른 포지션 크기 계산 (유동적 조절)
        Returns: (quantity, capital_used)
        """
        if trend_strength == "STRONG":
            capital_ratio = STRONG_TREND_POSITION_RATIO
        elif trend_strength == "WEAK":
            capital_ratio = WEAK_TREND_POSITION_RATIO
        else:
            return 0.0, 0.0
        
        # 최대 포지션 크기 제한
        capital_ratio = min(capital_ratio, MAX_POSITION_RATIO)
        
        # 사용 가능한 자본
        available_capital = self.capital * capital_ratio
        
        # 레버리지 적용
        leveraged_capital = available_capital * LEVERAGE
        
        # 수량 계산
        quantity = leveraged_capital / price
        
        return quantity, available_capital
    
    def check_entry_signal(self, row: pd.Series, prev_row: pd.Series) -> Tuple[bool, str]:
        """
        진입 신호 확인 (거래량 필수 확인)
        Returns: (should_enter, direction)
        """
        # 추세 강도 확인 (거래량 포함)
        trend_strength, volume_ratio = self.get_trend_strength(row)
        
        if trend_strength == "NONE":
            return False, ""
        
        # 거래량 필수 확인
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
        
        # ADX 방향성 확인 (추세 방향 확인)
        plus_di = row.get('plus_di', np.nan)
        minus_di = row.get('minus_di', np.nan)
        if not all(np.isfinite([plus_di, minus_di])):
            return False, ""
        
        # 롱 신호: EMA 골든크로스 + RSI 조건 + 가격 확인 + ADX 방향성 확인
        ema_cross_up = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
        # 완성된 봉의 종가로 가격 확인 (이전 봉 완성 후 확인 가능)
        price_above_ema = row['close'] > ema_fast
        # ADX 방향성: +DI가 -DI보다 커야 상승 추세
        bullish_adx = plus_di > minus_di
        if ema_cross_up and rsi >= RSI_LONG_MIN and price_above_ema and bullish_adx:
            return True, "long"
        
        # 숏 신호: EMA 데드크로스 + RSI 조건 + 가격 확인 + ADX 방향성 확인
        ema_cross_down = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow
        # 완성된 봉의 종가로 가격 확인 (이전 봉 완성 후 확인 가능)
        price_below_ema = row['close'] < ema_fast
        # ADX 방향성: -DI가 +DI보다 커야 하락 추세
        bearish_adx = minus_di > plus_di
        if ema_cross_down and rsi <= RSI_SHORT_MAX and price_below_ema and bearish_adx:
            return True, "short"
        
        return False, ""
    
    def apply_slippage(self, price: float, side: str) -> float:
        """슬리피지 적용"""
        if side == "long":
            return price * (1 + SLIPPAGE_RATE)
        else:
            return price * (1 - SLIPPAGE_RATE)
    
    def calculate_fee(self, price: float, quantity: float) -> float:
        """수수료 계산"""
        return price * quantity * FEE_RATE
    
    def enter_position(self, row: pd.Series, direction: str, entry_price: float):
        """포지션 진입"""
        trend_strength, volume_ratio = self.get_trend_strength(row)
        
        # 포지션 크기 계산
        quantity, capital_used = self.calculate_position_size(entry_price, trend_strength)
        
        if quantity <= 0:
            return
        
        # 슬리피지 적용
        fill_price = self.apply_slippage(entry_price, direction)
        
        # 수수료
        entry_fee = self.calculate_fee(fill_price, quantity)
        
        # 손절/익절 가격 계산
        atr = row.get('atr', np.nan)
        if not np.isfinite(atr) or atr <= 0:
            return
        
        if direction == "long":
            stop_loss = fill_price - (atr * STOP_LOSS_ATR_MULT)
            take_profit = fill_price + (atr * TAKE_PROFIT_ATR_MULT)
            partial_take_profit = fill_price + (atr * PARTIAL_TAKE_PROFIT_ATR_MULT)
        else:
            stop_loss = fill_price + (atr * STOP_LOSS_ATR_MULT)
            take_profit = fill_price - (atr * TAKE_PROFIT_ATR_MULT)
            partial_take_profit = fill_price - (atr * PARTIAL_TAKE_PROFIT_ATR_MULT)
        
        # 포지션 생성
        entry_time = pd.Timestamp(row['timestamp']) if 'timestamp' in row else row.name
        self.position = Position(
            side=direction,
            entry_price=fill_price,
            entry_time=entry_time,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trend_strength=trend_strength,
            volume_ratio=volume_ratio,
            capital_used=capital_used,
            partial_take_profit=partial_take_profit
        )
        
        # 자본 차감 (수수료만)
        self.capital -= entry_fee
        
        # 이벤트 로그
        self.events.append({
            'timestamp': row.name,
            'event_type': 'ENTRY',
            'side': direction,
            'price': fill_price,
            'quantity': quantity,
            'trend_strength': trend_strength,
            'volume_ratio': volume_ratio,
            'capital_used': capital_used,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'fee': entry_fee,
            'capital_after': self.capital,
            'rsi': row.get('rsi', np.nan),
            'adx': row.get('adx', np.nan),
            'ema_fast': row.get('ema_fast', np.nan),
            'ema_slow': row.get('ema_slow', np.nan)
        })
    
    def check_exit(self, row: pd.Series) -> Tuple[bool, float, str, bool]:
        """
        청산 조건 확인 (부분 익절 포함)
        Returns: (should_exit, exit_price, exit_reason, is_partial)
        """
        if self.position is None:
            return False, 0.0, "", False
        
        high = row.get('high', np.nan)
        low = row.get('low', np.nan)
        close = row.get('close', np.nan)
        
        if not all(np.isfinite([high, low, close])):
            return False, 0.0, "", False
        
        # 손절 확인 (우선순위 1)
        if self.position.side == "long":
            if low <= self.position.stop_loss:
                return True, self.position.stop_loss, "STOP_LOSS", False
        else:  # short
            if high >= self.position.stop_loss:
                return True, self.position.stop_loss, "STOP_LOSS", False
        
        # 부분 익절 확인 (우선순위 2, 아직 부분 익절 안 했으면)
        if not self.position.partial_taken and self.position.partial_take_profit is not None:
            if self.position.side == "long":
                if high >= self.position.partial_take_profit:
                    return True, self.position.partial_take_profit, "PARTIAL_TAKE_PROFIT", True
            else:  # short
                if low <= self.position.partial_take_profit:
                    return True, self.position.partial_take_profit, "PARTIAL_TAKE_PROFIT", True
        
        # 전체 익절 확인 (우선순위 3)
        if self.position.side == "long":
            if high >= self.position.take_profit:
                return True, self.position.take_profit, "TAKE_PROFIT", False
        else:  # short
            if low <= self.position.take_profit:
                return True, self.position.take_profit, "TAKE_PROFIT", False
        
        return False, 0.0, "", False
    
    def exit_position(self, row: pd.Series, exit_price: float, exit_reason: str, is_partial: bool = False):
        """포지션 청산 (부분 익절 지원)"""
        if self.position is None:
            return
        
        # 포지션 정보 저장 (부분 익절 시에도 사용)
        pos_side = self.position.side
        pos_entry = self.position.entry_price
        pos_entry_time = self.position.entry_time
        pos_trend_strength = self.position.trend_strength
        pos_volume_ratio = self.position.volume_ratio
        pos_capital_used = self.position.capital_used
        
        # 슬리피지 적용
        if pos_side == "long":
            fill_price = self.apply_slippage(exit_price, "sell")
        else:
            fill_price = self.apply_slippage(exit_price, "buy")
        
        # 부분 익절 처리
        if is_partial and not self.position.partial_taken:
            exit_quantity = self.position.quantity * PARTIAL_TAKE_PROFIT_RATIO
            self.position.remaining_quantity = self.position.quantity - exit_quantity
            self.position.partial_taken = True
            # 부분 익절 시 capital_used도 비례적으로 조정
            partial_capital_used = pos_capital_used * PARTIAL_TAKE_PROFIT_RATIO
        else:
            exit_quantity = self.position.remaining_quantity if hasattr(self.position, 'remaining_quantity') else self.position.quantity
            partial_capital_used = pos_capital_used
            self.position = None  # 전체 청산
        
        # 손익 계산
        if pos_side == "long":
            gross_pnl = (fill_price - pos_entry) * exit_quantity
        else:
            gross_pnl = (pos_entry - fill_price) * exit_quantity
        
        # 수수료
        exit_fee = self.calculate_fee(fill_price, exit_quantity)
        
        # 펀딩비 계산 (8시간마다, 부분 익절 시에는 비례적으로)
        current_time = pd.Timestamp(row['timestamp']) if 'timestamp' in row.index else pd.Timestamp.now()
        holding_hours = (current_time - pos_entry_time).total_seconds() / 3600
        funding_periods = int(holding_hours / 8)
        funding_cost = partial_capital_used * FUNDING_RATE * funding_periods
        if pos_side == "short":
            funding_cost = -funding_cost  # 숏은 펀딩비 수취 가능
        
        # 순손익
        net_pnl = gross_pnl - exit_fee - funding_cost
        self.capital += net_pnl
        self.total_funding_cost += funding_cost
        
        # 거래 로그
        trade = {
            'entry_time': pos_entry_time,
            'exit_time': row.name,
            'side': pos_side,
            'entry_price': pos_entry,
            'exit_price': fill_price,
            'quantity': exit_quantity,
            'gross_pnl': gross_pnl,
            'entry_fee': partial_capital_used * FEE_RATE,
            'exit_fee': exit_fee,
            'funding_cost': funding_cost,
            'net_pnl': net_pnl,
            'return_pct': (net_pnl / partial_capital_used) * 100 if partial_capital_used > 0 else 0,
            'trend_strength': pos_trend_strength,
            'volume_ratio_entry': pos_volume_ratio,
            'exit_reason': exit_reason,
            'holding_hours': holding_hours,
            'capital_before': self.capital - net_pnl,
            'capital_after': self.capital
        }
        self.trades.append(trade)
        
        # 이벤트 로그
        exit_time = pd.Timestamp(row['timestamp']) if 'timestamp' in row.index else pd.Timestamp.now()
        self.events.append({
            'timestamp': exit_time,
            'event_type': 'EXIT' if not is_partial else 'PARTIAL_EXIT',
            'side': pos_side,
            'price': fill_price,
            'exit_reason': exit_reason,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'funding_cost': funding_cost,
            'capital_after': self.capital
        })
    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        print(f"\n{'='*60}")
        print("백테스팅 시작")
        print(f"{'='*60}")
        print(f"데이터 기간: {df.index[0]} ~ {df.index[-1]}")
        print(f"데이터 개수: {len(df):,}개 봉")
        print(f"초기 자본: {INITIAL_CAPITAL} USDT")
        print(f"레버리지: {LEVERAGE}배")
        print(f"{'='*60}\n")
        
        # 지표 계산
        print("[1/3] 지표 계산 중...")
        df = self.calculate_indicators(df)
        # 필요한 컬럼만 확인 (ADX는 선택적)
        required_cols = ['ema_fast', 'ema_slow', 'rsi', 'atr', 'volume_ratio']
        valid_count = len(df.dropna(subset=required_cols))
        print(f"지표 계산 완료 (유효 데이터: {valid_count:,}개)\n")
        
        # 백테스트 루프 (look-ahead bias 방지: 현재 봉의 데이터만 사용)
        print("[2/3] 백테스트 실행 중...")
        # 필요한 지표 컬럼만 확인 (ADX는 선택적, 기본 OHLCV는 필수)
        required_cols = ['ema_fast', 'ema_slow', 'rsi', 'atr', 'volume_ratio']
        df = df.dropna(subset=required_cols).reset_index()
        total_bars = len(df)
        
        if total_bars == 0:
            print("오류: 유효한 데이터가 없습니다. 지표 계산을 확인해주세요.")
            return self._generate_results()
        
        print(f"유효 데이터: {total_bars:,}개 봉")
        
        for i in range(1, total_bars):
            if i % 10000 == 0:
                pct = (i / total_bars) * 100
                print(f"  진행률: {pct:.1f}% ({i:,}/{total_bars:,}봉)", end="\r")
            
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            # 현재 포지션이 없으면 진입 확인 (이전 봉 완성 후 신호 확인)
            if self.position is None:
                # 이전 봉(prev_row) 기준으로 신호 확인 (look-ahead bias 방지)
                should_enter, direction = self.check_entry_signal(prev_row, df.iloc[i-2] if i >= 2 else prev_row)
                if should_enter:
                    # 현재 봉(다음 봉)의 시가로 진입 (look-ahead bias 방지)
                    if i < total_bars:
                        entry_price = row['open']
                        self.enter_position(row, direction, entry_price)
            else:
                # 포지션이 있으면 청산 확인 (현재 봉의 고가/저가로 체결 확인)
                should_exit, exit_price, exit_reason, is_partial = self.check_exit(row)
                if should_exit:
                    self.exit_position(row, exit_price, exit_reason, is_partial)
            
            # 자산 가치 기록 (미실현 손익 포함)
            if self.position is not None:
                current_price = row['close']
                # 부분 익절 후에는 remaining_quantity 사용
                qty = self.position.remaining_quantity if hasattr(self.position, 'remaining_quantity') else self.position.quantity
                if self.position.side == "long":
                    unrealized_pnl = (current_price - self.position.entry_price) * qty
                else:
                    unrealized_pnl = (self.position.entry_price - current_price) * qty
                equity = self.capital + unrealized_pnl
            else:
                equity = self.capital
            
            self.equity_curve.append(equity)
        
        print(f"\n[3/3] 백테스팅 완료! (총 거래: {len(self.trades)}건)\n")
        
        # 결과 생성
        return self._generate_results()
    
    def _generate_results(self) -> Dict:
        """결과 생성"""
        if len(self.trades) == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'final_capital': self.capital,
                'total_return': 0.0,
                'total_return_pct': 0.0,
                'max_drawdown': self._calculate_max_drawdown(),
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'strong_trend_trades': 0,
                'strong_trend_pnl': 0.0,
                'weak_trend_trades': 0,
                'weak_trend_pnl': 0.0,
                'total_funding_cost': self.total_funding_cost
            }
        
        trades_df = pd.DataFrame(self.trades)
        
        # 기본 통계
        winning_trades = trades_df[trades_df['net_pnl'] > 0]
        losing_trades = trades_df[trades_df['net_pnl'] <= 0]
        
        total_return = self.capital - INITIAL_CAPITAL
        total_return_pct = (total_return / INITIAL_CAPITAL) * 100
        
        # 추세 강도별 성과
        strong_trend_trades = trades_df[trades_df['trend_strength'] == 'STRONG']
        weak_trend_trades = trades_df[trades_df['trend_strength'] == 'WEAK']
        
        # 추가 통계: 손익비, 최대 수익/손실
        avg_win = winning_trades['net_pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = abs(losing_trades['net_pnl'].mean()) if len(losing_trades) > 0 else 0
        risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        max_win = winning_trades['net_pnl'].max() if len(winning_trades) > 0 else 0
        max_loss = losing_trades['net_pnl'].min() if len(losing_trades) > 0 else 0
        
        # 손절/익절별 통계
        stop_loss_trades = trades_df[trades_df['exit_reason'] == 'STOP_LOSS']
        take_profit_trades = trades_df[trades_df['exit_reason'] == 'TAKE_PROFIT']
        
        results = {
            'total_trades': len(trades_df),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'final_capital': self.capital,
            'max_drawdown': self._calculate_max_drawdown(),
            'profit_factor': abs(winning_trades['net_pnl'].sum() / losing_trades['net_pnl'].sum()) if len(losing_trades) > 0 and losing_trades['net_pnl'].sum() < 0 else 0,
            'avg_win': avg_win,
            'avg_loss': losing_trades['net_pnl'].mean() if len(losing_trades) > 0 else 0,
            'risk_reward_ratio': risk_reward_ratio,
            'max_win': max_win,
            'max_loss': max_loss,
            'stop_loss_trades': len(stop_loss_trades),
            'take_profit_trades': len(take_profit_trades),
            'stop_loss_rate': len(stop_loss_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0,
            'take_profit_rate': len(take_profit_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0,
            'strong_trend_trades': len(strong_trend_trades),
            'strong_trend_pnl': strong_trend_trades['net_pnl'].sum() if len(strong_trend_trades) > 0 else 0,
            'weak_trend_trades': len(weak_trend_trades),
            'weak_trend_pnl': weak_trend_trades['net_pnl'].sum() if len(weak_trend_trades) > 0 else 0,
            'total_funding_cost': self.total_funding_cost
        }
        
        return results
    
    def _calculate_max_drawdown(self) -> float:
        """최대 낙폭 계산"""
        if len(self.equity_curve) == 0:
            return 0.0
        
        equity_array = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - peak) / peak
        max_drawdown = abs(np.min(drawdown)) * 100
        
        return max_drawdown
    
    def save_results(self, output_dir: Path, results: Dict):
        """결과를 CSV 파일로 저장 (체계적이고 구체적인 로그)"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 거래 내역 (trades.csv)
        if len(self.trades) > 0:
            trades_df = pd.DataFrame(self.trades)
            trades_df.to_csv(output_dir / 'trades.csv', index=False, encoding='utf-8-sig')
            print(f"  [저장] 거래 내역: trades.csv ({len(trades_df)}건)")
        
        # 2. 이벤트 로그 (events.csv) - 진입/청산 모든 이벤트
        if len(self.events) > 0:
            events_df = pd.DataFrame(self.events)
            events_df.to_csv(output_dir / 'events.csv', index=False, encoding='utf-8-sig')
            print(f"  [저장] 이벤트 로그: events.csv ({len(events_df)}건)")
        
        # 3. 자산 곡선 (equity_curve.csv)
        if len(self.equity_curve) > 0:
            equity_df = pd.DataFrame({
                'bar_index': range(len(self.equity_curve)),
                'equity': self.equity_curve
            })
            equity_df.to_csv(output_dir / 'equity_curve.csv', index=False, encoding='utf-8-sig')
            print(f"  [저장] 자산 곡선: equity_curve.csv ({len(self.equity_curve)}개)")
        
        # 4. 성과 요약 (summary.txt)
        summary_path = output_dir / 'summary.txt'
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("백테스트 성과 요약\n")
            f.write("="*60 + "\n\n")
            f.write(f"초기 자본: {INITIAL_CAPITAL} USDT\n")
            f.write(f"최종 자본: {results['final_capital']:.2f} USDT\n")
            f.write(f"총 수익: {results['total_return']:.2f} USDT\n")
            f.write(f"총 수익률: {results['total_return_pct']:.2f}%\n\n")
            f.write(f"총 거래 수: {results['total_trades']}건\n")
            f.write(f"승리 거래: {results['winning_trades']}건\n")
            f.write(f"손실 거래: {results['losing_trades']}건\n")
            f.write(f"승률: {results['win_rate']:.2f}%\n\n")
            f.write(f"평균 수익: {results['avg_win']:.2f} USDT\n")
            f.write(f"평균 손실: {results['avg_loss']:.2f} USDT\n")
            f.write(f"손익비 (평균 수익/평균 손실): {results.get('risk_reward_ratio', 0):.2f}\n")
            f.write(f"최대 수익 거래: {results.get('max_win', 0):.2f} USDT\n")
            f.write(f"최대 손실 거래: {results.get('max_loss', 0):.2f} USDT\n")
            f.write(f"수익 팩터: {results['profit_factor']:.2f}\n")
            f.write(f"최대 낙폭: {results['max_drawdown']:.2f}%\n\n")
            f.write(f"손절 거래: {results.get('stop_loss_trades', 0)}건 ({results.get('stop_loss_rate', 0):.1f}%)\n")
            f.write(f"익절 거래: {results.get('take_profit_trades', 0)}건 ({results.get('take_profit_rate', 0):.1f}%)\n\n")
            f.write(f"강한 추세 거래: {results['strong_trend_trades']}건, 수익: {results['strong_trend_pnl']:.2f} USDT\n")
            f.write(f"약한 추세 거래: {results['weak_trend_trades']}건, 수익: {results['weak_trend_pnl']:.2f} USDT\n")
            f.write(f"총 펀딩비: {results['total_funding_cost']:.4f} USDT\n")
        print(f"  [저장] 성과 요약: summary.txt")


# ================================
# 데이터 로드 함수
# ================================
def load_data(csv_path: str, months: int = 0) -> pd.DataFrame:
    """데이터 로드 및 필터링 (months=0이면 전체 데이터) + 15분봉으로 리샘플링"""
    print(f"[데이터 로드] {csv_path}")
    df = pd.read_csv(csv_path)
    
    # 타임스탬프 변환
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    
    # 최근 N개월 데이터만 사용 (months > 0일 때만)
    if months > 0:
        end_date = df.index.max()
        start_date = end_date - timedelta(days=months * 30)
        df = df[df.index >= start_date]
        print(f"[데이터 필터링] {start_date.date()} ~ {end_date.date()} ({len(df):,}개 1분봉)")
    else:
        # 전체 데이터 사용
        print(f"[전체 데이터 사용] {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}개 1분봉)")
    
    # 15분봉으로 리샘플링 (노이즈 감소)
    print(f"[리샘플링] 1분봉 -> 15분봉 변환 중...")
    df_resampled = df.resample('15min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    print(f"[리샘플링 완료] {len(df_resampled):,}개 15분봉")
    
    return df_resampled


# ================================
# 메인 함수
# ================================
def main():
    """메인 함수 - 1개월, 3개월, 3년 결과를 동시에 비교"""
    csv_path = Path(__file__).parent / CSV_FILE
    
    # 테스트할 기간들
    test_periods = [
        (1, "1개월"),
        (3, "3개월"),
        (0, "3년 (전체)")
    ]
    
    all_results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n{'='*80}")
    print("다중 기간 백테스트 시작")
    print(f"{'='*80}\n")
    
    # 각 기간별로 백테스트 실행
    for months, period_name in test_periods:
        print(f"\n{'='*80}")
        print(f"[{period_name} 백테스트]")
        print(f"{'='*80}")
        
        # 데이터 로드
        df = load_data(str(csv_path), months=months)
        
        if len(df) == 0:
            print(f"경고: {period_name} 데이터가 없습니다. 건너뜁니다.")
            continue
        
        # 백테스트 실행
        backtest = BinanceETHFuturesBacktest()
        results = backtest.run_backtest(df)
        
        # 결과 저장
        output_dir = Path(__file__).parent / OUTPUT_DIR / f"{timestamp}_{period_name.replace(' ', '_').replace('(', '').replace(')', '')}"
        print(f"\n[{period_name} 결과 저장 중...]")
        backtest.save_results(output_dir, results)
        
        # 결과 저장
        all_results[period_name] = {
            'results': results,
            'output_dir': output_dir,
            'data_period': f"{df.index[0].date()} ~ {df.index[-1].date()}"
        }
    
    # 비교 결과 출력
    print(f"\n\n{'='*80}")
    print("기간별 백테스트 결과 비교")
    print(f"{'='*80}\n")
    
    # 헤더
    print(f"{'지표':<20} {'1개월':>15} {'3개월':>15} {'3년 (전체)':>15}")
    print("-" * 80)
    
    # 각 지표별 비교
    metrics = [
        ('총 거래 수', 'total_trades', '건', 0),
        ('승률', 'win_rate', '%', 2),
        ('최종 자본', 'final_capital', 'USDT', 2),
        ('총 수익률', 'total_return_pct', '%', 2),
        ('최대 낙폭', 'max_drawdown', '%', 2),
        ('수익 팩터', 'profit_factor', '', 2),
        ('평균 수익', 'avg_win', 'USDT', 2),
        ('평균 손실', 'avg_loss', 'USDT', 2),
        ('손익비', 'risk_reward_ratio', '', 2),
        ('손절률', 'stop_loss_rate', '%', 1),
        ('익절률', 'take_profit_rate', '%', 1),
        ('강한 추세 거래', 'strong_trend_trades', '건', 0),
        ('강한 추세 수익', 'strong_trend_pnl', 'USDT', 2),
        ('약한 추세 거래', 'weak_trend_trades', '건', 0),
        ('약한 추세 수익', 'weak_trend_pnl', 'USDT', 2),
    ]
    
    for metric_name, metric_key, unit, decimals in metrics:
        row = f"{metric_name:<20}"
        for period_name in ["1개월", "3개월", "3년 (전체)"]:
            if period_name in all_results:
                value = all_results[period_name]['results'].get(metric_key, 0)
                if decimals == 0:
                    row += f" {value:>14}{unit}"
                else:
                    row += f" {value:>14.{decimals}f}{unit}"
            else:
                row += f" {'N/A':>15}"
        print(row)
    
    # 데이터 기간 정보
    print(f"\n{'데이터 기간':<20} {'1개월':>15} {'3개월':>15} {'3년 (전체)':>15}")
    print("-" * 80)
    row = f"{'':<20}"
    for period_name in ["1개월", "3개월", "3년 (전체)"]:
        if period_name in all_results:
            period_info = all_results[period_name]['data_period']
            row += f" {period_info:>14}"
        else:
            row += f" {'N/A':>15}"
    print(row)
    
    # 상세 결과 출력
    print(f"\n\n{'='*80}")
    print("기간별 상세 결과")
    print(f"{'='*80}\n")
    
    for period_name in ["1개월", "3개월", "3년 (전체)"]:
        if period_name not in all_results:
            continue
            
        results = all_results[period_name]['results']
        output_dir = all_results[period_name]['output_dir']
        
        print(f"\n[{period_name}]")
        print("-" * 80)
        print(f"데이터 기간: {all_results[period_name]['data_period']}")
        print(f"총 거래 수: {results.get('total_trades', 0)}건")
        if results.get('total_trades', 0) > 0:
            print(f"승률: {results.get('win_rate', 0):.2f}%")
            print(f"최종 자본: {results.get('final_capital', INITIAL_CAPITAL):.2f} USDT")
            print(f"총 수익률: {results.get('total_return_pct', 0):.2f}%")
            print(f"최대 낙폭: {results.get('max_drawdown', 0):.2f}%")
            print(f"수익 팩터: {results.get('profit_factor', 0):.2f}")
            print(f"평균 수익: {results.get('avg_win', 0):.2f} USDT")
            print(f"평균 손실: {results.get('avg_loss', 0):.2f} USDT")
            print(f"손익비 (평균 수익/평균 손실): {results.get('risk_reward_ratio', 0):.2f}")
            print(f"최대 수익 거래: {results.get('max_win', 0):.2f} USDT")
            print(f"최대 손실 거래: {results.get('max_loss', 0):.2f} USDT")
            print(f"손절 거래: {results.get('stop_loss_trades', 0)}건 ({results.get('stop_loss_rate', 0):.1f}%)")
            print(f"익절 거래: {results.get('take_profit_trades', 0)}건 ({results.get('take_profit_rate', 0):.1f}%)")
            print(f"강한 추세 거래: {results.get('strong_trend_trades', 0)}건, 수익: {results.get('strong_trend_pnl', 0):.2f} USDT")
            print(f"약한 추세 거래: {results.get('weak_trend_trades', 0)}건, 수익: {results.get('weak_trend_pnl', 0):.2f} USDT")
            print(f"총 펀딩비: {results.get('total_funding_cost', 0):.4f} USDT")
        else:
            print("거래가 발생하지 않았습니다.")
        print(f"결과 폴더: {output_dir}")
    
    print(f"\n{'='*80}")
    print(f"모든 백테스트 완료!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

