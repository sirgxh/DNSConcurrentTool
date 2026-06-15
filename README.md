# DNS 并发测试工具（DnsTest）

一个基于 **Python 3 + Tkinter + dnspython** 的 GUI DNS 并发测试工具，可同时对多个域名、多轮、高并发发起 DNS 查询，并把结果按「正常 / 错误」分色显示，还可导出为 TXT 文件。

> 作者：**Gxh**

---

## 软件截图

<img width="1920" height="1152" alt="image" src="https://github.com/user-attachments/assets/802f60e7-b135-414d-b77f-4d70041249f5" />


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

## 与其他 DNS 工具对比

### 一、GUI DNS 工具对比

| 项目 | 语言 | GUI | 并发查询 | ECS/EDNS | strace | 固定源端口 | IPv6 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **本工具 (DnsTest)** | Python | ✅ Tkinter | ✅ 线程池 | ✅ | ✅ | ✅ | ✅ |
| [DnsSpeedTestApp](https://github.com/xihan123/DnsSpeedTestApp) | 桌面应用 | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [bargozin-desktop](https://github.com/403unlocker/bargozin-desktop) | 桌面应用 | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| [whoisdigger](https://github.com/supermarsx/whoisdigger) | Tauri | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| [MyIP](https://github.com/jason5ng32/MyIP) | 网页/Web | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 二、CLI / 高性能批量 DNS 解析工具对比

| 项目 | 语言 | 功能定位 | 图形界面 | 适合场景 |
| :--- | :--- | :--- | :---: | :--- |
| **本工具 (DnsTest)** | Python | GUI 并发测试 + 多协议 | ✅ | 教学/测试/可视化/日常使用 |
| [massdns](https://github.com/blechschmidt/massdns) | C | 超高并发批量 DNS 解析（子域名枚举） | ❌ | 大规模批量查询、渗透测试 |
| [pydig](https://github.com/shuque/pydig) | Python | 通用 DNS 查询工具 | ❌ CLI | 单条/批量查询、学习 DNS 协议 |
| [go-bulk-dns-resolver](https://github.com/threatstream/go-bulk-dns-resolver) | Go | 极速批量 DNS 解析 | ❌ | 威胁情报 / 大规模解析 |
| [bulkDNS](https://github.com/maroofi/bulkDNS) | Python | 大规模 DNS 测量扫描 | ❌ | 学术研究 / 测量分析 |
| [asyncdns](https://github.com/flier/asyncdns) | Python | 异步 DNS 查询管道 | ❌ | 脚本集成 / 自动化处理 |

### 三、DNS 性能测试/压力测试工具对比

| 项目 | 语言 | UDP | TCP | DoT | DoH | 性能 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **本工具 (DnsTest)** | Python | ✅ | ✅ | ❌ | ❌ | 中等（适合日常测试） |
| [flamethrower](https://github.com/DNS-OARC/flamethrower) | C++ | ✅ | ✅ | ✅ | ✅ | 极高（专业级测试工具） |
| [dnsblast](https://github.com/jedisct1/dnsblast) | C | ✅ | ❌ | ❌ | ❌ | 高（轻量级压力测试） |
| [dnsstresss](https://github.com/MickaelBergem/dnsstresss) | Go | ✅ | ✅ | ❌ | ❌ | 高 |
| [dns-benchmark (xxnuo)](https://github.com/xxnuo/dns-benchmark) | Python | ✅ | ✅ | ✅ | ✅ | 中等（支持可视化图表） |
| [dnsperftest](https://github.com/cleanbrowsing/dnsperftest) | Shell | ✅ | ✅ | ✅ | ✅ | 中等（命令行多 DNS 对比） |

### 四、本工具的独特优势

- 🌟 **完整中文 GUI** — 无需命令行操作，Tkinter 图形界面，国内用户友好
- 🌟 **ECS (Client Subnet) 支持** — 可测试基于客户端子网的地理位域路由
- 🌟 **固定源端口 + IPv4/IPv6 双栈** — 用于测试策略防火墙、源端口过滤等安全场景
- 🌟 **strace 逐级追踪权威服务器** — 类似 `dig +trace`，完整还原 DNS 解析链路
- 🌟 **双日志窗口 + 实时进度** — 成功/失败分色显示，便于快速排查异常
- 🌟 **单文件 exe 可分发** — PyInstaller 打包，无 Python 环境也能运行

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

## 版本信息

- 工具名：**DnsTest**（DNS 并发测试工具-GXH）
- 作者：**Gxh**
- Python：3.12
- dnspython：2.x
- PyInstaller：6.x

---

*本工具仅用于学习与合规测试，请勿用于攻击他人 DNS 系统或违反法律法规。*
