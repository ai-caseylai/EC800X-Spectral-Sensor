# 水耕感測與控制系統 — 完整計畫書

## Hydroponic Sensor & Control System for EC800X QuecDuino (QuecPython)

---

## 一、專案概述

基於移遠 EC800X QuecDuino 開發板，搭建一套水耕栽培的感測與控制系統。系統整合光譜感測、水質監測、流量/壓力偵測、泵閥控制、以及 ESP32 雙 MCU 通訊，可即時監控水耕環境並自動化控制水流。

### 系統架構

```
                    ┌─────────────────────────────────┐
                    │        EC800X QuecDuino          │
                    │       (QuecPython MCU)           │
                    │                                  │
  I2C Bus ◄────────┤  GPIO66 (SDA)    GPIO67 (SCL)    │
                    │                                  │
  UART1  ◄─────────┤  TX / RX          → BA121        │
  UART2  ◄─────────┤  TX / RX          → ESP32        │
                    │                                  │
  ADC0   ◄─────────┤  ADC0 (pH)                       │
  ADC1   ◄─────────┤  ADC1 (Pressure)                 │
                    │                                  │
  GPIO   ◄─────────┤  GPIO25 (Valve)                  │
  GPIO   ◄─────────┤  GPIO26 (Flow Sensor)            │
  GPIO   ◄─────────┤  GPIO27 (Pump-A DIR)             │
  GPIO   ◄─────────┤  GPIO28 (Pump-B DIR)             │
  PWM    ◄─────────┤  PWM0 (Pump-A Speed)             │
  PWM    ◄─────────┤  PWM1 (Pump-B Speed)             │
  GPIO   ◄─────────┤  GPIO29 (Water Pump Relay)       │
  GPIO   ◄─────────┤  GPIO30 (Grow Light Relay)       │
  UART2  ◄─────────┤  TX / RX          → ESP32        │
                    └──────────────┬───────────────────┘
                                   │
                                   │ UART2 115200bps
                                   │ (JSON protocol)
                                   │
                    ┌──────────────▼───────────────────┐
                    │           ESP32                   │
                    │       (ESPHome / ESP-claw)        │
                    │                                   │
                    │  WiFi / MQTT → Home Assistant     │
                    │  遠端監控 + 控制指令下发            │
                    └───────────────────────────────────┘
```

---

## 二、硬體清單

| # | 感測器/控制器 | 型號 | 介面 | I2C 地址 | 功能 |
|---|-------------|------|------|---------|------|
| 1 | NIR 光譜感測器 | AS7263 | I2C | 0x49 | 近紅外光譜 610-860nm，6 通道 |
| 2 | 可見光光譜感測器 | AS7341 | I2C | 0x39 | 可見光+近紅外 390-890nm，10 通道 |
| 3 | 導電度+溫度感測器 | BA121 | UART1 9600bps | — | EC 導電度 (μS/cm) + 水溫 (°C) |
| 4 | pH 感測器 | PH4502C | ADC0 | — | pH 值 (0-14) |
| 5 | 水壓感測器 | XDB401/USP10 | ADC1 | — | 水壓 (0-1.2 MPa) |
| 6 | 霍爾效應流量計 | YF-S201 相容 | GPIO IRQ | — | 水流量 (L/min) + 累計流量 |
| 7 | 電磁閥 | 通用 5V 繼電器 | GPIO | — | ON/OFF 水流控制 |
| 8 | 蠕動泵 A | 5V 微型蠕動泵 | GPIO+PWM | — | 營養液泵，方向+流速控制 |
| 9 | 蠕動泵 B | 5V 微型蠕動泵 | GPIO+PWM | — | pH 調節泵，方向+流速控制 |
| 10 | 總水泵繼電器 | 通用繼電器模組 | GPIO | — | 總水泵 ON/OFF 控制 |
| 11 | 種植燈繼電器 | 通用繼電器模組 | GPIO | — | 種植燈 ON/OFF 控制 |
| 12 | ESP32 通訊模組 | ESP32 / ESP32-S3 | UART2 | — | WiFi/MQTT 橋接，遠端監控 |

