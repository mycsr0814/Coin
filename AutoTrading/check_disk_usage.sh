#!/bin/bash
# 디스크 사용량 확인 스크립트

echo "=========================================="
echo "디스크 사용량 확인"
echo "=========================================="
echo ""

# 전체 디스크 사용량
echo "전체 디스크 사용량:"
df -h /
echo ""

# 로그 디렉토리 크기
echo "로그 디렉토리 크기:"
du -sh /home/ubuntu/Coin/AutoTrading/logs/ 2>/dev/null || echo "로그 디렉토리 없음"
du -sh /var/log/trading-bot*.log 2>/dev/null || echo "systemd 로그 없음"
echo ""

# systemd journal 크기
echo "systemd journal 크기:"
sudo journalctl --disk-usage
echo ""

# 큰 파일 찾기 (상위 10개)
echo "큰 파일 상위 10개:"
sudo find /home/ubuntu/Coin -type f -size +10M -exec ls -lh {} \; 2>/dev/null | head -10
echo ""

# 로그 파일 개수
echo "로그 파일 개수:"
find /home/ubuntu/Coin/AutoTrading/logs -name "*.log*" 2>/dev/null | wc -l
echo ""

echo "=========================================="
echo "정리 명령어:"
echo "=========================================="
echo "오래된 로그 삭제: sudo journalctl --vacuum-time=7d"
echo "로그 크기 제한: sudo journalctl --vacuum-size=100M"
echo "파일 로그 정리: find /home/ubuntu/Coin/AutoTrading/logs -name '*.log.*' -mtime +7 -delete"

