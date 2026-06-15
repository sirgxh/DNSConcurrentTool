# -*- coding: utf-8 -*-
# =============================================================================
# DNS 并发测试工具
# 作者    : Gxh
# 版本    : v1.0
# 语言    : Python 3.x
# 依赖    : dnspython  (pip install dnspython)
#           tkinter     (Python 标准库，GUI 框架)
# 功能描述:
#   1. 支持多域名并发 DNS 查询（一行一个域名）
#   2. 支持自定义 DNS 服务器，留空时使用本机系统默认 DNS
#   3. 支持调整并发数、轮数、超时时间、轮间间隔
#   4. 支持指定固定源端口（src-port）、EDNS bufsize、ECS（Client Subnet）
#   5. 支持 IPv4 / IPv6 双栈选择
#   6. 支持 strace 模式（逐级追踪权威服务器，类似 dig +trace）
#   7. 简短模式输出单行摘要；非简短模式直接输出原始 DNS 响应报文
#   8. 两个日志窗口：全部日志（成功绿色 / 失败红色）+ 仅失败日志
#   9. 可将测试结果导出为 TXT 文件
#
# 打包说明:
#   pip install pyinstaller
#   pyinstaller --onefile --noconsole --name DnsTest dig_concurrent.py
#   生成产物位于 dist/DnsTest.exe，可直接复制到其他 Windows 机器运行
# =============================================================================

# ---------- 第三方库导入 ----------
import socket           # 原生 socket 发送 UDP，便于控制源端口与地址族
import tkinter as tk    # Tkinter 主模块，创建主窗口
from tkinter import ttk, filedialog, messagebox  # 子组件、文件对话框、消息框
import threading        # 后台线程执行测试，避免卡住 GUI
import time             # 计时、轮间 sleep
from concurrent.futures import ThreadPoolExecutor, as_completed  # 线程池
from datetime import datetime  # 日志时间戳

# ---------- dnspython 相关模块 ----------
import dns.message      # 构造/解析 DNS 消息
import dns.rdata        # 表示 RDATA（虽然未直接使用，但显式保留以备扩展）
import dns.rdataclass   # IN / CH / HS 等（保留）
import dns.rdatatype    # A / AAAA / CNAME / MX / TXT / NS ... 等记录类型
import dns.query        # 高层查询接口（保留，当前底层用 socket 手动发送）
import dns.name         # 域名（Name 对象）处理
import dns.edns         # EDNS 选项（ECS/Client Subnet、bufsize 等）
import dns.flags        # 把响应 flags（QR/AA/TC/RD/RA/AD/CD）格式化为可读文本
import dns.rcode        # 把响应 rcode（0=NOERROR、3=NXDOMAIN、2=SERVFAIL...）转文本
import dns.resolver     # 用于读取系统默认 DNS 服务器列表（Resolver().nameservers）


# ---------- 可配置的全局参数 ----------
# 记录类型下拉框可选项，涵盖最常用的解析类型
RECORD_TYPES = [
    "A",         # IPv4 地址记录
    "AAAA",      # IPv6 地址记录
    "CNAME",     # 别名记录
    "MX",        # 邮件交换记录
    "TXT",       # 文本记录（SPF/DKIM/DMARC 等）
    "NS",        # 权威名称服务器
    "PTR",       # 反向指针（需要 IP 反解析为 in-addr.arpa / ip6.arpa）
    "SOA",       # 起始授权记录
    "SRV",       # 服务定位记录
    "CAA",       # CA 授权策略
    "SPF",       # 旧版 SPF（目前主流使用 TXT+ v=spf1）
    "NAPTR",     # 命名授权指针（ENUM/VoIP 常用）
    "DS",        # DNSSEC 委派签名者
    "DNSKEY",    # DNSSEC 公钥
    "RRSIG",     # DNSSEC 资源记录签名
    "NSEC",      # DNSSEC 下一个安全域名
    "NSEC3",     # DNSSEC NSEC3（散列版本）
    "TLSA",      # DANE TLS 证书关联
    "HINFO",     # 主机信息（CPU/OS，基本废弃）
    "LOC",       # 地理位置（经纬度）
    "DNAME",     # 委派重命名（整条子域别名）
    "ANY",       # 请求所有类型（多数权威已废弃，容易被截断）
]