### UART 資源分配

| UART | 用途 | 波特率 | 狀態 |
|------|------|--------|------|
| UART0 | Debug / REPL | 115200 | 開發用 |
| UART1 | BA121 導電度感測器 | 9600 | 已佔用 |
| **UART2** | **ESP32 通訊橋接** | **115200** | **ESP32 專用** |

---

## 三、接線圖

### 3.1 I2C 匯流排（AS7341 + AS7263 共用）

```
EC800X QuecDuino          AS7341 (0x39)         AS7263 (0x49)
┌──────────┐              ┌──────────┐          ┌──────────┐
│ Pin 16   │─── SDA ──────┤ SDA      │──────────┤ SDA      │
│ GPIO66   │              │          │          │          │
│ Pin 17   │─── SCL ──────┤ SCL      │──────────┤ SCL      │
│ GPIO67   │              │          │          │          │
│ 3.3V     │─── VCC ──────┤ VCC      │──────────┤ VCC      │
│ GND      │─── GND ──────┤ GND      │──────────┤ GND      │
└──────────┘              └──────────┘          └──────────┘
               I2C0 @ 400KHz (FAST_MODE)
```

### 3.2 UART1（BA121 導電度感測器）

```
EC800X QuecDuino          BA121 模組
┌──────────┐              ┌──────────┐
│ UART1 TX │──────────────┤ RX (Pin5)│
│ UART1 RX │──────────────┤ TX (Pin4)│
│ 5V       │──────────────┤ VCC      │
│ GND      │──────────────┤ GND      │
└──────────┘              └──────────┘
               UART1 @ 9600bps, 8N1
```

### 3.3 UART2（ESP32 通訊橋接）

```
EC800X QuecDuino          ESP32
┌──────────┐              ┌──────────┐
│ UART2 TX │──────────────┤ RX       │
│ UART2 RX │──────────────┤ TX       │
│ GND      │──────────────┤ GND      │
└──────────┘              └──────────┘
               UART2 @ 115200bps, 8N1
               JSON line protocol (newline delimited)

  注意：
  - TX/RX 交叉連接（EC800X TX → ESP32 RX）
  - 雙方 GND 必須相連
  - 邏輯電平均為 3.3V，無需電平轉換
  - ESP32 端需運行對應的 UART 接收程式
```

### 3.4 ADC（pH + 水壓，需分壓電路）

PH4502C 和壓力感測器輸出 0-5V，EC800X ADC 最大接受 1.3V，
必須使用電阻分壓（R1=33KΩ, R2=10KΩ）。

```
感測器 Signal ──┬── R1 (33KΩ) ──┬── EC800X ADC
                │                │
                │            R2 (10KΩ)
                │                │
                └────────────────┴── GND

分壓比 = R2 / (R1+R2) = 10/43 ≈ 0.233
V_adc = V_sensor × 0.233
V_sensor = V_adc / 0.233
```

```
PH4502C:  Po pin → 分壓 → ADC0
壓力感測器: Signal → 分壓 → ADC1
```

### 3.5 GPIO（電磁閥 + 流量計）

```
EC800X QuecDuino          繼電器模組            電磁閥
┌──────────┐              ┌──────────┐         ┌──────────┐
│ GPIO25   │──────────────┤ IN       │         │          │
│          │              │ COM → 5V │─── 5V ──┤ VCC      │
│          │              │ NO       │─────────┤ Valve +   │
│ GND      │──────────────┤ GND      │         │ Valve - → │
└──────────┘              └──────────┘    GND──┘ GND      │
                                           └──────────┘
  繼電器 active-low：GPIO LOW = 開閥


EC800X QuecDuino          YF-S201 流量計
┌──────────┐              ┌──────────┐
│ GPIO26   │──────────────┤ Signal   │  (黃線, PULL_UP)
│ 5V       │──────────────┤ VCC (紅) │
│ GND      │──────────────┤ GND (黑) │
└──────────┘              └──────────┘
  GPIO IRQ_FALLING 計數脈衝
  4980 脈衝 = 1 公升
```

