"""거래 내역 분석 스크립트"""
import pandas as pd

df = pd.read_csv('backtest_results/20260105_150115_backtest/trades.csv')

wins = df[df['net_pnl'] > 0]
losses = df[df['net_pnl'] <= 0]

print("="*60)
print("수익률 22.90% 원인 분석")
print("="*60)
print(f"\n총 거래: {len(df)}건")
print(f"승리: {len(wins)}건, 손실: {len(losses)}건")
print(f"승률: {len(wins)/len(df)*100:.2f}%")

print(f"\n총 수익: {df['net_pnl'].sum():.2f} USDT")
print(f"승리 거래 합계: {wins['net_pnl'].sum():.2f} USDT")
print(f"손실 거래 합계: {losses['net_pnl'].sum():.2f} USDT")

print(f"\n평균 수익: {wins['net_pnl'].mean():.2f} USDT")
print(f"평균 손실: {losses['net_pnl'].mean():.2f} USDT")

print(f"\n최대 수익: {df['net_pnl'].max():.2f} USDT")
print(f"최대 손실: {df['net_pnl'].min():.2f} USDT")

print(f"\n손익비: {abs(wins['net_pnl'].sum() / losses['net_pnl'].sum()):.2f}:1")

print(f"\n=== 승리 거래 상세 (2건) ===")
print(wins[['entry_time', 'side', 'entry_price', 'exit_price', 'net_pnl', 'return_pct', 'holding_hours', 'exit_reason']].to_string())

print(f"\n=== 손익비 계산 ===")
print(f"손절: 0.36 ATR")
print(f"익절: 31.0 ATR")
print(f"이론적 손익비: {31.0/0.36:.1f}:1")

print(f"\n=== 첫 번째 대승 거래 분석 ===")
first_win = wins.iloc[0]
print(f"진입: {first_win['entry_time']}")
print(f"방향: {first_win['side']}")
print(f"진입가: {first_win['entry_price']:.2f}")
print(f"청산가: {first_win['exit_price']:.2f}")
print(f"가격 변동: {abs(first_win['entry_price'] - first_win['exit_price']):.2f}")
print(f"가격 변동률: {abs(first_win['entry_price'] - first_win['exit_price'])/first_win['entry_price']*100:.2f}%")
print(f"수익: {first_win['net_pnl']:.2f} USDT")
print(f"수익률: {first_win['return_pct']:.2f}%")
print(f"보유 기간: {first_win['holding_hours']:.1f}시간 ({first_win['holding_hours']/24:.1f}일)")


