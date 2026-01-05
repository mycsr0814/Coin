import time
import threading
import winsound
import tkinter as tk
from tkinter import Canvas
import tkinter.scrolledtext as st
from datetime import datetime, timedelta
import pyupbit
import pandas as pd

# ==========================================
# [1] 시간대별 전략 설정 (수정됨: 5배 -> 3배)
# ==========================================
def get_current_strategy():
    now = datetime.now()
    h = now.hour
    m = now.minute

    if h == 9 and m <= 10:
        return {"mode": "MORNING RUSH 🔥", "vol_mul": 3.0, "price_th": 3.0}
    elif h >= 23 or h < 1:
        return {"mode": "US MARKET 🌙", "vol_mul": 3.0, "price_th": 2.5}
    elif 3 <= h < 7:
        return {"mode": "DAWN WHALE 🕵️", "vol_mul": 3.0, "price_th": 1.5}
    else:
        # [수정 완료] 기존 5.0 -> 3.0으로 변경
        return {"mode": "NORMAL SCAN 🙂", "vol_mul": 3.0, "price_th": 2.0}

# ==========================================
# [2] 코인 목록 조회
# ==========================================
def get_target_tickers():
    try:
        return pyupbit.get_tickers(fiat="KRW")
    except Exception:
        return []

# ==========================================
# [3] 감시 로직
# ==========================================
def check_surge(watch_list, cooldowns, status_callback=None, alert_callback=None, log_callback=None):
    if not watch_list: return

    strategy = get_current_strategy()
    
    if status_callback:
        status_text = f"[{strategy['mode']}] Vol x{strategy['vol_mul']} / Price {strategy['price_th']}%"
        status_callback(status_text)

    for ticker in watch_list:
        try:
            if ticker in cooldowns:
                if datetime.now() < cooldowns[ticker]:
                    # 쿨다운 중일 때는 로그 생략 (너무 시끄러움 방지)
                    continue
                else:
                    del cooldowns[ticker]

            df = pyupbit.get_ohlcv(ticker, interval="minute1", count=10)
            
            if df is None or len(df) < 5: 
                time.sleep(0.05)
                continue

            vol_avg = df['volume'].mean()
            if vol_avg == 0: vol_avg = 1

            # 직전 봉(iloc[-2])과 현재 봉(iloc[-1]) 검사
            candidates = [df.iloc[-2], df.iloc[-1]]

            for i, candle in enumerate(candidates):
                current_price = float(candle['close'])
                open_price = float(candle['open'])
                current_vol = float(candle['volume'])
                
                pct_change = ((current_price - open_price) / open_price) * 100
                vol_ratio = current_vol / vol_avg

                # 조건 충족 여부
                is_vol_ok = vol_ratio > strategy['vol_mul']
                is_price_ok = pct_change >= strategy['price_th']
                
                # 로그 출력 (현재 진행중인 봉만)
                if log_callback and i == 1:
                    if vol_ratio > 2.0 or abs(pct_change) > 0.5:
                        msg = f"Vol x{vol_ratio:.1f} | Price {pct_change:.2f}%"
                        log_callback(ticker, vol_ratio, pct_change, msg)

                # 감지 성공
                if is_vol_ok and is_price_ok:
                    symbol_name = ticker.replace("KRW-", "")
                    
                    if log_callback: 
                        log_callback(ticker, vol_ratio, pct_change, "🚨 급등 포착 성공! 🚨")
                    
                    if alert_callback:
                        alert_callback(symbol_name, current_price, pct_change)
                    
                    cooldowns[ticker] = datetime.now() + timedelta(minutes=10)
                    break 

            time.sleep(0.1) 

        except Exception as e:
            print(f"Logic Error: {e}")
            time.sleep(0.1)