### 3.6 PWM + GPIO（蠕動泵 ×2）

```
EC800X QuecDuino          MOS 驅動板            蠕動泵
┌──────────┐              ┌──────────┐         ┌──────────┐
│ GPIO27   │──────────────┤ DIR      │         │          │
│ PWM0     │──────────────┤ PWM (IN) │         │  Pump A  │
│ 5V       │──────────────┤ VCC      │── 5V ──┤  Motor   │
│ GND      │──────────────┤ GND      │─────────┤  GND     │
└──────────┘              └──────────┘         └──────────┘

┌──────────┐              ┌──────────┐         ┌──────────┐
│ GPIO28   │──────────────┤ DIR      │         │          │
│ PWM1     │──────────────┤ PWM (IN) │         │  Pump B  │
│ 5V       │──────────────┤ VCC      │── 5V ──┤  Motor   │
│ GND      │──────────────┤ GND      │─────────┤  GND     │
└──────────┘              └──────────┘         └──────────┘

  GPIO: 方向控制 (0=正轉, 1=反轉)
  PWM: 流速控制 (duty 0-100%)
  頻率: 1000 Hz (1 kHz)
```

### 3.7 GPIO（繼電器 ×2）

```
EC800X QuecDuino          繼電器模組 A           總水泵
┌──────────┐              ┌──────────┐         ┌──────────┐
│ GPIO29   │──────────────┤ IN       │         │          │
│          │              │ COM → 5V │─── 5V ──┤ VCC      │
│          │              │ NO       │─────────┤ Pump +   │
│ GND      │──────────────┤ GND      │         │ Pump - → │
└──────────┘              └──────────┘    GND──┘ GND      │
                                           └──────────┘


EC800X QuecDuino          繼電器模組 B           種植燈
┌──────────┐              ┌──────────┐         ┌──────────┐
│ GPIO30   │──────────────┤ IN       │         │          │
│          │              │ COM → AC │─── AC ──┤ Light +  │
│          │              │ NO       │─────────┤ Light -  │
│ GND      │──────────────┤ GND      │         └──────────┘
└──────────┘              └──────────┘
  繼電器 active-low：GPIO LOW = ON
  種植燈若為 AC 220V，請注意安全，使用適當繼電器
```

---

## 四、軟體架構

### 4.1 檔案清單

```
QuecPythonDriver/
├── quec_i2c.py      # I2C 適配層 (QuecI2C + I2CDevice)
├── as7341.py        # AS7341 可見光+近紅外光譜感測器驅動
├── as7263.py        # AS7263 近紅外光譜感測器驅動
├── ba121.py         # BA121 導電度+溫度感測器驅動
├── ph4502c.py       # PH4502C pH 感測器驅動
├── pressure.py      # 水壓感測器驅動
├── valve.py         # 電磁閥控制驅動
├── flow.py          # 霍爾效應流量計驅動
├── pump.py          # 蠕動泵驅動 (方向 + 流速)
├── relay.py         # 繼電器控制 (總水泵 + 種植燈)
├── esp_bridge.py    # ESP32 UART 通訊橋接
├── main.py          # 主程式 (開機自動執行)
└── upload.sh        # 上傳腳本 (ampy/mpremote)
```

### 4.2 模組依賴關係

```
main.py
  ├── quec_i2c.py   ← as7341.py, as7263.py
  ├── as7341.py     ← quec_i2c (I2CDevice)
  ├── as7263.py     ← quec_i2c (QuecI2C)
  ├── ba121.py      (獨立, UART1)
  ├── ph4502c.py    (獨立, ADC)
  ├── pressure.py   (獨立, ADC)
  ├── valve.py      (獨立, GPIO)
  ├── flow.py       (獨立, GPIO IRQ)
  ├── pump.py       (獨立, GPIO + PWM_V2)
  ├── relay.py      (獨立, GPIO)
  └── esp_bridge.py (獨立, UART2)
```

