# AWS 우분투 프리티어 배포 가이드

단계별로 AWS에 거래 봇을 배포하는 방법을 안내합니다.

## 📋 준비사항

- AWS 계정
- EC2 인스턴스 (우분투 프리티어)
- SSH 키 페어 (.pem 파일)
- 바이낸스 API 키 및 시크릿

---

## 1단계: EC2 인스턴스 시작/확인

### 1-1. AWS 콘솔에서 인스턴스 확인

1. AWS 콘솔 로그인 → EC2 서비스 이동
2. "인스턴스" 메뉴에서 인스턴스 상태 확인
3. 인스턴스가 "중지됨" 상태면 "인스턴스 시작" 클릭
4. 인스턴스가 "실행 중" 상태가 될 때까지 대기 (약 1-2분)

### 1-2. 인스턴스 정보 확인

- **퍼블릭 IPv4 주소**: SSH 연결에 필요 (예: `3.34.123.45`)
- **보안 그룹**: 인바운드 규칙에 SSH(포트 22) 허용 확인
- **키 페어 이름**: SSH 접속에 사용할 .pem 파일 이름

---

## 2단계: 로컬 컴퓨터에서 SSH 연결 테스트

### 2-1. Windows (PowerShell 또는 CMD)

```powershell
# .pem 파일이 있는 디렉토리로 이동
cd C:\Users\mycsr\Downloads  # 예시 경로

# SSH 연결 (ubuntu는 기본 사용자명)
ssh -i your-key.pem ubuntu@3.34.123.45

# 또는 ec2-user (Amazon Linux인 경우)
ssh -i your-key.pem ec2-user@3.34.123.45
```

### 2-2. 연결 성공 확인

다음과 같은 메시지가 보이면 성공:
```
Welcome to Ubuntu 22.04 LTS...
ubuntu@ip-xxx-xxx-xxx-xxx:~$
```

---

## 3단계: 서버 환경 설정

### 3-1. 시스템 업데이트

```bash
# 패키지 목록 업데이트
sudo apt update

# 시스템 업그레이드 (선택사항, 시간이 걸릴 수 있음)
sudo apt upgrade -y
```

### 3-2. 필수 패키지 설치

```bash
# Python 3 및 pip 설치
sudo apt install python3 python3-pip python3-venv -y

# Git 설치 (코드 업로드용)
sudo apt install git -y

# 기타 유틸리티
sudo apt install htop nano wget curl -y

# Python 버전 확인
python3 --version
# Python 3.10 이상이어야 합니다
```

---

## 4단계: 코드 업로드 방법 (3가지 중 선택)

### 방법 1: Git 사용 (권장)

#### 4-1. 로컬에서 Git 저장소 준비

```powershell
# 로컬 컴퓨터에서 (Windows PowerShell)
cd C:\Users\mycsr\Coin
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
```

#### 4-2. 서버에서 코드 클론

```bash
# AWS 서버에서
cd /home/ubuntu
git clone https://github.com/your-username/your-repo.git
cd Coin/AutoTrading
```

### 방법 2: SCP로 파일 전송 (간단)

#### 4-1. 로컬에서 파일 압축

```powershell
# Windows PowerShell에서
cd C:\Users\mycsr\Coin
# AutoTrading 폴더만 압축 (WinRAR 또는 7-Zip 사용)
# 또는 PowerShell로:
Compress-Archive -Path AutoTrading -DestinationPath AutoTrading.zip
```

#### 4-2. SCP로 업로드

```powershell
# Windows PowerShell에서
scp -i your-key.pem AutoTrading.zip ubuntu@3.34.123.45:/home/ubuntu/
```

#### 4-3. 서버에서 압축 해제

```bash
# AWS 서버에서
cd /home/ubuntu
unzip AutoTrading.zip
cd AutoTrading
```

### 방법 3: 직접 복사 (작은 파일만)

