#!/bin/bash
# 빠른 배포 스크립트
# AWS 우분투 서버에서 실행

set -e  # 오류 발생 시 중단

echo "=========================================="
echo "거래 봇 빠른 배포 스크립트"
echo "=========================================="

# 1. 시스템 업데이트
echo "[1/8] 시스템 업데이트 중..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git htop nano

# 2. 프로젝트 디렉토리 확인
echo "[2/8] 프로젝트 디렉토리 확인..."
if [ ! -d "/home/ubuntu/Coin/AutoTrading" ]; then
    echo "오류: /home/ubuntu/Coin/AutoTrading 디렉토리를 먼저 생성하세요"
    exit 1
fi

cd /home/ubuntu/Coin/AutoTrading

# 3. 가상환경 생성
echo "[3/8] 가상환경 생성 중..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 4. pip 업그레이드
echo "[4/8] pip 업그레이드 중..."
pip install --upgrade pip

# 5. 필수 패키지 설치
echo "[5/8] 필수 패키지 설치 중..."
pip install ccxt pandas numpy python-dotenv

# 6. 로그 디렉토리 생성
echo "[6/8] 로그 디렉토리 생성 중..."
mkdir -p logs
chmod 755 logs

# 7. .env 파일 확인
echo "[7/8] .env 파일 확인 중..."
if [ ! -f ".env" ]; then
    echo "경고: .env 파일이 없습니다. 수동으로 생성해주세요."
    echo "예시:"
    echo "BINANCE_API_KEY=your_key"
    echo "BINANCE_API_SECRET=your_secret"
    echo "BINANCE_TESTNET=true"
    echo "ENABLE_TRADING=false"
else
    chmod 600 .env
    echo ".env 파일이 존재합니다."
fi

# 8. 테스트 실행
echo "[8/8] 테스트 실행 중..."
echo "=========================================="
echo "배포 완료!"
echo "=========================================="
echo ""
echo "다음 명령어로 테스트하세요:"
echo "  cd /home/ubuntu/Coin/AutoTrading"
echo "  source venv/bin/activate"
echo "  python3 main.py"
echo ""
echo "systemd 서비스 설정은 README를 참고하세요."