### 4.3 各驅動 API 詳細說明

---

#### 4.3.1 quec_i2c.py — I2C 適配層

封裝 QuecPython 獨有的 I2C API，提供兩種介面：

**QuecI2C** — 底層操作
```python
from quec_i2c import QuecI2C
i2c = QuecI2C(I2C.I2C0, I2C.FAST_MODE)

i2c.write_reg(addr, reg, value)       # 寫單一暫存器 → 0=成功
i2c.read_reg(addr, reg, length)       # 讀暫存器 → bytearray
i2c.read_reg_byte(addr, reg)          # 讀單 byte → int
i2c.write_reg_bytes(addr, reg, data)  # 寫多 bytes → 0=成功
i2c.scan()                            # 掃描設備 → [0x39, 0x49, ...]
```

**I2CDevice** — Adafruit 相容介面（給 AS7341 用）
```python
from quec_i2c import I2CDevice
dev = I2CDevice(i2c, 0x39)

dev.write(buf)                              # buf[0]=reg, buf[1:]=data
dev.write_then_readinto(out_buf, in_buf)    # 寫 reg 後讀取
```

---

#### 4.3.2 as7341.py — AS7341 光譜感測器 (0x39)

10 通道可見光+近紅外感測器，由 SMUX 多工器分兩次讀取全部通道。

```python
from quec_i2c import QuecI2C, I2CDevice
from as7341 import AS7341

dev = I2CDevice(i2c, 0x39)
sensor = AS7341(dev)

# 設定增益
sensor.gain = AS7341.GAIN_256X    # GAIN_0_5X ~ GAIN_512X

# 讀取所有 10 通道 (需約 200ms)
data = sensor.all_channels
# → {"F1": v, "F2": v, ..., "F8": v, "CLEAR": v, "NIR": v}

# 閃爍偵測
sensor.configure_flicker_detection()
hz = sensor.flicker_detected  # Hz 或 None
sensor.initialize()  # 恢復正常模式
```

| 通道 | 波長 | 顏色 |
|------|------|------|
| F1 | 415nm | 紫光 |
| F2 | 445nm | 藍光 |
| F3 | 480nm | 青光 |
| F4 | 515nm | 綠光 |
| F5 | 555nm | 黃綠 |
| F6 | 590nm | 黃光 |
| F7 | 630nm | 橙光 |
| F8 | 680nm | 紅光 |
| CLEAR | 全波段 | 環境光 |
| NIR | 近紅外 | 910nm |

---

#### 4.3.3 as7263.py — AS7263 光譜感測器 (0x49)

6 通道近紅外感測器，使用虛擬暫存器協定（TX_VALID/RX_VALID 輪詢）。

```python
from as7263 import AS7263

sensor = AS7263(i2c, 0x49)
sensor.begin()
sensor.set_gain(AS7263.GAIN_X64)       # GAIN_X1/X3_7/X16/X64
sensor.set_integration_time(50)         # 2.78ms 單位

data = sensor.measure()
# → {"R": v, "S": v, "T": v, "U": v, "V": v, "W": v}
```

| 通道 | 波長 | 用途 |
|------|------|------|
| R | 610nm | 橙紅光 |
| S | 680nm | 紅光/葉綠素 |
| T | 730nm | 近紅外 |
| U | 760nm | 近紅外 |
| V | 810nm | 近紅外 |
| W | 860nm | 近紅外/NDVI |

---

#### 4.3.4 ba121.py — BA121 導電度+溫度 (UART1)

