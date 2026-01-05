# 바이낸스 ETH 선물 자동 거래 봇 (실전)

백테스트 코드를 기반으로 한 실전 거래 봇입니다. AWS에서 24시간 실행 가능합니다.

## 📁 파일 구조

```
AutoTrading/
├── trading_strategy.py      # 공통 전략 로직 (지표 계산, 신호 확인)
├── binance_client.py        # 바이낸스 API 클라이언트
├── live_trading_bot.py       # 실전 거래 봇 메인 클래스
├── config.py                # 설정 파일
├── main.py                  # 메인 실행 파일
└── README_LIVE_TRADING.md   # 이 파일
```

## 🚀 시작하기

### 1. 환경 변수 설정

`.env` 파일을 생성하고 다음 내용을 입력하세요:

```bash
# 바이낸스 API 설정
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true  # 테스트넷 사용 여부 (true/false)

# 거래 설정
INITIAL_CAPITAL=30.0  # 초기 자본금 (USDT)

# 리스크 관리
MAX_DAILY_LOSS_PCT=10.0  # 일일 최대 손실 %
MAX_DRAWDOWN_PCT=20.0  # 최대 드로우다운 %
MAX_TRADES_PER_DAY=10  # 일일 최대 거래 횟수

# 안전장치
ENABLE_TRADING=false  # 실제 거래 활성화 여부 (true/false)
MIN_BALANCE=10.0  # 최소 잔고 (이하일 경우 거래 중단)

# 로깅
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 실행

```bash
# 모의 거래 모드 (ENABLE_TRADING=false)
python main.py

# 실제 거래 모드 (ENABLE_TRADING=true) - 주의!
python main.py
```

## ⚙️ AWS 배포

### 1. EC2 인스턴스 설정

- Ubuntu 22.04 LTS 권장
- 최소 t2.micro (무료 티어 가능)
- 보안 그룹: 아웃바운드 HTTPS 허용

### 2. 환경 설정

```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# Python 3.10+ 설치
sudo apt install python3 python3-pip -y

# 프로젝트 클론 및 이동
cd /home/ubuntu
git clone <your-repo>
cd Coin/AutoTrading

# 의존성 설치
pip3 install -r requirements.txt

# 환경 변수 설정 (시스템 환경 변수 또는 .env 파일)
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"
export BINANCE_TESTNET="true"
export ENABLE_TRADING="false"  # 처음에는 false로 시작
```

### 3. systemd 서비스 설정

`/etc/systemd/system/trading-bot.service` 파일 생성:

```ini
[Unit]
Description=Binance ETH Futures Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Coin/AutoTrading
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 /home/ubuntu/Coin/AutoTrading/main.py
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

### 4. 로그 확인

```bash
# 실시간 로그 확인
sudo journalctl -u trading-bot -f

# 또는 파일 로그
tail -f /var/log/trading-bot.log
tail -f logs/trading_bot.log
```

## 🛡️ 안전장치

1. **모의 거래 모드**: 기본값은 `ENABLE_TRADING=false`
2. **일일 손실 제한**: `MAX_DAILY_LOSS_PCT` 설정값 초과 시 자동 중단
3. **드로우다운 제한**: `MAX_DRAWDOWN_PCT` 설정값 초과 시 자동 중단
4. **최소 잔고**: `MIN_BALANCE` 이하일 경우 거래 중단
5. **일일 거래 횟수 제한**: `MAX_TRADES_PER_DAY` 설정값 초과 시 거래 중단

## 📊 모니터링

- 로그 파일: `logs/trading_bot.log`
- 실시간 로그: 콘솔 출력
- systemd 로그: `sudo journalctl -u trading-bot`

## ⚠️ 주의사항

1. **처음에는 반드시 테스트넷으로 테스트하세요**
   - `BINANCE_TESTNET=true`
   - `ENABLE_TRADING=false` (모의 거래)

2. **실제 거래 전 충분한 테스트**
   - 최소 1주일 이상 모의 거래로 테스트
   - 다양한 시장 상황에서 검증

3. **API 키 보안**
   - API 키는 환경 변수로 관리
   - `.env` 파일은 `.gitignore`에 추가
   - API 키 권한은 최소한으로 설정 (거래만 허용)

4. **리스크 관리**
   - 작은 자본으로 시작
   - 손실 한도 설정 필수
   - 정기적인 모니터링

## 🔧 문제 해결

### 연결 오류
- 네트워크 연결 확인
- 바이낸스 API 상태 확인
- 방화벽 설정 확인

### 주문 실패
- 잔고 확인
- 레버리지 설정 확인
- 최소 주문 금액 확인

### 로그 확인
```bash
# 최근 오류 확인
grep ERROR logs/trading_bot.log | tail -20

# 특정 날짜 로그
grep "2026-01-05" logs/trading_bot.log
```

## 📝 라이센스

이 코드는 교육 목적으로 제공됩니다. 실제 거래에 사용할 경우 모든 책임은 사용자에게 있습니다.

