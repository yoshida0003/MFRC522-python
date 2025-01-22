import RPi.GPIO as GPIO
import MFRC522
import signal
import time
import mysql.connector  # MySQLライブラリのインポート
import uuid
import hashlib
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # CORSを有効にする
socketio = SocketIO(app, cors_allowed_origins="*")

continue_reading = True

# Capture SIGINT for cleanup when the script is aborted
def end_read(signal, frame):
    global continue_reading
    print("Ctrl+C captured, ending read.")
    continue_reading = False
    GPIO.cleanup()

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# GPIOの初期化
GPIO.setmode(GPIO.BOARD)

# MySQLデータベースへの接続設定
db_config = {
    'user': 'root',  # MySQLのユーザー名
    'password': 'yossy0508',  # MySQLのパスワード
    'host': 'localhost',
    'database': 'io',
}

# MySQLに接続
try:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
except mysql.connector.Error as err:
    print(f'Error: {err}')

# GPIOのモードをBOARDに設定
GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

# サーボモータ制御用のピンの設定
servo_pin = 12  # BOARDモードでの12番ピン

# GPIOのモードとピンの設定
GPIO.setup(servo_pin, GPIO.OUT)

# PWMの設定
pwm = GPIO.PWM(servo_pin, 50)  # 50Hz
pwm.start(0)

# LEDピンの設定 (BOARDモード)
LED_RED = 5   # BOARDモードでの5番ピン
LED_GREEN = 7 # BOARDモードでの7番ピン
RFID_UID = [3, 176, 167, 19, 7]
password = "yossy0508"

def set_angle(angle):   
    duty = angle / 18 + 2
    GPIO.output(servo_pin, True)
    pwm.ChangeDutyCycle(duty)
    time.sleep(1)
    GPIO.output(servo_pin, False)
    pwm.ChangeDutyCycle(0)

def turn_led_on(led):
    GPIO.setup(led, GPIO.OUT)
    GPIO.output(led, GPIO.HIGH)

def turn_led_off(led):
    GPIO.setup(led, GPIO.OUT)
    GPIO.output(led, GPIO.LOW)

def turn_red_on():
    turn_led_off(LED_GREEN)
    turn_led_on(LED_RED)

def turn_green_on():
    turn_led_off(LED_RED)
    turn_led_on(LED_GREEN)

def blink_red(duration):
    for _ in range(duration * 2):
        turn_led_on(LED_RED)
        time.sleep(0.5)
        turn_led_off(LED_RED)
        time.sleep(0.5)
    turn_red_on()  # 最後に赤ランプを点灯したままにする

# Create an object of the class MFRC522
MIFAREReader = MFRC522.MFRC522()

@app.route('/scan', methods=['POST'])
def scan():
    global continue_reading
    continue_reading = True
    while continue_reading:
        # Scan for cards    
        (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

        # If a card is found
        if status == MIFAREReader.MI_OK:
            print("Card detected")
        
            # Get the UID of the card
            (status, uid) = MIFAREReader.MFRC522_Anticoll()

            # If we have the UID, continue
            if status == MIFAREReader.MI_OK:
                # UIDをカンマ区切りの文字列に変換
                uid_str = ','.join(map(str, uid))
                
                # データベースにUIDが存在するか確認
                cursor.execute("SELECT name FROM auth WHERE rfid_uid = %s", (uid_str,))
                result = cursor.fetchone()

                if result:
                    name = result[0]
                    print('バッジ {} が許可されました！名前: {}'.format(uid_str, name))  # バッジが許可されたことを表示

                    turn_green_on()  # 緑ランプを点灯
                    turn_led_off(LED_RED)  # 赤ランプを消灯

                    # サーボを90度に設定
                    set_angle(90)
                    time.sleep(10)
                    set_angle(0)

                    turn_red_on()  # サーボモータが元の位置に戻った後に赤ランプを点灯
                    turn_led_off(LED_GREEN)  # 緑ランプを消灯

                    # フロントエンドに結果を送信
                    socketio.emit('scan_result', {'message': 'おかえりなさい！', 'name': name})
                    return jsonify({'message': 'おかえりなさい！', 'name': name}), 200
                else:
                    print('バッジ {} は許可されていません！'.format(uid_str))
                    blink_red(10)  # 10秒間赤ランプを点滅
                    return jsonify({'message': 'バッジ {} は許可されていません！'.format(uid_str)}), 403

    return jsonify({'message': 'スキャンが中断されました'}), 500

if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        pass
    finally:
        cursor.close()
        connection.close()
        pwm.stop()
        GPIO.cleanup()

        # プログラム終了時にLEDを消灯