```python
from ba121 import BA121

sensor = BA121(UART.UART1, tx_pin=0, rx_pin=0)
sensor.init()

# 讀取導電度和溫度
conductivity, temperature = sensor.read()
# conductivity: μS/cm (float)
# temperature: °C (float)

# 基線校正（需浸泡純水）
sensor.baseline_calibration()

# 自訂 NTC 參數
sensor.set_ntc_resistance(10000)   # 10KΩ
sensor.set_ntc_b_value(3950)       # B 值
```

**UART 協定：**
- 9600bps, 8N1
- 6-byte 封包：`CMD(1B) + DATA(4B big-endian) + CHKSUM(1B)`
- 校驗和 = sum(bytes[0:5]) & 0xFF
- 讀取指令：0xA0，回應：0xAA
- 讀取延遲：800ms

---

#### 4.3.5 ph4502c.py — PH4502C pH 感測器 (ADC)

```python
from ph4502c import PH4502C

sensor = PH4502C(
    adc_channel=ADC.ADC0,
    divider_ratio=0.233,    # 電阻分壓比 R2/(R1+R2)
)

# 單點校正
sensor.calibrate(known_ph=7.0)           # 用 pH7 校正液
# 或雙點校正
sensor.calibrate_two_point(4.0, v1, 7.0, v2)

ph = sensor.read_ph()     # → float (0-14)
voltage = sensor.read_ph_voltage()  # → float (V)
```

**pH 公式：**
```
V_adc = raw × (1.3 / 4096)
V_actual = V_adc / divider_ratio
pH = calibration + (mid_voltage - V_actual) / ph_step
```

---

#### 4.3.6 pressure.py — 水壓感測器 (ADC)

```python
from pressure import PressureSensor

sensor = PressureSensor(
    adc_channel=ADC.ADC1,
    max_pressure=1.2,       # MPa
    divider_ratio=0.233,    # 分壓比
)

pressure, voltage = sensor.read_pressure()
# pressure: MPa (float)
# voltage: V (float)
```

**壓力公式（0.5-4.5V 線性輸出）：**
```
pressure = (V_actual - 0.5) / (4.5 - 0.5) × max_pressure
```

---

#### 4.3.7 valve.py — 電磁閥控制 (GPIO)

```python
from valve import WaterValve

valve = WaterValve(gpio_pin=25, active_low=True)

valve.open()           # 開閥
valve.close()          # 關閥
valve.toggle()         # 切換
valve.is_open          # → True/False
```

---

#### 4.3.8 flow.py — 霍爾效應流量計 (GPIO IRQ)

```python
from flow import FlowSensor

flow = FlowSensor(gpio_pin=26, pulses_per_liter=4980)

rate_lpm, total_liters = flow.read()
# rate_lpm: L/min (float)
# total_liters: 累計流量 L (float)

flow.flow_rate         # → float (L/min)
flow.total_liters      # → float (L)
flow.reset_total()     # 歸零累計流量
```

**原理：**
- GPIO 中斷 (IRQ_FALLING) 計數脈衝
- 流速 = (脈衝數 / PPL) / (秒數 / 60) L/min
- 累計 = 脈衝數 / PPL

---

#### 4.3.9 pump.py — 蠕動泵控制 (GPIO + PWM)

```python
from pump import PeristalticPump
from misc import PWM_V2

pump = PeristalticPump(
    dir_gpio=27,                # 方向控制 GPIO
    pwm_channel=PWM_V2.PWM0,   # PWM 通道
    freq=1000.0,                # PWM 頻率 Hz
    name="Nutrient-Pump",
)
pump.init()

pump.start(speed=80, direction=PeristalticPump.FORWARD)  # 啟動 80% 正轉
pump.set_speed(50)              # 調速至 50%
pump.set_direction(PeristalticPump.REVERSE)  # 反轉
pump.stop()                     # 停止

pump.is_running    # → bool
pump.speed         # → int (0-100)
pump.direction     # → "forward"/"reverse"
pump.status()      # → "Nutrient-Pump: forward @ 50%"
```

---

#### 4.3.10 relay.py — 繼電器控制 (GPIO)

