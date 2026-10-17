#!/usr/bin/env python3
"""
WorkBuddy AI 国际版反向代理 - 一键部署脚本
自动检测环境、配置端口、设置开机自启、启动服务

用法:
    python install.py          # 交互式部署
    python install.py --port 8899 --autostart --install-dir C:\\Users\\me\\wb_proxy
"""

import os
import sys
import json
import time
import shutil
import argparse
import urllib.request
import subprocess
from pathlib import Path


# ============ 颜色输出 ============
class Color:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_green(msg):
    print(f"{Color.GREEN}{msg}{Color.END}")


def print_yellow(msg):
    print(f"{Color.YELLOW}{msg}{Color.END}")


def print_red(msg):
    print(f"{Color.RED}{msg}{Color.END}")


def print_cyan(msg):
    print(f"{Color.CYAN}{msg}{Color.END}")


def print_bold(msg):
    print(f"{Color.BOLD}{msg}{Color.END}")


# ============ 环境检测 ============
def detect_workbuddy():
    """检测 WorkBuddy AI 国际版安装和配置"""
    info = {
        "installed": False,
        "install_path": None,
        "version": None,
        "config_dir": None,
        "auth_file": None,
        "jwt_token": None,
        "user_id": None,
        "machine_id": None,
    }

    # 检测安装路径
    possible_paths = [
        r"C:\Program Files\WorkBuddyAI",
        r"C:\Program Files (x86)\WorkBuddyAI",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\WorkBuddyAI"),
        os.path.expandvars(r"%LOCALAPPDATA%\WorkBuddyAI"),
    ]

    for p in possible_paths:
        exe = os.path.join(p, "WorkBuddyAI.exe")
        if os.path.exists(exe):
            info["installed"] = True
            info["install_path"] = p
            # 尝试获取版本
            try:
                from win32com.client import Dispatch
                ver_parser = Dispatch("Scripting.FileSystemObject")
                info["version"] = ver_parser.GetFileVersion(exe)
            except:
                info["version"] = "unknown"
            break

    # 检测配置目录
    config_paths = [
        os.path.expanduser("~/.workbuddy-ai"),
        os.path.expandvars(r"%APPDATA%\WorkDaddy\profiles\workbuddy-ai"),
        os.path.expanduser("~/.workbuddy"),
    ]

    for p in config_paths:
        if os.path.isdir(p):
            info["config_dir"] = p
            break

    # 检测 auth 文件
    auth_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop-ai.info"),
        os.path.expandvars(r"%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info"),
    ]

    for p in auth_paths:
        if os.path.exists(p):
            info["auth_file"] = p
            break

    # 尝试读取 JWT token（从同目录的 token_live.txt）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(script_dir, "token_live.txt")
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            token = f.read().strip()
            if token:
                info["jwt_token"] = token

    # 尝试从 settings.json 读取用户信息
    if info["config_dir"]:
        settings_file = os.path.join(info["config_dir"], "settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                if "userId" in settings:
                    info["user_id"] = settings["userId"]
                if "machineId" in settings:
                    info["machine_id"] = settings["machineId"]
            except:
                pass

    return info


def check_python():
    """检查 Python 环境"""
    return sys.version_info >= (3, 8)


def check_port_available(port):
    """检查端口是否可用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


# ============ 部署逻辑 ============
def get_install_dir():
    """获取默认安装目录"""
    return os.path.join(os.path.expanduser("~"), "wb_proxy")


def copy_files(install_dir, source_dir):
    """复制反代文件到安装目录"""
    os.makedirs(install_dir, exist_ok=True)

    files_to_copy = ["workbuddy_proxy.py", "token_live.txt"]
    copied = []

    for f in files_to_copy:
        src = os.path.join(source_dir, f)
        dst = os.path.join(install_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            copied.append(f)

    return copied


def create_startup_script(install_dir, port):
    """创建启动脚本"""
    bat_path = os.path.join(install_dir, "start_proxy.bat")
    vbs_path = os.path.join(install_dir, "start_hidden.vbs")

    # BAT 启动脚本
    bat_content = f"""@echo off
chcp 65001 >nul
echo ============================================
echo WorkBuddy AI 国际版反向代理
echo ============================================
echo 端口: {port}
echo.
python "{os.path.join(install_dir, 'workbuddy_proxy.py')}" --port {port}
pause
"""
    with open(bat_path, "w", encoding="gbk") as f:
        f.write(bat_content)

    # VBS 隐藏启动脚本
    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python ""{os.path.join(install_dir, 'workbuddy_proxy.py')}"" --port {port}", 0, False
'''
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    return bat_path, vbs_path


def setup_autostart(vbs_path):
    """设置开机自启（启动文件夹快捷方式）"""
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    shortcut_path = os.path.join(startup_dir, "WorkBuddyAI-Proxy.lnk")

    try:
        # 创建快捷方式
        ws = __import__("win32com.client", fromlist=["Dispatch"]).Dispatch("WScript.Shell")
        shortcut = ws.CreateShortcut(shortcut_path)
        shortcut.TargetPath = "wscript.exe"
        shortcut.Arguments = f'"{vbs_path}"'
        shortcut.WorkingDirectory = os.path.dirname(vbs_path)
        shortcut.WindowStyle = 7
        shortcut.Description = "WorkBuddy AI 国际版反向代理服务"
        shortcut.Save()
        return True, shortcut_path
    except Exception as e:
        # 备用方案：直接复制 VBS 到启动文件夹
        try:
            shutil.copy2(vbs_path, os.path.join(startup_dir, "WorkBuddyAI-Proxy.vbs"))
            return True, os.path.join(startup_dir, "WorkBuddyAI-Proxy.vbs")
        except Exception as e2:
            return False, str(e2)


def remove_autostart():
    """移除开机自启"""
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    removed = []
    for f in ["WorkBuddyAI-Proxy.lnk", "WorkBuddyAI-Proxy.vbs"]:
        p = os.path.join(startup_dir, f)
        if os.path.exists(p):
            os.remove(p)
            removed.append(f)
    return removed


def start_proxy(install_dir, port):
    """启动反代服务"""
    script_path = os.path.join(install_dir, "workbuddy_proxy.py")
    python_exe = sys.executable

    # 检查是否已经在运行
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
        return "already_running"
    except:
        pass

    # 启动
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        [python_exe, script_path, "--port", str(port)],
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        cwd=install_dir
    )

    # 等待启动
    for i in range(10):
        time.sleep(1)
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            if resp.status == 200:
                return "started"
        except:
            continue
    return "timeout"


def stop_proxy(port):
    """停止反代服务"""
    # 找到监听该端口的进程并杀掉
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                return True
    except:
        pass
    return False


def verify_proxy(port):
    """验证反代服务"""
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
        health = json.loads(resp.read().decode("utf-8"))

        # 测试聊天
        body = json.dumps({
            "model": "gpt-5.6-luna",
            "messages": [{"role": "user", "content": "说一个字"}],
            "stream": False
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp2:
            chat = json.loads(resp2.read().decode("utf-8"))
            content = chat["choices"][0]["message"]["content"]

        return {
            "health": health,
            "chat_ok": True,
            "chat_content": content,
        }
    except Exception as e:
        return {"health": None, "chat_ok": False, "error": str(e)}


# ============ 交互式菜单 ============
def interactive_menu():
    """交互式部署菜单"""
    os.system("cls" if os.name == "nt" else "clear")

    print_bold("=" * 60)
    print_bold("  WorkBuddy AI 国际版反向代理 - 一键部署")
    print_bold("=" * 60)
    print()

    # 环境检测
    print_cyan("[1/4] 正在检测环境...")
    info = detect_workbuddy()

    if info["installed"]:
        print_green(f"  ✓ WorkBuddy AI 已安装: {info['install_path']}")
        print_green(f"  ✓ 版本: {info['version']}")
    else:
        print_yellow("  ! 未检测到 WorkBuddy AI 安装（不影响反代使用，反代直接调云端 API）")

    if info["config_dir"]:
        print_green(f"  ✓ 配置目录: {info['config_dir']}")

    if info["jwt_token"]:
        print_green(f"  ✓ JWT Token: 已配置 ({len(info['jwt_token'])} 字符)")
    else:
        print_red("  ✗ JWT Token: 未找到")
        print_yellow("    请将 token 保存到同目录的 token_live.txt，或在部署后手动填写")

    if not check_python():
        print_red("  ✗ Python 版本过低，需要 3.8+")
        return

    print()

    # 配置端口
    print_cyan("[2/4] 配置端口")
    while True:
        default_port = "8899"
        port_input = input(f"  请输入端口号（默认 {default_port}）: ").strip()
        port = int(port_input) if port_input else int(default_port)
        if 1 <= port <= 65535:
            if check_port_available(port):
                print_green(f"  ✓ 端口 {port} 可用")
                break
            else:
                print_yellow(f"  ! 端口 {port} 已被占用，尝试其他端口")
        else:
            print_red("  ✗ 端口号无效（1-65535）")

    print()

    # 安装目录
    print_cyan("[3/4] 配置安装目录")
    default_dir = get_install_dir()
    dir_input = input(f"  请输入安装目录（默认 {default_dir}）: ").strip()
    install_dir = dir_input if dir_input else default_dir
    print_green(f"  ✓ 安装目录: {install_dir}")

    print()

    # 开机自启
    print_cyan("[4/4] 开机自启")
    autostart_input = input("  是否设置开机自启？(Y/n): ").strip().lower()
    enable_autostart = autostart_input != "n"

    print()
    print_bold("=" * 60)
    print_bold("  部署配置确认")
    print_bold("=" * 60)
    print(f"  端口: {port}")
    print(f"  安装目录: {install_dir}")
    print(f"  开机自启: {'是' if enable_autostart else '否'}")
    print(f"  JWT Token: {'已配置' if info['jwt_token'] else '未配置'}")
    print()

    confirm = input("  确认开始部署？(Y/n): ").strip().lower()
    if confirm == "n":
        print_yellow("  部署已取消")
        return

    print()
    print_cyan("正在部署...")

    # 1. 复制文件
    source_dir = os.path.dirname(os.path.abspath(__file__))
    copied = copy_files(install_dir, source_dir)
    print_green(f"  ✓ 已复制文件: {', '.join(copied)}")

    # 2. 创建启动脚本
    bat_path, vbs_path = create_startup_script(install_dir, port)
    print_green(f"  ✓ 已创建启动脚本: {os.path.basename(bat_path)}, {os.path.basename(vbs_path)}")

    # 3. 开机自启
    if enable_autostart:
        success, autostart_path = setup_autostart(vbs_path)
        if success:
            print_green(f"  ✓ 已设置开机自启: {autostart_path}")
        else:
            print_red(f"  ✗ 开机自启设置失败: {autostart_path}")

    # 4. 启动服务
    print_cyan("  正在启动反代服务...")
    status = start_proxy(install_dir, port)
    if status == "started":
        print_green("  ✓ 反代服务已启动")
    elif status == "already_running":
        print_yellow("  ! 反代服务已在运行")
    else:
        print_red("  ✗ 反代服务启动超时，请检查日志")

    # 5. 验证
    print_cyan("  正在验证服务...")
    result = verify_proxy(port)
    if result["chat_ok"]:
        print_green(f"  ✓ 服务验证成功！模型回复: {result['chat_content']}")
    else:
        print_red(f"  ✗ 服务验证失败: {result.get('error', 'unknown')}")

    print()
    print_bold("=" * 60)
    print_bold("  部署完成！")
    print_bold("=" * 60)
    print_green(f"  反代地址: http://127.0.0.1:{port}")
    print_green(f"  OpenAI 兼容端点: http://127.0.0.1:{port}/v1/chat/completions")
    print_green(f"  Responses API 端点: http://127.0.0.1:{port}/v1/responses")
    print_green(f"  模型列表: http://127.0.0.1:{port}/v1/models")
    print_green(f"  健康检查: http://127.0.0.1:{port}/health")
    print()
    print_yellow("  在其他 Agent 中配置:")
    print_yellow(f"    Base URL: http://127.0.0.1:{port}/v1")
    print_yellow(f"    API Key: 任意值（如 sk-xxx）")
    print_yellow(f"    上游格式: Chat Completions（推荐）")
    print()
    if not info["jwt_token"]:
        print_red("  注意: JWT Token 未配置，请将 token 写入 token_live.txt 后重启服务")
        print()

    input("  按回车键退出...")


# ============ 命令行参数模式 ============
def cli_mode(args):
    """命令行参数模式（非交互）"""
    info = detect_workbuddy()
    port = args.port
    install_dir = args.install_dir or get_install_dir()

    print(f"端口: {port}")
    print(f"安装目录: {install_dir}")
    print(f"开机自启: {args.autostart}")

    # 复制文件
    source_dir = os.path.dirname(os.path.abspath(__file__))
    copied = copy_files(install_dir, source_dir)
    print(f"已复制: {copied}")

    # 创建启动脚本
    bat_path, vbs_path = create_startup_script(install_dir, port)
    print(f"启动脚本: {bat_path}")

    # 开机自启
    if args.autostart:
        success, path = setup_autostart(vbs_path)
        print(f"开机自启: {'成功' if success else '失败'} - {path}")

    # 启动
    if not args.no_start:
        status = start_proxy(install_dir, port)
        print(f"服务状态: {status}")

    print("部署完成！")


# ============ 主入口 ============
def main():
    parser = argparse.ArgumentParser(description="WorkBuddy AI 国际版反向代理 - 一键部署")
    parser.add_argument("--port", type=int, default=8899, help="监听端口（默认 8899）")
    parser.add_argument("--install-dir", type=str, help="安装目录")
    parser.add_argument("--autostart", action="store_true", help="设置开机自启")
    parser.add_argument("--no-start", action="store_true", help="部署后不启动服务")
    parser.add_argument("--stop", action="store_true", help="停止正在运行的反代服务")
    parser.add_argument("--remove-autostart", action="store_true", help="移除开机自启")
    parser.add_argument("--status", action="store_true", help="查看服务状态")

    args = parser.parse_args()

    if args.stop:
        port = args.port
        if stop_proxy(port):
            print_green(f"已停止端口 {port} 上的反代服务")
        else:
            print_yellow(f"未找到端口 {port} 上的反代服务")
        return

    if args.remove_autostart:
        removed = remove_autostart()
        if removed:
            print_green(f"已移除开机自启: {removed}")
        else:
            print_yellow("未找到开机自启项")
        return

    if args.status:
        port = args.port
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
            health = json.loads(resp.read().decode("utf-8"))
            print_green(f"服务运行中: http://127.0.0.1:{port}")
            print(f"  上游: {health.get('upstream')}")
            print(f"  JWT: {health.get('jwt')}")
        except:
            print_red(f"服务未运行: http://127.0.0.1:{port}")
        return

    # 如果有任何命令行参数（除了默认值），使用 CLI 模式
    if args.install_dir or args.autostart or args.no_start:
        cli_mode(args)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
