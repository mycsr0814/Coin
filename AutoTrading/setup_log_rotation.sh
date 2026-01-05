#!/bin/bash
# 로그 로테이션 설정 스크립트

echo "로그 로테이션 설정 중..."

# 1. systemd journal 로그 크기 제한 설정
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/trading-bot.conf > /dev/null <<EOF
[Journal]
SystemMaxUse=100M
SystemKeepFree=200M
SystemMaxFileSize=10M
MaxRetentionSec=7day
EOF

# 2. logrotate 설정 (파일 로그용)
sudo tee /etc/logrotate.d/trading-bot > /dev/null <<EOF
/home/ubuntu/Coin/AutoTrading/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload trading-bot > /dev/null 2>&1 || true
    endscript
}

/var/log/trading-bot.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload trading-bot > /dev/null 2>&1 || true
    endscript
}

/var/log/trading-bot-error.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload trading-bot > /dev/null 2>&1 || true
    endscript
}
EOF

# 3. systemd journal 재시작
sudo systemctl restart systemd-journald

echo "로그 로테이션 설정 완료!"
echo ""
echo "설정 내용:"
echo "- systemd journal: 최대 100MB, 7일 보관"
echo "- 파일 로그: 일일 로테이션, 7일 보관, 압축"
echo ""
echo "현재 디스크 사용량 확인:"
df -h /