```python
from relay import Relay

# 總水泵
water_pump = Relay(gpio_pin=29, name="WaterPump")
water_pump.on()          # 啟動水泵
water_pump.off()         # 關閉水泵
water_pump.toggle()      # 切換
water_pump.is_on         # → True/False
water_pump.status()      # → "WaterPump: ON"

# 種植燈
light = Relay(gpio_pin=30, name="GrowLight")
light.on()               # 開燈
light.off()              # 關燈
```

---

#### 4.3.11 esp_bridge.py — ESP32 UART 通訊橋接 (UART2)

EC800X 與 ESP32 之間的 JSON 通訊協定，用於：
- **上傳**：EC800X 將感測器資料送給 ESP32 → ESP32 轉發 WiFi/MQTT
- **下載**：ESP32 發送控制指令給 EC800X → 執行閥/泵/繼電器操作

```python
from esp_bridge import ESPBridge
from machine import UART

bridge = ESPBridge(UART.UART2, baud=115200)
bridge.init()

# 發送感測器資料
bridge.send_sensor_data(ph=6.8, ec=1500, temp=25.3, pressure=0.5)

# 發送設備狀態
bridge.send_status(valve="OPEN", pump_a="forward@80", pump_b="STOPPED")

# 接收並執行指令
bridge.process_commands(
    valve=valve, pump_a=pump_a, pump_b=pump_b,
    water_pump_relay=water_pump, grow_light_relay=grow_light,
)
```

**通訊協定（JSON + newline）：**

EC800X → ESP32（感測器資料，每 2 秒自動送出）：
```json
{"t":"sensor","ph":6.8,"ec":1500,"temp":25.3,"pressure":0.5,"flow_rate":1.2,"flow_total":3.5,"valve":"CLOSED"}
```

EC800X → ESP32（設備狀態）：
```json
{"t":"status","valve":"OPEN","pump_a":"forward@80","pump_b":"STOPPED","water_pump":"ON","grow_light":"OFF"}
```

EC800X → ESP32（指令確認）：
```json
{"t":"ack","id":"cmd_001","ok":true,"msg":"valve opened"}
{"t":"ack","id":"cmd_002","ok":false,"msg":"unknown pump: c"}
```

ESP32 → EC800X（控制指令）：

| 指令 | JSON 範例 | 說明 |
|------|----------|------|
| 開閥 | `{"cmd":"valve","action":"open"}` | action: open/close/toggle |
| 控制泵 | `{"cmd":"pump","id":"a","speed":80,"dir":"forward"}` | id: a/b, speed: 0-100, dir: forward/reverse |
| 停泵 | `{"cmd":"pump","id":"b","action":"stop"}` | 或 speed=0 |
| 繼電器 | `{"cmd":"relay","id":"water_pump","action":"on"}` | id: water_pump/grow_light, action: on/off/toggle |

---

## 五、GPIO 與資源分配

| 資源 | 腳位/通道 | 用途 | 備註 |
|------|----------|------|------|
| I2C0 SDA | GPIO66 (Pin16) | AS7341 + AS7263 | 400KHz |
| I2C0 SCL | GPIO67 (Pin17) | AS7341 + AS7263 | 400KHz |
| UART0 | TX/RX | Debug / REPL | 開發用 |
| UART1 | TX/RX | BA121 導電度 | 9600bps |
| **UART2** | **TX/RX** | **ESP32 通訊** | **115200bps** |
| ADC0 | ADC0 | PH4502C pH | 分壓 0.233 |
| ADC1 | ADC1 | 水壓感測器 | 分壓 0.233 |
| GPIO25 | OUT | 電磁閥繼電器 | active-low |
| GPIO26 | IN IRQ | 流量計信號 | PULL_UP, FALLING |
| GPIO27 | OUT | 蠕動泵 A 方向 | 0=正轉, 1=反轉 |
| PWM0 | PWM | 蠕動泵 A 流速 | 1KHz, duty 0-100% |
| GPIO28 | OUT | 蠕動泵 B 方向 | 0=正轉, 1=反轉 |
| PWM1 | PWM | 蠕動泵 B 流速 | 1KHz, duty 0-100% |
| GPIO29 | OUT | 總水泵繼電器 | active-low |
| GPIO30 | OUT | 種植燈繼電器 | active-low |

