# DNS 并发测试工具（DnsTest）

一个基于 **Python 3 + Tkinter + dnspython** 的 GUI DNS 并发测试工具，可同时对多个域名、多轮、高并发发起 DNS 查询，并把结果按「正常 / 错误」分色显示，还可导出为 TXT 文件。

> 作者：**Gxh**

---

## 功能特性

- ✅ 支持多域名（一行一个）
- ✅ 自定义 DNS 服务器 IP 与端口（留空使用本机默认 DNS）
- ✅ 调整并发数、轮数、超时、轮间间隔
- ✅ EDNS bufsize 与 **ECS（Client Subnet）**
- ✅ 固定源端口（测试策略/防火墙）
- ✅ IPv4 / IPv6 双栈选择
- ✅ **strace 模式**（逐级追踪权威服务器，类似 `dig +trace`）
- ✅ 记录类型：A / AAAA / CNAME / MX / TXT / NS / PTR / SOA / SRV / CAA / SPF / NAPTR / DS / DNSKEY / RRSIG / NSEC / NSEC3 / TLSA / LOC / DNAME / ANY
- ✅ 双日志窗口：所有日志（正常绿色 / 失败红色）+ 报错日志独立窗口
- ✅ 单行摘要 / 原始报文两种输出模式
- ✅ 状态栏实时进度（总请求数 / 已完成 / 成功数 / 失败数 / 成功率）
- ✅ 一键导出 TXT（含时间戳前缀）
- ✅ 可打包为**单文件 exe**（`dist\DnsTest.exe`），直接拷贝到其他 Windows 机器运行

---

## 运行方式

### 方式一：单文件 exe（推荐，不需要安装 Python）

直接双击 `dist\DnsTest.exe` 即可运行。

> 如 `dist\` 目录不存在，请使用下方源码方式运行并打包。

### 方式二：Python 源码方式

```bash
pip install dnspython
python dig_concurrent.py
```

要求 Python 版本 ≥ 3.8（Tkinter 为标准库，默认已集成）。

---

## 打包为单文件 exe

```bash
pip install pyinstaller
cd 项目目录
pyinstaller --onefile --noconsole --name DnsTest dig_concurrent.py
```

产物：`dist\DnsTest.exe`（约 12 MB）

---

## 参数说明

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| 域名 | `example.com` | 一行一个域名，可输入多个 |
| DNS 服务器 | 空 | 留空时使用本机系统默认 DNS |
| 端口 | `53` | DNS 服务器 UDP 端口 |
| IP 版本 | `IPv4` | IPv4 / IPv6 |
| 并发数 | `1` | 每一轮同时发起的查询数 |
| 轮数 | `1` | 总共执行多少轮 |
| 超时（秒） | `1` | 每次查询最长等待时间，小数允许 |
| 每轮间隔（毫秒） | `50` | 两轮之间的冷却时间，0 表示不等待 |
| ECS 子网 | 空 | 格式：`IP/源掩码[/作用域掩码]` |
| bufsize | 空 | EDNS UDP 报文最大大小（字节） |
| 固定源端口 | 空 | UDP 发送时固定使用的源端口（1-65535） |
| 记录类型 | `A` | 见上方列表 |
| 简短输出 | ✅ 勾选 | 勾选后每条日志单行摘要；取消则直出原始报文 |
| strace 模式 | ❌ 未勾选 | 逐级追踪权威服务器 |

总请求数计算公式：

```
总请求数 = 域名数 × 并发数 × 轮数
```

---

## 输出示例（简短模式）

```
[2026-06-13 10:30:15.421] [R1-example.com-#1] example.com A @ 1.1.1.1:53 -> 172.66.147.243 | status: NOERROR | 耗时: 126.8ms | id: 0x5ABC
[2026-06-13 10:30:15.425] [R1-example.com-#2] example.com A @ 1.1.1.1:53 -> 172.66.147.243 | status: NOERROR | 耗时: 123.5ms | id: 0x5ABD
...
=== 测试结束 ===  总请求: 1000  成功: 983  失败: 17  成功率: 98.30%
```

其中 `R1-example.com-#1` 表示「第 1 轮 / 域名 example.com / 第 1 个并发请求」。

---

## 使用示例

### 示例 1：快速并发压测

| 参数 | 输入 |
| :--- | :--- |
| 域名 | `example.com` |
| DNS 服务器 | `1.1.1.1` |
| 并发数 | `50` |
| 轮数 | `10` |
| 超时 | `2` |

点 **开始测试**，窗口会滚动显示全部 500 条查询结果。

### 示例 2：使用本机默认 DNS 批量测试

| 参数 | 输入 |
| :--- | :--- |
| 域名 | 每行一个，例如 `example.com` / `baidu.com` / `qq.com` |
| DNS 服务器 | 留空（自动使用本机默认 DNS） |
| 记录类型 | `A` |

### 示例 3：ECS + bufsize 同时使用

| 参数 | 输入 |
| :--- | :--- |
| DNS 服务器 | 权威 DNS IP |
| ECS 子网 | `203.0.113.0/24` |
| bufsize | `4096` |

---

## 常见问题

**Q1：启动 exe 后窗口为空？**
首次启动会在临时目录解压一次（约 30-50 MB），稍等几秒即可出现窗口。

**Q2：大量红色 "超时"？**
- DNS 服务器限流或网络抖动，调大超时或降低并发；
- 确认网络可达（`ping <dns-ip>` 与 `nslookup example.com <dns-ip>`）。

**Q3：固定源端口绑定失败？**
- 1024 以下端口需要管理员权限；
- 端口可能被其他程序占用，换一个即可。

**Q4：ECS 无效果？**
ECS 仅在对方 DNS 显式支持时才生效，常见公共递归（1.1.1.1 / 8.8.8.8 / 223.5.5.5）均支持。

---

## 项目结构

```
dig/
├── dig_concurrent.py          # 主程序（约 750 行，含详细注释）
├── README.md                  # 项目说明（本文件）
├── DNS测试工具使用说明.md      # 详细使用说明（中文）
├── .gitignore                 # 忽略 build/ dist/ __pycache__/ 等
├── DnsTest.spec               # PyInstaller 配置（自动生成）
├── build/                     # PyInstaller 中间产物
└── dist/
    └── DnsTest.exe            # 单文件可执行程序
```

---

## 版本信息

- 工具名：**DnsTest**（DNS 并发测试工具-GXH）
- 作者：**Gxh**
- Python：3.12
- dnspython：2.x
- PyInstaller：6.x

---

*本工具仅用于学习与合规测试，请勿用于攻击他人 DNS 系统或违反法律法规。*