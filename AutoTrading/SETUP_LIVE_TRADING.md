# 실전 거래 모드 설정 가이드

⚠️ **중요**: 바이낸스 테스트넷은 선물 거래를 지원하지 않으므로, 실전 거래 모드로만 실행 가능합니다.

## 1단계: .env 파일 수정

AWS 서버에서 다음 명령어로 .env 파일을 수정하세요:

```bash
cd /home/ubuntu/Coin/AutoTrading
nano .env
```

다음과 같이 수정하세요:

```bash
# 바이낸스 API 설정 (실제 API 키 사용)
BINANCE_API_KEY=your_actual_api_key_here
BINANCE_API_SECRET=your_actual_api_secret_here
BINANCE_TESTNET=false  # 테스트넷 비활성화 (선물 거래 미지원)

# 거래 설정
INITIAL_CAPITAL=30.0

# 리스크 관리
MAX_DAILY_LOSS_PCT=10.0  # 일일 최대 손실 10%
MAX_DRAWDOWN_PCT=20.0    # 최대 드로우다운 20%
MAX_TRADES_PER_DAY=10    # 일일 최대 거래 10회

# ⚠️ 실전 거래 활성화 (신중하게!)
ENABLE_TRADING=true      # true로 변경하면 실제 거래가 실행됩니다!
MIN_BALANCE=10.0         # 최소 잔고 10 USDT

# 로깅
LOG_LEVEL=INFO
```

**저장**: `Ctrl + O` → Enter → `Ctrl + X`

## 2단계: 코드 업데이트

GitHub에서 최신 코드를 가져오세요:

```bash
cd /home/ubuntu/Coin/AutoTrading
git pull origin main
```

또는 수동으로 파일을 업데이트하세요.

## 3단계: 테스트 실행

```bash
# 가상환경 활성화
source venv/bin/activate

# 테스트 실행 (ENABLE_TRADING=false로 먼저 테스트)
python3 main.py
```

정상 작동 확인 후 `Ctrl + C`로 중단하세요.

## 4단계: 실전 거래 활성화 (최종 확인 후)

⚠️ **최종 확인사항**:

1. ✅ API 키가 올바른지 확인
2. ✅ 잔고가 충분한지 확인 (최소 30 USDT 권장)
3. ✅ 리스크 관리 설정 확인
4. ✅ 백테스트 결과 검토 완료
5. ✅ 모의 거래 테스트 완료 (가능한 경우)

**그 다음에만** `.env` 파일에서 `ENABLE_TRADING=true`로 변경하세요.

## 5단계: systemd 서비스 시작

```bash
# 서비스 파일 생성
sudo nano /etc/systemd/system/trading-bot.service
```

다음 내용 입력:

```ini
[Unit]
Description=Binance ETH Futures Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Coin/AutoTrading
Environment="PATH=/home/ubuntu/Coin/AutoTrading/venv/bin:/usr/bin:/usr/local/bin"
ExecStart=/home/ubuntu/Coin/AutoTrading/venv/bin/python3 /home/ubuntu/Coin/AutoTrading/main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/trading-bot.log
StandardError=append:/var/log/trading-bot-error.log

[Install]
WantedBy=multi-user.target
```

서비스 시작:

```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

## 6단계: 모니터링

```bash
# 실시간 로그 확인
sudo journalctl -u trading-bot -f

# 파일 로그 확인
tail -f /home/ubuntu/Coin/AutoTrading/logs/trading_bot.log
```

## ⚠️ 주의사항

1. **작은 자본으로 시작**: 처음에는 최소 금액(30 USDT)으로 시작하세요
2. **정기 모니터링**: 최소 하루에 한 번은 로그를 확인하세요
3. **리스크 관리**: 일일 손실 한도에 도달하면 자동으로 중단됩니다
4. **서비스 중지**: 문제 발생 시 즉시 중지하세요
   ```bash
   sudo systemctl stop trading-bot
   ```

## 문제 해결

### 레버리지 설정 경고
- 레버리지 설정이 실패해도 경고만 표시되고 계속 진행됩니다
- 바이낸스 웹사이트에서 수동으로 레버리지를 설정할 수도 있습니다

### API 연결 오류
- API 키와 시크릿이 올바른지 확인
- 바이낸스 API 상태 확인: https://www.binance.com/en/support/announcement

### 주문 실패
- 잔고 확인
- 최소 주문 금액 확인
- 레버리지 설정 확인