---

## 六、主程式流程

```
┌──────────────┐
│   開機啟動    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ 初始化 I2C   │ ← I2C0 @ 400KHz
│ 掃描設備     │ ← 預期 0x39, 0x49
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ 初始化感測器  │ ← AS7341, AS7263, BA121, pH, 壓力
│ 初始化控制器  │ ← 閥, 流量計, 蠕動泵 A/B, 繼電器
│ 初始化通訊    │ ← ESP32 UART2 橋接
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  主迴圈       │ ← 每 2 秒執行一次
│  ┌──────────┐│
│  │讀 AS7263 ││ ← NIR 6 通道
│  │讀 AS7341 ││ ← VIS+NIR 10 通道 + 閃爍偵測
│  │讀 BA121  ││ ← EC (mS/cm) + 溫度 (°C)
│  │讀 pH     ││ ← pH 值
│  │讀水壓    ││ ← MPa
│  │讀流量    ││ ← L/min + 累計 L
│  │閥狀態    ││ ← OPEN/CLOSED
│  │泵狀態    ││ ← A/B 各自方向+速度
│  │繼電器    ││ ← 總水泵 + 種植燈 ON/OFF
│  │ESP32     ││ ← 接收指令 + 送出感測器資料
│  └──────────┘│
│  sleep(2s)   │
└──────┬───────┘
       │
       ▼
     重複
```

---

## 七、ESP32 端整合指南

ESP32 端需運行 UART 接收程式，將 EC800X 資料轉發至 WiFi/MQTT。

### 7.1 ESP32 接線

```
ESP32              EC800X QuecDuino
┌──────────┐      ┌──────────┐
│ GPIO16 RX│◄─────┤ UART2 TX │
│ GPIO17 TX│─────►│ UART2 RX │
│ GND      │◄────►│ GND      │
└──────────┘      └──────────┘
```

### 7.2 ESP32 Arduino 範例程式

```cpp
// ESP32 — UART to MQTT Bridge for EC800X Hydroponic System
#include <HardwareSerial.h>

HardwareSerial ecSerial(1);  // UART1 on ESP32

void setup() {
    Serial.begin(115200);
    ecSerial.begin(115200, SERIAL_8N1, 16, 17);  // RX=16, TX=17
}

void loop() {
    // Read JSON lines from EC800X
    static String buf = "";
    while (ecSerial.available()) {
        char c = ecSerial.read();
        if (c == '\n') {
            // Parse JSON and forward to MQTT
            Serial.println("From EC800X: " + buf);
            // mqtt_client.publish("hydroponic/sensors", buf.c_str());
            buf = "";
        } else {
            buf += c;
        }
    }

    // Send commands to EC800X
    // ecSerial.println("{\"cmd\":\"valve\",\"action\":\"open\"}");
    // ecSerial.println("{\"cmd\":\"pump\",\"id\":\"a\",\"speed\":80,\"dir\":\"forward\"}");
    // ecSerial.println("{\"cmd\":\"relay\",\"id\":\"grow_light\",\"action\":\"on\"}");
}
```

### 7.3 MQTT Topic 建議

| Topic | 方向 | 說明 |
|-------|------|------|
| `hydroponic/sensors` | EC800X → MQTT | 感測器資料 |
| `hydroponic/status` | EC800X → MQTT | 設備狀態 |
| `hydroponic/ack` | EC800X → MQTT | 指令確認 |
| `hydroponic/cmd/valve` | MQTT → EC800X | 閥控制 |
| `hydroponic/cmd/pump` | MQTT → EC800X | 泵控制 |
| `hydroponic/cmd/relay` | MQTT → EC800X | 繼電器控制 |