# =============================================================================
# 工具主类：DigConcurrentTool
#   - 在 __init__ 中创建 Tk 窗口与全部控件
#   - _run_test 在单独后台线程中执行，避免 GUI 假死
# =============================================================================
class DigConcurrentTool:
    """
    DNS 并发测试工具主类。

    典型用法::

        root = tk.Tk()
        app = DigConcurrentTool(root)
        root.mainloop()
    """

    # -------------------------------------------------------------------------
    # 构造函数：搭建整个界面（参数区、按钮、两个日志窗口、状态栏）
    # -------------------------------------------------------------------------
    def __init__(self, root):
        self.root = root                                 # 保存主窗口引用
        self.root.title("DNS 并发测试工具-GXH")          # 窗口标题
        # 主窗口初始尺寸，足够大以便显示长日志行
        self.root.geometry("1200x850")

        # ---------- 运行状态相关成员 ----------
        # 用于从外部中断测试循环（点击"停止"时置位）
        self.stop_event = threading.Event()

        # 保存完整日志行（纯文本，用于导出 TXT）
        self.result_lines = []

        # 进度变量：在状态栏右侧显示"进度: 已完成/总数"
        self.progress_done = 0      # 已完成查询数
        self.progress_total = 0     # 计划查询总数

        # ---------- 开始构建 UI ----------
        self._build_ui()

    # -------------------------------------------------------------------------
    # _build_ui：把主窗口拆分为若干区块
    #   [参数区] LabelFrame + 多个输入框
    #   [按钮区] 开始测试 / 停止 / 导出TXT / 清空输出
    #   [日志区] 上方：所有日志（彩色）；下方：仅报错日志
    #   [状态栏] 左侧状态文字 + 右侧进度
    # -------------------------------------------------------------------------
    def _build_ui(self):
        # 最外层容器：一个带内边距的 Frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)  # 填充整个窗口

        # ============= 1. 参数区 =============
        param_frame = ttk.LabelFrame(main_frame, text="测试参数", padding=10)
        param_frame.pack(fill=tk.X)

        # ---------- Tkinter 绑定变量（所有输入控件共享它们） ----------
        # DNS 服务器 IP 或域名；空字符串 => 使用系统默认 DNS
        self.var_dns_server = tk.StringVar(value="")
        # DNS 服务器端口（权威 DNS 默认 53，某些 DoT/DoH 工具可能走其他端口）
        self.var_port = tk.StringVar(value="53")
        # 并发线程数（即一轮同时发起的查询数）
        self.var_concurrency = tk.StringVar(value="1")
        # 测试轮数（每个域名 × 并发 × 轮数 = 总请求数）
        self.var_rounds = tk.StringVar(value="1")
        # 每次查询超时时间（秒，允许小数）
        self.var_timeout = tk.StringVar(value="1")
        # 轮与轮之间的间隔时间（毫秒），0 表示不等待
        self.var_interval = tk.StringVar(value="50")
        # EDNS Client Subnet（ECS）子网：格式 "IP/源掩码[/作用域掩码]"，留空即禁用
        self.var_ecs = tk.StringVar(value="")
        # EDNS UDP 报文最大大小（payload / bufsize），留空即使用库默认值
        self.var_bufsize = tk.StringVar(value="")
        # 发送端固定源端口（用于测试有端口绑定的策略/防火墙），留空即 OS 自动分配
        self.var_src_port = tk.StringVar(value="")
        # 解析记录类型下拉选择
        self.var_record_type = tk.StringVar(value="A")
        # IP 版本选择（IPv4 / IPv6）——控制 socket 家族与源地址
        self.var_ip_family = tk.StringVar(value="IPv4")
        # 简短输出开关（选中时单行一条日志；否则原样展示响应报文）
        self.var_short_output = tk.BooleanVar(value=True)
        # strace 模式（逐级查找权威服务器，再向权威直接查询）
        self.var_strace = tk.BooleanVar(value=False)

        # ---------- 具体布局：使用 grid 三列布局 ----------
        # row = 当前要摆放的行号，随着参数递增
        row = 0

        # 域名（多行文本框），跨 2 列显示
        ttk.Label(param_frame, text="域名（一行一个）:").grid(
            row=row, column=0, sticky="ne", padx=5, pady=3)
        self.txt_domains = tk.Text(param_frame, height=4, width=30,
                                   font=("Consolas", 10))
        self.txt_domains.insert("1.0", "example.com")      # 默认示例
        self.txt_domains.grid(row=row, column=1, rowspan=2,
                              sticky="we", padx=5, pady=3)

        # DNS 服务器
        ttk.Label(param_frame, text="DNS服务器:").grid(
            row=row, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_dns_server, width=18).grid(
            row=row, column=3, sticky="we", padx=5, pady=3)

        # 端口
        ttk.Label(param_frame, text="端口:").grid(
            row=row, column=4, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_port, width=8).grid(
            row=row, column=5, sticky="we", padx=5, pady=3)

        # ---------- 下一行：IP 版本 + bufsize ----------
        row += 1
        ttk.Label(param_frame, text="IP版本:").grid(
            row=row, column=2, sticky="e", padx=5, pady=3)
        ttk.Combobox(param_frame, textvariable=self.var_ip_family,
                     values=["IPv4", "IPv6"], width=8, state="readonly").grid(
            row=row, column=3, sticky="we", padx=5, pady=3)

        ttk.Label(param_frame, text="bufsize:").grid(
            row=row, column=4, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_bufsize, width=8).grid(
            row=row, column=5, sticky="we", padx=5, pady=3)

        # ---------- 下一行：固定源端口 ----------
        row += 1
        ttk.Label(param_frame, text="固定源端口:").grid(
            row=row, column=0, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_src_port, width=10).grid(
            row=row, column=1, sticky="we", padx=5, pady=3)

        # 并发数
        ttk.Label(param_frame, text="并发数:").grid(
            row=row, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_concurrency, width=10).grid(
            row=row, column=3, sticky="we", padx=5, pady=3)

        # 测试轮数
        ttk.Label(param_frame, text="测试轮数:").grid(
            row=row, column=4, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_rounds, width=10).grid(
            row=row, column=5, sticky="we", padx=5, pady=3)

        # ---------- 下一行：超时 + 间隔 + ECS ----------
        row += 1
        ttk.Label(param_frame, text="超时(秒):").grid(
            row=row, column=0, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_timeout, width=10).grid(
            row=row, column=1, sticky="we", padx=5, pady=3)

        ttk.Label(param_frame, text="每轮间隔(毫秒):").grid(
            row=row, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_interval, width=10).grid(
            row=row, column=3, sticky="we", padx=5, pady=3)

        ttk.Label(param_frame, text="ECS 子网:").grid(
            row=row, column=4, sticky="e", padx=5, pady=3)
        ttk.Entry(param_frame, textvariable=self.var_ecs, width=20).grid(
            row=row, column=5, sticky="we", padx=5, pady=3)

        # ---------- 下一行：记录类型下拉框 ----------
        row += 1
        ttk.Label(param_frame, text="记录类型:").grid(
            row=row, column=0, sticky="e", padx=5, pady=3)
        ttk.Combobox(param_frame, textvariable=self.var_record_type,
                     values=RECORD_TYPES, width=10, state="readonly").grid(
            row=row, column=1, sticky="we", padx=5, pady=3)

        # ---------- 复选框：简短输出 / strace 模式 ----------
        row += 1
        cb_frame = ttk.Frame(param_frame)
        cb_frame.grid(row=row, column=0, columnspan=6, sticky="w",
                       padx=5, pady=3)
        ttk.Checkbutton(cb_frame, text="简短输出（单行一条日志）",
                        variable=self.var_short_output).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(cb_frame, text="strace 模式（逐级追踪权威）",
                        variable=self.var_strace).pack(side=tk.LEFT, padx=10)

        # 让 grid 每列随窗口缩放
        for col in range(6):
            param_frame.columnconfigure(col, weight=1)

        # ============= 2. 按钮区 =============
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        self.btn_start = ttk.Button(button_frame, text="开始测试",
                                    command=self.on_start)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        # 停止按钮默认禁用，测试启动后再启用
        self.btn_stop = ttk.Button(button_frame, text="停止",
                                   command=self.on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        # 导出当前日志为 TXT 文件
        self.btn_export = ttk.Button(button_frame, text="导出为 TXT",
                                     command=self.on_export)
        self.btn_export.pack(side=tk.LEFT, padx=5)

        # 清空当前所有日志（不会影响历史导出文件）
        self.btn_clear = ttk.Button(button_frame, text="清空输出",
                                    command=self.on_clear)
        self.btn_clear.pack(side=tk.LEFT, padx=5)

        # 用于在状态栏显示实时进度（示例："进度: 0/0"
        self.progress_var = tk.StringVar(value="进度: 0/0")

        # ============= 3. 双日志窗口 =============
        output_container = ttk.Frame(main_frame)
        output_container.pack(fill=tk.BOTH, expand=True)

        # ---- 3.1 顶部：所有日志 ----
        ttk.Label(output_container, text="所有日志（正常=绿色 / 报错=红色）:").pack(
            anchor="w")

        # 使用 Frame 包装 Text + Scrollbar，方便独立控制每个窗口
        out_frame = ttk.Frame(output_container)
        out_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # Text 本体：wrap=NONE 禁止自动换行，超长行会在两个窗口内水平滚动
        self.txt_output = tk.Text(out_frame, wrap=tk.NONE, height=18,
                                   font=("Consolas", 10))
        # 水平 / 垂直滚动条，联动 txt_output
        yscroll_out = ttk.Scrollbar(out_frame, orient=tk.VERTICAL,
                                    command=self.txt_output.yview)
        xscroll_out = ttk.Scrollbar(out_frame, orient=tk.HORIZONTAL,
                                    command=self.txt_output.xview)
        # 让 Text 在滚动时也能反过去驱动滑块位置
        self.txt_output.configure(yscrollcommand=yscroll_out.set,
                                   xscrollcommand=xscroll_out.set)

        # 使用 grid 把 Text 放在中心，滚动条分别在右与在下
        self.txt_output.grid(row=0, column=0, sticky="nsew")
        yscroll_out.grid(row=0, column=1, sticky="ns")
        xscroll_out.grid(row=1, column=0, sticky="ew")
        out_frame.rowconfigure(0, weight=1)
        out_frame.columnconfigure(0, weight=1)

        # 为不同日志级别配置不同颜色
        self.txt_output.tag_configure("ok", foreground="green")    # 成功
        self.txt_output.tag_configure("err", foreground="red")      # 失败
        self.txt_output.tag_configure("info", foreground="black")   # 信息/标题

        # ---- 3.2 底部：仅报错日志 ----
        ttk.Label(output_container, text="报错日志:").pack(anchor="w")

        err_frame = ttk.Frame(output_container)
        err_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_errors = tk.Text(err_frame, wrap=tk.NONE, height=12,
                                   font=("Consolas", 10), foreground="red")
        yscroll_err = ttk.Scrollbar(err_frame, orient=tk.VERTICAL,
                                    command=self.txt_errors.yview)
        xscroll_err = ttk.Scrollbar(err_frame, orient=tk.HORIZONTAL,
                                    command=self.txt_errors.xview)
        self.txt_errors.configure(yscrollcommand=yscroll_err.set,
                                   xscrollcommand=xscroll_err.set)
        self.txt_errors.grid(row=0, column=0, sticky="nsew")
        yscroll_err.grid(row=0, column=1, sticky="ns")
        xscroll_err.grid(row=1, column=0, sticky="ew")
        err_frame.rowconfigure(0, weight=1)
        err_frame.columnconfigure(0, weight=1)

        # ============= 4. 状态栏 =============
        # 左侧显示状态文字，右侧显示进度
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))

        # 状态栏：就绪 / 测试中 / 完成 N/M / 错误
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom_frame, textvariable=self.status_var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(bottom_frame, textvariable=self.progress_var, anchor="e").pack(
            side=tk.RIGHT)

    # =========================================================================
    # on_start：点击"开始测试"后的动作
    #   1. 读取并校验参数（若非法则弹框提示）
    #   2. 重置停止信号和进度
    #   3. 切换按钮状态
    #   4. 启动后台线程执行 _run_test，防止 GUI 卡死
    # =========================================================================
    def on_start(self):
        try:
            params = self._collect_params()
        except ValueError as e:
            # 参数错误：直接 messagebox 提示，不启动线程
            messagebox.showerror("参数错误", str(e))
            return

        # 重置停止信号，并清空进度与日志缓冲
        self.stop_event.clear()
        with threading.Lock():
            self.progress_done = 0
            self.progress_total = 0
            self.result_lines = []

        # UI 切换：测试中禁用"开始"，启用"停止"；状态栏同步更新
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_var.set("测试中...")
        self.progress_var.set("进度: 0/0")

        # 在新线程中运行 _run_test，以免阻塞 Tk 主循环
        thread = threading.Thread(target=self._run_test, args=(params,),
                                  daemon=True)
        thread.start()

    # =========================================================================
    # on_stop：点击"停止"——置位事件，让 _run_test 在下轮循环时退出
    # =========================================================================
    def on_stop(self):
        self.stop_event.set()
        self.status_var.set("正在停止...")

    # =========================================================================
    # on_clear：清空两个文本控件以及在内存中的日志列表
    # =========================================================================
    def on_clear(self):
        self.txt_output.delete("1.0", tk.END)
        self.txt_errors.delete("1.0", tk.END)
        # 线程安全：虽然这里是 GUI 线程直接操作，但为防止与后台线程并发写入
        tmp = threading.Lock()
        with tmp:
            self.result_lines = []
        self.progress_var.set("进度: 0/0")
        self.status_var.set("就绪")

    # =========================================================================
    # on_export：把内存中的全部日志行写入用户指定 TXT 文件
    #   文件名默认带时间戳，避免覆盖
    # =========================================================================
    def on_export(self):
        # 需要加锁读：避免与后台写线程交错
        with threading.Lock():
            lines = list(self.result_lines)
        if not lines:
            messagebox.showwarning("提示", "当前没有输出内容可导出。")
            return

        # 默认文件名：dig_test_YYYYmmdd_HHMMSS.txt
        default_name = "dig_test_%s.txt" % datetime.now().strftime("%Y%m%d_%H%M%S")
        # 弹出保存文件对话框
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not filepath:
            # 用户取消
            return

        try:
            # UTF-8 写入，保证中文与 ASCII 字符都能正常显示
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("成功", "导出成功:\n%s" % filepath)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # =========================================================================
    # _collect_params：读取 GUI 中所有输入并组装为 dict
    #   任意参数非法都会抛出 ValueError（由 on_start 捕获并显示）
    # =========================================================================
    def _collect_params(self):
        # 1) 读取域名：按行切分，过滤空行
        raw_text = self.txt_domains.get("1.0", tk.END).strip()
        domains = []
        for line in raw_text.splitlines():
            line = line.strip()
            if line:
                domains.append(line)
        if not domains:
            raise ValueError("请至少输入一个域名。")

        # 2) DNS 服务器：空字符串时使用系统默认
        dns_server = self.var_dns_server.get().strip()
        if not dns_server:
            try:
                resolver = dns.resolver.Resolver()
                if not resolver.nameservers:
                    raise RuntimeError("未找到系统默认 DNS。")
                dns_server = resolver.nameservers[0]
            except Exception as e:
                raise ValueError("DNS 服务器为空且无法获取系统默认 DNS: %s" % e)
        else:
            # 允许用户输入 "ip:port" 形式，这里仅保留 ip
            if ":" in dns_server and dns_server.count(":") == 1 \
                    and not dns_server.startswith("["):
                parts = dns_server.rsplit(":", 1)
                if parts[0]:
                    dns_server = parts[0]

        # 3) 端口：1 ~ 65535 整数
        try:
            port = int(self.var_port.get())
            if port <= 0 or port > 65535:
                raise ValueError
        except ValueError:
            raise ValueError("端口必须是 1-65535 的整数。")

        # 4) IP 版本：只能是 IPv4 或 IPv6
        ip_family = self.var_ip_family.get()
        if ip_family not in ("IPv4", "IPv6"):
            raise ValueError("IP 版本必须是 IPv4 或 IPv6。")

        # 5) 并发数：正整数
        try:
            concurrency = int(self.var_concurrency.get())
            if concurrency <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("并发数必须是正整数。")

        # 6) 测试轮数：正整数
        try:
            rounds = int(self.var_rounds.get())
            if rounds <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("测试轮数必须是正整数。")

        # 7) 超时时间：正数（允许小数）
        try:
            timeout = float(self.var_timeout.get())
            if timeout <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("超时时间必须是正数（秒）。")

        # 8) 每轮间隔：允许空字符串 = 不等待
        raw_interval = self.var_interval.get().strip()
        if not raw_interval:
            interval_ms = 0.0
        else:
            try:
                interval_ms = float(raw_interval)
                if interval_ms < 0:
                    raise ValueError
            except ValueError:
                raise ValueError("每轮间隔时间必须是非负数（毫秒）或留空。")

        # 9) bufsize：正整数 / 留空
        bufsize = None
        raw_buf = self.var_bufsize.get().strip()
        if raw_buf:
            try:
                bufsize = int(raw_buf)
                if bufsize <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError("bufsize 必须是正整数或留空。")

        # 10) 固定源端口：1-65535 / 留空
        src_port = None
        raw_sp = self.var_src_port.get().strip()
        if raw_sp:
            try:
                src_port = int(raw_sp)
                if src_port <= 0 or src_port > 65535:
                    raise ValueError
            except ValueError:
                raise ValueError("固定源端口必须是 1-65535 的整数或留空。")

        # 11) ECS：直接字符串，构造时再解析
        ecs = self.var_ecs.get().strip()

        # 12) 记录类型：直接返回字符串（后续会转为 rdatatype 枚举）
        record_type = self.var_record_type.get().strip()

        # 13) 简短输出 & strace 标志
        short_output = self.var_short_output.get()
        strace = self.var_strace.get()

        return {
            "domains": domains,
            "dns_server": dns_server,
            "port": port,
            "ip_family": ip_family,
            "concurrency": concurrency,
            "rounds": rounds,
            "timeout": timeout,
            "interval_sec": interval_ms / 1000.0,
            "ecs": ecs,
            "bufsize": bufsize,
            "src_port": src_port,
            "record_type": record_type,
            "short_output": short_output,
            "strace": strace,
        }

    # =========================================================================
    # _write_output：把一条日志写入 GUI 并缓存到列表，供导出 TXT
    #   level = "ok"（绿色）/ "err"（红色）/ "info"（黑色）
    #   该函数始终运行在 GUI 主线程之外，因此直接向 Text 插入是可接受的
    #   （Tk 本身非线程安全，但其在 Windows 上容忍这种写入；如果遇到闪烁，
    #   可以把文本缓存，再通过 root.after(0, callback) 回主线程刷新）
    # =========================================================================
    def _write_output(self, text, level="info"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        display = "[%s] %s" % (timestamp, text)

        # 缓存到 result_lines（用于导出）
        with threading.Lock():
            self.result_lines.append(display)

        # 彩色插入主日志窗口（根据 level 选择 tag）
        tag = level
        self.txt_output.insert(tk.END, display + "\n", tag)

        # 失败日志同时写入下方错误窗口
        if level == "err":
            self.txt_errors.insert(tk.END, display + "\n")

        # 滚动到最后一行，便于用户即时观察最新结果
        self.txt_output.see(tk.END)
        self.txt_errors.see(tk.END)
        # 刷新窗口（update_idletasks 比 update 更轻量，不会处理用户交互）
        self.root.update_idletasks()

    # =========================================================================
    # _update_progress：刷新状态栏的"进度: N/M"（每次 future 完成调用）
    # =========================================================================
    def _update_progress(self):
        with threading.Lock():
            done = self.progress_done
            total = self.progress_total
        try:
            self.progress_var.set("进度: %d/%d" % (done, total))
        except Exception:
            pass

    # =========================================================================
    # _run_test：真正的测试主循环（运行在后台线程）
    #   - 构建 DNS 查询报文
    #   - 使用 ThreadPoolExecutor 并发提交
    #   - 每次 future 结束：刷新日志与进度
    #   - 轮之间 sleep params["interval_sec"]
    # =========================================================================
    def _run_test(self, params):
        try:
            # ---------- 输出标题日志 ----------
            domains_str = "; ".join(params["domains"])
            header = (
                "=== 开始测试 ===  域名: %s  DNS: %s:%d (%s)  "
                "类型: %s  并发: %d  轮数: %d  超时: %ss  "
                "间隔: %dms  ECS: '%s'  bufsize: %s  源端口: %s  "
                "简短: %s  strace: %s"
                % (domains_str, params["dns_server"], params["port"],
                   params["ip_family"], params["record_type"],
                   params["concurrency"], params["rounds"], params["timeout"],
                   int(params["interval_sec"] * 1000),
                   params["ecs"], params["bufsize"], params["src_port"],
                   params["short_output"], params["strace"])
            )
            self._write_output(header, "info")

            # ---------- 预构建通用对象 ----------
            # 记录类型转枚举（若未知类型会抛出异常）
            rtype_enum = dns.rdatatype.RdataType[params["record_type"].upper()]

            # 解析 ECS：格式 "IP/src_mask[/scope_mask]"；异常会在标题日志后给出
            ecs_option = None
            if params["ecs"]:
                try:
                    ecs_parts = params["ecs"].split("/")
                    addr = ecs_parts[0].strip()
                    src_mask = int(ecs_parts[1]) if len(ecs_parts) > 1 else 24
                    scope_mask = int(ecs_parts[2]) if len(ecs_parts) > 2 else 0
                    ecs_option = dns.edns.ECSOption(addr, src_mask, scope_mask)
                except Exception as e:
                    self._write_output("ECS 参数解析失败：%s（将以无 ECS 继续）" % e,
                                       "err")
                    ecs_option = None

            # ---------- 初始化进度与计数器 ----------
            total_queries = len(params["domains"]) * params["concurrency"] * params["rounds"]
            with threading.Lock():
                self.progress_total = total_queries
                self.progress_done = 0
            self._update_progress()

            # 成功 / 失败计数必须在轮循环外初始化，跨轮累积
            success_count = 0
            fail_count = 0

            # ---------- 主循环：每一轮 ----------
            for round_idx in range(params["rounds"]):
                # 检查是否停止
                if self.stop_event.is_set():
                    self._write_output("[第 %d 轮前] 收到停止信号，终止测试。"
                                       % (round_idx + 1), "info")
                    break

                self._write_output("--- 第 %d / %d 轮 ---" %
                                   (round_idx + 1, params["rounds"]), "info")

                # 把本轮全部任务提交到 ThreadPoolExecutor
                futures = []
                with ThreadPoolExecutor(max_workers=params["concurrency"]) as executor:
                    for domain in params["domains"]:
                        for ci in range(params["concurrency"]):
                            if self.stop_event.is_set():
                                break
                            # 把每个查询包装为一个 future，顺序会因并发变为无序
                            fut = executor.submit(
                                self._do_query,
                                domain=domain,
                                dns_server=params["dns_server"],
                                port=params["port"],
                                ip_family=params["ip_family"],
                                rtype_enum=rtype_enum,
                                timeout=params["timeout"],
                                ecs_option=ecs_option,
                                bufsize=params["bufsize"],
                                src_port=params["src_port"],
                                short_output=params["short_output"],
                                strace=params["strace"],
                                seq="R%d-%s-#%d" % (round_idx + 1, domain, ci + 1),
                            )
                            futures.append(fut)

                    # 逐个取结果，as_completed 会按完成顺序 yield future
                    # 注意：success_count / fail_count 在轮循环外初始化，
                    # 这里只做累加，不再重置，保证总计数与总请求数匹配
                    for fut in as_completed(futures):
                        if self.stop_event.is_set():
                            break
                        try:
                            output, is_ok = fut.result()
                            level = "ok" if is_ok else "err"
                            self._write_output(output, level)
                            if is_ok:
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e:
                            fail_count += 1
                            self._write_output("[异常] %s" % e, "err")

                        # 更新进度
                        with threading.Lock():
                            self.progress_done += 1
                        self._update_progress()

                # ---------- 轮间间隔 ----------
                if self.stop_event.is_set():
                    break
                if params["interval_sec"] > 0 and round_idx < params["rounds"] - 1:
                    waited = 0.0
                    step = 0.05
                    # 分段 sleep，使停止信号能较快被响应
                    while waited < params["interval_sec"] \
                            and not self.stop_event.is_set():
                        time.sleep(step)
                        waited += step

            # ---------- 最终结果汇总 ----------
            if total_queries:
                summary = (
                    "=== 测试结束 ===  总请求: %d  成功: %d  失败: %d  成功率: %.2f%%"
                    % (total_queries, success_count, fail_count,
                       success_count * 100.0 / total_queries)
                )
            else:
                summary = "=== 测试结束 ===  无请求"
            self._write_output(summary, "info")
            self.status_var.set("完成 - 成功 %d/%d" % (success_count, total_queries))
        except Exception as e:
            # 异常兜底：写出错误并更新状态
            self._write_output("[测试错误] %s" % e, "err")
            self.status_var.set("错误")
        finally:
            # 无论成功失败都要恢复按钮状态
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

    # =========================================================================
    # _do_query：执行一次单独查询（可能是普通 DNS，也可能是 strace）
    # 返回: (日志字符串, 是否成功 —— rcode==0 或 至少有 ANSWER)
    # =========================================================================
    def _do_query(self, domain, dns_server, port, ip_family, rtype_enum,
                  timeout, ecs_option, bufsize, src_port, short_output,
                  strace, seq):
        # 先看看用户是否已停止：若是，跳过本次查询
        if self.stop_event.is_set():
            return ("[%s] 已停止，跳过" % seq, False)

        try:
            qname = dns.name.from_text(domain)

            # 若启用 strace：交给专用函数处理（逐级找权威）
            if strace:
                return self._do_strace(qname, domain, rtype_enum, timeout,
                                        ip_family, ecs_option, bufsize,
                                        src_port, short_output, seq)

            # ---------- 构建 DNS 查询报文 ----------
            query = dns.message.make_query(qname, rtype_enum)

            # 应用 EDNS（bufsize / ECS 可以同时生效）
            if ecs_option is not None and bufsize:
                query.use_edns(payload=bufsize, options=[ecs_option])
            elif ecs_option is not None:
                query.use_edns(options=[ecs_option])
            elif bufsize:
                query.use_edns(payload=bufsize)

            # 选择 socket 家族与源地址绑定 IP
            if ip_family == "IPv6":
                af = socket.AF_INET6
                bind_addr = "::"
            else:
                af = socket.AF_INET
                bind_addr = "0.0.0.0"

            wire = query.to_wire()
            start = time.time()
            with socket.socket(af, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                # 若指定了源端口，则 bind；否则由 OS 自动分配
                if src_port:
                    try:
                        sock.bind((bind_addr, src_port))
                    except OSError as e:
                        # 端口被占用 / 无权限 都能友好提示
                        return ("[%s] %s %s @ %s:%d -> ERROR: 无法绑定源端口 %s (%s)"
                                % (seq, domain, rtype_enum.name, dns_server, port,
                                   src_port, e), False)
                try:
                    sock.sendto(wire, (dns_server, port))
                    data, _ = sock.recvfrom(65535)
                except Exception as e:
                    elapsed_ms = (time.time() - start) * 1000
                    return ("[%s] %s %s @ %s:%d -> ERROR: %s | 耗时: %.1fms | id: 0x%04X"
                            % (seq, domain, rtype_enum.name, dns_server, port,
                               e, elapsed_ms, query.id), False)

            # 解析响应
            response = dns.message.from_wire(data)
            elapsed_ms = (time.time() - start) * 1000

            # 根据是否"简短输出"决定展示样式
            if short_output:
                return self._format_short_line(seq, domain, rtype_enum,
                                                dns_server, port, response,
                                                elapsed_ms)
            else:
                # 非简短：直接输出 str(response) 原始文本
                return (str(response), response.rcode() == 0)

        except Exception as e:
            elapsed_ms = 0.0
            return ("[%s] %s %s @ %s:%d -> ERROR: %s | 耗时: %.1fms"
                    % (seq, domain, rtype_enum.name, dns_server, port,
                       e, elapsed_ms), False)

    # =========================================================================
    # _do_strace：模拟 dig +trace
    #   1. 内置一组根提示（ROOT_HINTS）
    #   2. 向当前权威查询区域的 NS 记录
    #   3. 解析 NS 得到 IP，作为下一级候选权威
    #   4. 最终向最底层权威直查目标记录
    # 返回: (要写入日志的多行字符串, 是否成功)
    # =========================================================================
    def _do_strace(self, qname, domain, rtype_enum, timeout, ip_family,
                    ecs_option, bufsize, src_port, short_output, seq):
        lines = []            # 逐行构建日志
        is_ok = False

        try:
            # 根提示（所有支持递归的解析器都内置一份；这里也内置一份）
            ROOT_HINTS = [
                "198.41.0.4",     # a.root-servers.net
                "199.9.14.201",   # b
                "192.33.4.12",    # c
                "199.7.91.13",    # d
                "192.203.230.10", # e
                "192.5.5.241",    # f
                "192.112.36.4",   # g
                "198.97.190.53",  # h
                "192.36.148.17",  # i
                "192.58.128.30",  # j
                "193.0.14.129",   # k
                "199.7.83.42",    # l
                "202.12.27.33",   # m
            ]

            current_zone = dns.name.root      # 起始区域：根 "."
            current_servers = list(ROOT_HINTS)

            if ip_family == "IPv6":
                af = socket.AF_INET6
                bind_addr = "::"
            else:
                af = socket.AF_INET
                bind_addr = "0.0.0.0"

            start_total = time.time()

            labels = qname.labels   # ("www", "example", "com", "")
            # 从最长域名逐级缩短（www.example.com -> example.com -> com -> 根）
            for i in range(len(labels), 0, -1):
                zone = dns.name.Name(labels[i - 1:])
                zone_text = zone.to_text()
                lines.append(";; 查询区域: %s  候选权威: %s"
                             % (zone_text, ", ".join(current_servers[:3])))

                # 向 current_servers 中的某个 NS 查这个区域的 NS 记录
                ns_list = None
                selected_server = None
                last_response = None

                for ns in current_servers:
                    if self.stop_event.is_set():
                        lines.append(";; 已停止")
                        return ("\n".join(lines), False)
                    try:
                        q = dns.message.make_query(zone, dns.rdatatype.NS)
                        if ecs_option is not None and bufsize:
                            q.use_edns(payload=bufsize, options=[ecs_option])
                        elif ecs_option is not None:
                            q.use_edns(options=[ecs_option])
                        elif bufsize:
                            q.use_edns(payload=bufsize)

                        wire = q.to_wire()
                        with socket.socket(af, socket.SOCK_DGRAM) as s:
                            s.settimeout(timeout)
                            if src_port:
                                try:
                                    s.bind((bind_addr, src_port))
                                except OSError:
                                    pass
                            s.sendto(wire, (ns, 53))
                            data, _ = s.recvfrom(65535)
                        response = dns.message.from_wire(data)
                        last_response = response
                        selected_server = ns

                        # 情况 1：权威直接把 NS 放在 ANSWER 中
                        if response.answer:
                            tmp = []
                            for rrset in response.answer:
                                if rrset.rdtype == dns.rdatatype.NS:
                                    for rd in rrset:
                                        tmp.append(str(rd.target))
                            if tmp:
                                ns_list = tmp
                                break

                        # 情况 2：权威把 NS 放在 AUTHORITY 中（常见）
                        if response.authority:
                            for rrset in response.authority:
                                if rrset.rdtype == dns.rdatatype.NS:
                                    ns_list = [str(rd.target) for rd in rrset]
                                    break
                            if ns_list:
                                break
                    except Exception:
                        # 当前 NS 不通时，循环继续尝试下一个
                        continue

                # 如果始终没拿到 NS：退回到最近响应的权威，直接用它查询
                if not ns_list:
                    lines.append(";; 未能获取 %s 的 NS 记录，使用最近一次响应服务器"
                                 % zone_text)
                    if last_response is not None and selected_server:
                        current_servers = [selected_server]
                        current_zone = zone
                        break
                    else:
                        elapsed_ms = (time.time() - start_total) * 1000
                        lines.append("[%s] strace 失败: 无法查询根/上级权威" % seq)
                        lines.append("[%s] 耗时: %.1fms" % (seq, elapsed_ms))
                        return ("\n".join(lines), False)

                # 把 NS 域名解析到 IP（有些权威直接在 ADDITIONAL 中带 glue，
                # 这里为稳妥起见统一走系统解析）
                if selected_server:
                    lines.append(";; 从 %s 获取 %s NS: %s"
                                 % (selected_server, zone_text,
                                    ", ".join(ns_list[:5])))

                resolved = []
                for ns in ns_list:
                    try:
                        # getaddrinfo 能处理 IPv4/IPv6 混合结果
                        infos = socket.getaddrinfo(ns, 53, family=af,
                                                    type=socket.SOCK_DGRAM)
                        for info in infos:
                            resolved.append(info[4][0])
                    except Exception:
                        continue
                if not resolved:
                    # 再次兜底：向系统做一次通用解析
                    try:
                        infos = socket.getaddrinfo(ns_list[0], 53,
                                                    type=socket.SOCK_DGRAM)
                        for info in infos:
                            resolved.append(info[4][0])
                    except Exception:
                        resolved = [selected_server] if selected_server \
                            else current_servers

                # 更新下一轮候选权威（只保留最多 8 个，避免无限膨胀）
                current_servers = resolved[:8]
                current_zone = zone

            # ---------- 向最底层权威直接查询目标记录 ----------
            final_server = current_servers[0] if current_servers else dns_server
            lines.append(";; 最终权威: %s:53  查询: %s %s"
                         % (final_server, domain, rtype_enum.name))

            query = dns.message.make_query(qname, rtype_enum)
            if ecs_option is not None and bufsize:
                query.use_edns(payload=bufsize, options=[ecs_option])
            elif ecs_option is not None:
                query.use_edns(options=[ecs_option])
            elif bufsize:
                query.use_edns(payload=bufsize)

            start = time.time()
            wire = query.to_wire()
            with socket.socket(af, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                if src_port:
                    try:
                        s.bind((bind_addr, src_port))
                    except OSError:
                        pass
                s.sendto(wire, (final_server, 53))
                data, _ = s.recvfrom(65535)
            response = dns.message.from_wire(data)
            elapsed_ms = (time.time() - start) * 1000

            is_ok = response.rcode() == 0

            if short_output:
                text, _ = self._format_short_line(seq, domain, rtype_enum,
                                                   final_server, 53,
                                                   response, elapsed_ms)
                lines.append(text)
            else:
                # 非简短 + strace：直出 str(response) 原始报文
                lines.append(str(response))

            total_ms = (time.time() - start_total) * 1000
            lines.append("[%s] 总追踪耗时: %.1fms" % (seq, total_ms))

            return ("\n".join(lines), is_ok)

        except Exception as e:
            lines.append("[%s] strace ERROR: %s" % (seq, e))
            return ("\n".join(lines), False)

    # =========================================================================
    # _format_short_line：单行格式化简短日志
    #   [seq] domain TYPE @ server:port -> IP1;IP2 | status: NOERROR | 耗时: x.xms | id: 0xXXXX
    # =========================================================================
    def _format_short_line(self, seq, domain, rtype_enum, server, port,
                            response, elapsed_ms):
        # rcode 转文本（NOERROR / NXDOMAIN / SERVFAIL ...）
        try:
            rcode_text = dns.rcode.to_text(response.rcode())
        except Exception:
            rcode_text = str(response.rcode())
        is_ok = response.rcode() == 0

        # 先尝试从 ANSWER 中取记录；如果是 CNAME 链，会有多个 RR
        answer_parts = []
        if response.answer:
            for rrset in response.answer:
                for rd in rrset:
                    answer_parts.append(str(rd))
        else:
            # 空响应但 authority 中可能有 SOA（表示权威拒绝或不存在）
            for rrset in response.authority:
                for rd in rrset:
                    answer_parts.append("auth:%s" % rd)

        if answer_parts:
            # 最多显示前 8 条，避免单行过长
            answer = ";".join(answer_parts[:8])
        else:
            answer = "(无 ANSWER)"

        # 对整条 answer 再做一次截断（如 IP 列表仍可能很长）
        if len(answer) > 200:
            answer = answer[:200] + "..."

        line = ("[%s] %s %s @ %s:%d -> %s | status: %s | 耗时: %.1fms | id: 0x%04X"
                % (seq, domain, rtype_enum.name, server, port,
                   answer, rcode_text, elapsed_ms, response.id))
        return (line, is_ok)


# =============================================================================
# main：入口函数
#   如果文件被当作脚本运行（python dig_concurrent.py），则启动 GUI
#   如果文件被 import 作为模块使用，则不会自动启动
# =============================================================================
def main():
    root = tk.Tk()
    DigConcurrentTool(root)
    root.mainloop()


# 只有直接运行脚本（而非 import）时才进入 main
if __name__ == "__main__":
    main()