# ==========================================
# [4] GUI 클래스
# ==========================================
class CoinBreakoutGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Upbit Smart Signal")
        self.root.geometry("450x750")
        
        self.bg_color = "#0b162a"
        self.text_white = "#ffffff"
        self.text_grey = "#969da8"
        self.up_red = "#d24f45"
        self.btn_blue = "#093687"
        
        self.root.configure(bg=self.bg_color)
        
        self.is_running = False
        self.watch_list = []
        self.cooldowns = {} 
        self.last_scan_time = datetime.now() - timedelta(minutes=10)
        
        self.log_window = None
        self.log_text_widget = None

        self.setup_ui()
        
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg=self.bg_color, height=60)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        tk.Label(header_frame, text="스마트 급등 포착", font=("Malgun Gothic", 16, "bold"), fg=self.text_white, bg=self.bg_color).place(x=20, rely=0.5, anchor="w")
        
        self.status_frame = tk.Frame(self.root, bg=self.bg_color)
        self.status_frame.pack(fill=tk.X, padx=20, pady=(10, 10))
        
        self.watch_count_label = tk.Label(self.status_frame, text="연결 대기 중...", font=("Malgun Gothic", 10), fg=self.text_grey, bg=self.bg_color, anchor="w")
        self.watch_count_label.pack(fill=tk.X)

        self.status_label = tk.Label(self.status_frame, text="READY", font=("Arial", 11, "bold"), fg="#2ecc71", bg=self.bg_color, anchor="w")
        self.status_label.pack(fill=tk.X, pady=(2,0))

        btn_frame = tk.Frame(self.root, bg=self.bg_color)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 15))

        self.start_button = tk.Button(btn_frame, text="감시 시작", font=("Malgun Gothic", 12, "bold"), bg=self.btn_blue, fg='white', relief=tk.FLAT, cursor='hand2', command=self.toggle_detection)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 5))

        self.log_button = tk.Button(btn_frame, text="로그(Log)", font=("Malgun Gothic", 12, "bold"), bg="#2c3e50", fg='white', relief=tk.FLAT, cursor='hand2', command=self.open_log_window)
        self.log_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, ipady=5, padx=(5, 0))
        
        col_frame = tk.Frame(self.root, bg=self.bg_color)
        col_frame.pack(fill=tk.X, padx=20)
        tk.Label(col_frame, text="코인명", fg=self.text_grey, bg=self.bg_color, font=("Malgun Gothic", 9)).pack(side=tk.LEFT)
        tk.Label(col_frame, text="등락률/현재가", fg=self.text_grey, bg=self.bg_color, font=("Malgun Gothic", 9)).pack(side=tk.RIGHT)

        list_frame = tk.Frame(self.root, bg=self.bg_color)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(5, 0))
        
        self.canvas = Canvas(list_frame, bg=self.bg_color, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.bg_color)
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=430)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.empty_label = tk.Label(self.scrollable_frame, text="데이터 수신 대기 중...", font=("Malgun Gothic", 10), fg=self.text_grey, bg=self.bg_color)
        self.empty_label.pack(pady=50)

    def open_log_window(self):
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = tk.Toplevel(self.root)
            self.log_window.title("실시간 감시 로그")
            self.log_window.geometry("400x300")
            self.log_window.configure(bg="black")
            self.log_text_widget = st.ScrolledText(self.log_window, bg="black", fg="#00ff00", font=("Consolas", 10), state='disabled')
            self.log_text_widget.pack(fill=tk.BOTH, expand=True)
            self.append_log(">>> 시스템 로그가 시작되었습니다.")

    def append_log(self, message):
        if self.log_window and self.log_text_widget and self.log_window.winfo_exists():
            self.log_text_widget.configure(state='normal')
            timestamp = datetime.now().strftime("[%H:%M:%S]")
            self.log_text_widget.insert(tk.END, f"{timestamp} {message}\n")
            self.log_text_widget.see(tk.END)
            self.log_text_widget.configure(state='disabled')

    def log_updater(self, ticker, vol, price, msg):
        coin = ticker.replace("KRW-", "")
        formatted_msg = f"{coin:<5} | {msg}"
        self.root.after(0, lambda: self.append_log(formatted_msg))

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
    def add_coin_card(self, symbol, price, pct_change):
        try:
            # 1. '데이터 수신 대기 중' 라벨이 있으면 제거
            if hasattr(self, 'empty_label') and self.empty_label.winfo_exists():
                self.empty_label.destroy()
            
            # 2. 새로운 카드(Row) 생성
            row = tk.Frame(self.scrollable_frame, bg=self.bg_color, bd=0, pady=8)
            inner = tk.Frame(row, bg=self.bg_color)
            inner.pack(fill=tk.X, padx=20)
            
            left_frame = tk.Frame(inner, bg=self.bg_color)
            left_frame.pack(side=tk.LEFT)
            tk.Label(left_frame, text=symbol, font=("Arial", 11, "bold"), fg=self.text_white, bg=self.bg_color, anchor="w").pack(anchor="w")
            tk.Label(left_frame, text=datetime.now().strftime('%H:%M:%S'), font=("Arial", 9), fg=self.text_grey, bg=self.bg_color, anchor="w").pack(anchor="w")

            right_frame = tk.Frame(inner, bg=self.bg_color)
            right_frame.pack(side=tk.RIGHT)
            tk.Label(right_frame, text=f"+{pct_change:.2f}%", font=("Arial", 11, "bold"), fg=self.up_red, bg=self.bg_color, anchor="e").pack(anchor="e")
            
            price_val = float(price)
            price_text = f"{price_val:,.0f}" if price_val >= 100 else f"{price_val:.2f}"
            tk.Label(right_frame, text=price_text, font=("Arial", 10), fg=self.text_white, bg=self.bg_color, anchor="e").pack(anchor="e")

            tk.Frame(row, bg="#252b36", height=1).pack(fill=tk.X, side=tk.BOTTOM, pady=(8,0))

            # ==========================================
            # [수정 핵심] 최신 알림을 리스트 '맨 위'로 올리는 로직
            # ==========================================
            children = self.scrollable_frame.winfo_children()
            
            # children[-1]은 방금 만든 row 자신입니다.
            # children[-2]가 바로 직전에 만든(현재 화면 최상단에 있는) 카드입니다.
            # 따라서 직전 카드(-2) 앞에 row를 끼워 넣어야(before) 시각적으로 맨 위에 옵니다.
            if len(children) >= 2:
                row.pack(fill=tk.X, before=children[-2])
            else:
                row.pack(fill=tk.X) # 첫 번째 카드인 경우 그냥 추가

            # ==========================================
            # [수정 핵심] 화면 강제 갱신 및 스크롤 최상단 이동
            # ==========================================
            # 리스트 40개 제한
            if len(children) > 40:
                # 리스트 맨 뒤(화면상 맨 아래)에 있는 위젯 삭제
                # children[0]이 가장 오래된 위젯일 확률이 높음 (winfo_children은 생성순)
                children[0].destroy()

            self.scrollable_frame.update_idletasks() # 레이아웃 즉시 계산
            self.canvas.configure(scrollregion=self.canvas.bbox("all")) # 스크롤 영역 재설정
            self.canvas.yview_moveto(0) # 스크롤바를 강제로 맨 위로 올림 (중요!)

        except Exception as e:
            print(f"GUI Error: {e}")

    def play_alert_sound(self):
        def beep():
            winsound.Beep(1500, 100)
            time.sleep(0.05)
            winsound.Beep(1500, 100)
        threading.Thread(target=beep, daemon=True).start()
            
    def safe_alert_callback(self, symbol, price, pct_change):
        self.root.after(0, self.play_alert_sound)
        self.root.after(0, self.add_coin_card, symbol, price, pct_change)
    
    def update_status_text(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))

    def toggle_detection(self):
        if not self.is_running:
            self.is_running = True
            self.start_button.config(text="중지", bg='#c84a31') 
            self.watch_count_label.config(text="서버 연결 중...")
            threading.Thread(target=self.detection_loop, daemon=True).start()
        else:
            self.is_running = False
            self.start_button.config(text="다시 시작", bg=self.btn_blue)
            self.status_label.config(text="MONITORING STOPPED")
            self.watch_count_label.config(text="대기 중")
            
    def detection_loop(self):
        while self.is_running:
            try:
                if datetime.now() - self.last_scan_time >= timedelta(minutes=5) or not self.watch_list:
                    new_list = get_target_tickers()
                    if new_list:
                        self.watch_list = new_list
                        self.root.after(0, lambda l=len(new_list): self.watch_count_label.config(text=f"KRW 마켓 {l}개 종목 스캔 중"))
                        self.log_updater("SYSTEM", 0, 0, f"종목 리스트 갱신 완료 ({len(new_list)}개)")
                    self.last_scan_time = datetime.now()

                check_surge(self.watch_list, self.cooldowns, 
                            status_callback=self.update_status_text, 
                            alert_callback=self.safe_alert_callback,
                            log_callback=self.log_updater)
                time.sleep(1)
            except Exception as e:
                print(f"Loop Error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = CoinBreakoutGUI(root)
    root.mainloop()