---

## 八、上傳與部署

### 8.1 上傳方式

```bash
# 方法一：使用上傳腳本
chmod +x upload.sh
./upload.sh /dev/tty.usbmodemXXXX

# 方法二：ampy 手動上傳
pip install adafruit-ampy
for f in quec_i2c.py as7341.py as7263.py ba121.py ph4502c.py pressure.py valve.py flow.py pump.py relay.py esp_bridge.py main.py; do
    ampy -p /dev/tty.usbmodemXXXX -b 115200 put $f
done

# 方法三：QPYcom GUI 手動拖放
```

### 8.2 上傳檔案清單

```
quec_i2c.py    → I2C 適配層
as7341.py      → AS7341 驅動
as7263.py      → AS7263 驅動
ba121.py       → BA121 驅動
ph4502c.py     → pH 驅動
pressure.py    → 壓力驅動
valve.py       → 閥控制
flow.py        → 流量驅動
pump.py        → 泵控制
relay.py       → 繼電器控制 (總水泵 + 種植燈)
esp_bridge.py  → ESP32 UART 通訊橋接
main.py        → 主程式 (開機自動執行)
```

---

## 九、驗證步驟

上傳後依序驗證：

| 步驟 | 驗證項目 | 預期結果 |
|------|---------|---------|
| 1 | I2C scan | 偵測到 0x39 (AS7341) 和 0x49 (AS7263) |
| 2 | AS7341 chip_id | 回傳 0x09 |
| 3 | AS7263 hw_version | 回傳 0x3F |
| 4 | AS7341 讀值 | F1-F8 + CLEAR + NIR 非 0/65535 |
| 5 | AS7263 讀值 | R-W 非 0/65535 |
| 6 | BA121 讀值 | EC 值合理 (自來水 ~100-500 μS/cm) |
| 7 | pH 讀值 | 放入校正液確認 pH ≈ 4.0/7.0 |
| 8 | 壓力讀值 | 無壓力時 ≈ 0 MPa |
| 9 | 流量讀值 | 無水流時 ≈ 0 L/min |
| 10 | 閥控制 | open/close 切換正常 |
| 11 | 泵控制 | start/stop/speed/direction 正常 |
| 12 | 繼電器 | water_pump.on/off + grow_light.on/off 正常 |
| 13 | ESP32 通訊 | UART2 收到 JSON 感測器資料 |
| 14 | ESP32 遠端控制 | ESP32 發送指令，EC800X 正確執行並回傳 ack |

---

## 十、注意事項

1. **電壓分壓**：PH4502C 和壓力感測器輸出 0-5V，EC800X ADC 最大 1.3V，必須使用分壓電路（R1=33KΩ, R2=10KΩ，分壓比 ≈ 0.233）
2. **BA121 讀取延遲**：讀取指令後需等待 800ms 才能收到回應
3. **AS7263 虛擬暫存器**：使用 TX_VALID/RX_VALID 輪詢協定，非標準 I2C
4. **AS7341 SMUX**：10 通道需分兩次讀取（F1-F4+NIR + F5-F8+CLEAR），約需 200ms
5. **蠕動泵 PWM 頻率**：建議 1-10 KHz，過低會有震動，過高 MOS 驅動板可能不支援
6. **GPIO 電壓**：EC800X GPIO 為 3.3V，驅動 5V 繼電器/泵時確認邏輯電平相容
7. **ESP32 UART**：雙方均為 3.3V 邏輯，無需電平轉換；TX/RX 交叉連接
8. **ESP32 通訊協定**：每條訊息以 `\n` 結尾，JSON 格式，方便除錯和擴展
9. **main.py**：QuecPython 開機自動執行 `main.py`，修改後重啟模組即生效

---

## 十一、GitHub 儲存庫

https://github.com/ai-caseylai/EC800X-Spectral-Sensor

```
git clone https://github.com/ai-caseylai/EC800X-Spectral-Sensor.git
```