```powershell
# Windows PowerShell에서 각 파일을 개별적으로 업로드
scp -i your-key.pem AutoTrading/trading_strategy.py ubuntu@3.34.123.45:/home/ubuntu/Coin/AutoTrading/
scp -i your-key.pem AutoTrading/binance_client.py ubuntu@3.34.123.45:/home/ubuntu/Coin/AutoTrading/
# ... 나머지 파일들도 동일하게
```

---

## 5단계: 프로젝트 디렉토리 구조 확인

```bash
# AWS 서버에서
cd /home/ubuntu/Coin/AutoTrading
ls -la

# 다음 파일들이 있어야 합니다:
# - trading_strategy.py
# - binance_client.py
# - live_trading_bot.py
# - config.py
# - main.py
# - requirements.txt
```

---

## 6단계: Python 가상환경 설정 및 의존성 설치

### 6-1. 가상환경 생성

```bash
cd /home/ubuntu/Coin/AutoTrading
python3 -m venv venv
source venv/bin/activate

# 프롬프트에 (venv)가 표시되면 성공
```

### 6-2. pip 업그레이드

```bash
pip install --upgrade pip
```

### 6-3. 필수 패키지만 설치 (프리티어 메모리 제한 고려)

```bash
# 필수 패키지만 설치 (빠르고 가벼움)
pip install ccxt pandas numpy python-dotenv

# 설치 확인
pip list
```

---

## 7단계: 환경 변수 설정

### 7-1. .env 파일 생성

```bash
cd /home/ubuntu/Coin/AutoTrading
nano .env
```

### 7-2. .env 파일 내용 입력

```bash
# 바이낸스 API 설정
BINANCE_API_KEY=your_actual_api_key_here
BINANCE_API_SECRET=your_actual_api_secret_here
BINANCE_TESTNET=true

# 거래 설정
INITIAL_CAPITAL=30.0

# 리스크 관리
MAX_DAILY_LOSS_PCT=10.0
MAX_DRAWDOWN_PCT=20.0
MAX_TRADES_PER_DAY=10

# 안전장치 (처음에는 false로!)
ENABLE_TRADING=false
MIN_BALANCE=10.0

# 로깅
LOG_LEVEL=INFO
```

**저장**: `Ctrl + O` → Enter → `Ctrl + X`

### 7-3. .env 파일 권한 설정 (보안)

```bash
chmod 600 .env  # 소유자만 읽기/쓰기 가능
```

---

## 8단계: 로그 디렉토리 생성

```bash
cd /home/ubuntu/Coin/AutoTrading
mkdir -p logs
chmod 755 logs
```

---

## 9단계: 테스트 실행

### 9-1. 가상환경 활성화 후 테스트

```bash
cd /home/ubuntu/Coin/AutoTrading
source venv/bin/activate
python3 main.py
```

### 9-2. 정상 작동 확인

다음과 같은 메시지가 보이면 성공:
```
============================================================
거래 봇 초기화 중...
============================================================
초기 잔고: 30.00 USDT
캔들 데이터 200개 수집 완료
============================================================
거래 봇 실행 중... (Ctrl+C로 종료)
```

### 9-3. 오류 발생 시 확인사항

```bash
# 로그 확인
cat logs/trading_bot.log

# Python 오류 확인
python3 main.py 2>&1 | head -50
```

---

## 10단계: systemd 서비스 설정 (백그라운드 실행)

### 10-1. 서비스 파일 생성

```bash
sudo nano /etc/systemd/system/trading-bot.service
```

### 10-2. 서비스 파일 내용 입력

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

**저장**: `Ctrl + O` → Enter → `Ctrl + X`

### 10-3. 서비스 활성화 및 시작

```bash
# systemd 재로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅 시 자동 시작)
sudo systemctl enable trading-bot

# 서비스 시작
sudo systemctl start trading-bot

# 상태 확인
sudo systemctl status trading-bot
```

### 10-4. 서비스 관리 명령어

```bash
# 서비스 시작
sudo systemctl start trading-bot

# 서비스 중지
sudo systemctl stop trading-bot

# 서비스 재시작
sudo systemctl restart trading-bot

# 상태 확인
sudo systemctl status trading-bot

# 로그 확인
sudo journalctl -u trading-bot -f
```

---

## 11단계: 모니터링 설정

### 11-1. 로그 확인 방법

```bash
# 실시간 로그 (systemd)
sudo journalctl -u trading-bot -f

# 파일 로그
tail -f /home/ubuntu/Coin/AutoTrading/logs/trading_bot.log

# 오류 로그
tail -f /var/log/trading-bot-error.log

# 최근 100줄만 보기
tail -n 100 /home/ubuntu/Coin/AutoTrading/logs/trading_bot.log
```

### 11-2. 프로세스 확인

```bash
# Python 프로세스 확인
ps aux | grep python

# 메모리 사용량 확인
free -h

# 디스크 사용량 확인
df -h
```

---

## 12단계: 보안 설정 (중요!)

### 12-1. .env 파일 보안

```bash
# .env 파일은 절대 Git에 커밋하지 마세요!
cd /home/ubuntu/Coin/AutoTrading
echo ".env" >> .gitignore
```

### 12-2. 방화벽 설정 (필요시)

```bash
# SSH만 허용 (기본 설정)
sudo ufw status
sudo ufw allow 22/tcp
sudo ufw enable
```

---

## 🔧 문제 해결

### 문제 1: SSH 연결 실패

```bash
# 로컬에서 확인
# 1. 인스턴스가 "실행 중" 상태인지 확인
# 2. 퍼블릭 IP 주소가 올바른지 확인
# 3. 보안 그룹에서 SSH(포트 22) 허용 확인
# 4. .pem 파일 권한 확인 (Windows는 보통 문제없음)
```

### 문제 2: Python 패키지 설치 실패

```bash
# 메모리 부족 시 (프리티어)
# 1. 스왑 메모리 생성
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 2. 패키지를 하나씩 설치
pip install ccxt
pip install pandas
pip install numpy
pip install python-dotenv
```

### 문제 3: 서비스 시작 실패

```bash
# 오류 확인
sudo journalctl -u trading-bot -n 50

# 일반적인 원인:
# 1. 가상환경 경로가 잘못됨
# 2. .env 파일이 없거나 잘못됨
# 3. Python 패키지가 설치되지 않음
```

### 문제 4: API 연결 실패

```bash
# 1. .env 파일의 API 키 확인
cat .env | grep BINANCE

# 2. 인터넷 연결 확인
ping google.com

# 3. 바이낸스 API 상태 확인
curl https://api.binance.com/api/v3/ping
```

---

## ✅ 체크리스트

배포 전 확인사항:

- [ ] EC2 인스턴스가 실행 중
- [ ] SSH 연결 성공
- [ ] Python 3.10+ 설치됨
- [ ] 코드 파일 업로드 완료
- [ ] 가상환경 생성 및 활성화
- [ ] 필수 패키지 설치 완료
- [ ] .env 파일 생성 및 API 키 입력
- [ ] 테스트 실행 성공
- [ ] systemd 서비스 설정 완료
- [ ] 서비스가 정상 실행 중
- [ ] 로그가 정상적으로 기록됨

---

## 🚀 다음 단계

1. **모의 거래로 테스트** (최소 1주일)
   - `ENABLE_TRADING=false` 유지
   - `BINANCE_TESTNET=true` 유지
   - 로그를 정기적으로 확인

2. **실제 거래 전 최종 확인**
   - 백테스트 결과와 모의 거래 결과 비교
   - 리스크 관리 설정 재확인
   - `ENABLE_TRADING=true`로 변경 (신중하게!)

3. **정기 모니터링**
   - 일일 로그 확인
   - 잔고 확인
   - 서비스 상태 확인

---

## 📞 추가 도움

문제가 발생하면:
1. 로그 파일 확인: `logs/trading_bot.log`
2. systemd 로그 확인: `sudo journalctl -u trading-bot`
3. 오류 메시지를 기록하여 검색

