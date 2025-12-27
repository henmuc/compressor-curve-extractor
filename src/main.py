import os
import sys
import traceback
from datetime import datetime
from collections import deque

import tkinter as tk
import matplotlib as mpl

_ENV_BACKEND = os.environ.get("MPLBACKEND")
_BACKEND_SOURCE = "auto"
if _ENV_BACKEND:
    mpl.use(_ENV_BACKEND, force=True)
    _BACKEND_SOURCE = f"env:{_ENV_BACKEND}"
else:
    try:
        mpl.use("QtAgg", force=True)
        import matplotlib.backends.backend_qtagg  # noqa: F401
        _BACKEND_SOURCE = "auto:QtAgg"
    except Exception:
        mpl.use("TkAgg", force=True)
        _BACKEND_SOURCE = "auto:TkAgg"

# 避免中文显示为方块：尽量使用常见中文字体，不影响无该字体的环境
mpl.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "sans-serif"]
mpl.rcParams["axes.unicode_minus"] = False

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from scipy.interpolate import PchipInterpolator
from PIL import Image
from tkinter import filedialog, messagebox, simpledialog, Tk

DEFAULT_IGVS = [0, 20, 40, 60, 80]
DEFAULT_NUM_POINTS = 10
DEFAULT_DESIGN_FLOW = 5776
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
LOG_PATH = os.path.join(BASE_DIR, "run.log")
CURRENT_STAGE = "init"
OVERLAY_TEXT = None
CANCEL_REASON = None
INTERACTION = None


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{CURRENT_STAGE}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def set_cancel_reason(reason):
    global CANCEL_REASON
    CANCEL_REASON = reason


def log_traceback():
    tb = traceback.format_exc()
    for line in tb.rstrip().splitlines():
        log(line)


class UserCancelled(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class InteractionManager:
    def __init__(self, fig, ax, close_state):
        self.fig = fig
        self.ax = ax
        self.close_state = close_state
        self.queue = deque()
        self.cid_click = fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.cid_key = fig.canvas.mpl_connect("key_press_event", self._on_key)

    def _on_click(self, event):
        if event.inaxes != self.ax:
            return
        if event.button != 1:
            return
        self.queue.append(("click", (event.xdata, event.ydata)))

    def _on_key(self, event):
        key = event.key
        if key in ("escape", "q"):
            self.queue.append(("cancel", None))
        elif key in ("b", "backspace"):
            self.queue.append(("back", None))
        elif key in ("enter", "return"):
            self.queue.append(("finish", None))

    def _ensure_alive(self):
        if self.close_state.get("closed"):
            set_cancel_reason("窗口已关闭")
            log("窗口已关闭")
            raise UserCancelled(CANCEL_REASON or "窗口已关闭")
        if self.fig is None or not plt.fignum_exists(self.fig.number):
            set_cancel_reason("窗口不存在")
            log("窗口不存在")
            raise UserCancelled(CANCEL_REASON or "窗口不存在")

    def _poll(self):
        self._ensure_alive()
        if self.queue:
            return self.queue.popleft()
        plt.pause(0.05)
        self._ensure_alive()
        if self.queue:
            return self.queue.popleft()
        return None

    def wait_single(self):
        while True:
            evt = self._poll()
            if evt is None:
                continue
            kind, payload = evt
            if kind == "click":
                return "ok", payload
            if kind == "back":
                return "back", None
            if kind == "cancel":
                set_cancel_reason("用户中止")
                log("用户通过键盘中止")
                raise UserCancelled(CANCEL_REASON or "用户中止")
            if kind == "finish":
                # ignore finish for single point
                continue

    def wait_many(self, overlay_base, step_label, update_overlay):
        points = []
        while True:
            overlay_msg = f"{overlay_base}\n已取点: {len(points)} 个。左键添加点，B 撤销上一个，回车结束，Q/ESC 中止。"
            update_overlay(overlay_msg)
            evt = self._poll()
            if evt is None:
                continue
            kind, payload = evt
            if kind == "click":
                points.append(payload)
                log(f"步骤 {step_label}: 添加点 {payload}")
            elif kind == "back":
                if points:
                    removed = points.pop()
                    log(f"步骤 {step_label}: 撤销点 {removed}")
                else:
                    log(f"步骤 {step_label}: 无可撤销点，返回重做本步骤")
                    return "back", []
            elif kind == "finish":
                log(f"步骤 {step_label}: 结束取点，共 {len(points)} 个")
                return "ok", points
            elif kind == "cancel":
                set_cancel_reason("用户中止")
                log("用户通过键盘中止")
                raise UserCancelled(CANCEL_REASON or "用户中止")


def set_stage(stage):
    global CURRENT_STAGE
    CURRENT_STAGE = stage
    log(f"stage={stage}")


def set_overlay(fig, text):
    global OVERLAY_TEXT
    if OVERLAY_TEXT is None:
        OVERLAY_TEXT = fig.text(
            0.01,
            0.99,
            text,
            ha="left",
            va="top",
            fontsize=11,
            color="white",
            bbox={"facecolor": "black", "alpha": 0.6, "pad": 6},
        )
    else:
        OVERLAY_TEXT.set_text(text)
    fig.canvas.draw_idle()


def announce_step(fig, step, message):
    log(f"步骤 {step}: {message}")
    if fig is not None:
        set_overlay(fig, f"步骤 {step}:\n{message}")


def ginput_single(manager, fig, ax, stage, step_label, overlay_text):
    set_cancel_reason(None)
    set_stage(stage)
    ax.set_title(overlay_text)
    announce_step(fig, step_label, overlay_text)
    while True:
        status, payload = manager.wait_single()
        if status == "back":
            log(f"步骤 {step_label}: 用户请求后退")
            return "back", None
        if status == "ok":
            log(f"步骤 {step_label}: 获取点 {payload}")
            return "ok", payload


def ginput_many(manager, fig, ax, stage, step_label, overlay_text):
    set_cancel_reason(None)
    set_stage(stage)
    ax.set_title(overlay_text)
    announce_step(fig, step_label, overlay_text)

    def updater(msg):
        set_overlay(fig, f"步骤 {step_label}:\n{msg}")

    status, pts = manager.wait_many(overlay_text, step_label, updater)
    if status == "back":
        return "back", (np.array([]), np.array([]))
    pts = np.array(pts)
    if pts.size == 0:
        return "ok", (np.array([]), np.array([]))
    x, y = zip(*pts)
    return "ok", (np.array(x), np.array(y))


def attach_close_logger(fig):
    state = {"closed": False}

    def _on_close(event):
        state["closed"] = True
        log(f"figure close_event fired at stage={CURRENT_STAGE}")

    fig.canvas.mpl_connect("close_event", _on_close)
    return state


def select_image():
    root = Tk()
    root.withdraw()
    root.update()
    path = filedialog.askopenfilename(
        filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")]
    )
    root.destroy()
    return path


def pixel_to_value(pixel, p1, p2, v1, v2):
    if p1 == p2:
        return np.full_like(pixel, v1, dtype=float) if isinstance(pixel, np.ndarray) else float(v1)
    scale = (v2 - v1) / (p2 - p1)
    return (pixel - p1) * scale + v1


def get_color(idx):
    colors = ['r', 'b', 'g', 'm', 'c', 'k']
    return colors[idx % len(colors)]


def prompt_float(prompt_text, title, default=None):
    while True:
        try:
            raw = input(prompt_text)
        except EOFError:
            raw = None
        except KeyboardInterrupt:
            set_cancel_reason("用户中止")
            log("用户在数值输入时中止")
            raise UserCancelled(CANCEL_REASON or "用户中止")

        if raw is None or raw == "":
            # No stdin (double-click) or empty: use dialog
            root = Tk()
            root.withdraw()
            try:
                ans = simpledialog.askstring(
                    title=title,
                    prompt=prompt_text,
                    initialvalue=str(default) if default is not None else None,
                    parent=root,
                )
            finally:
                root.destroy()
            if ans is None:
                set_cancel_reason("用户取消输入")
                log("用户取消数值输入对话框")
                raise UserCancelled(CANCEL_REASON or "用户取消输入")
            raw = ans

        try:
            return float(raw)
        except ValueError:
            log(f"输入的数值无效: {raw}; 请重新输入")
            prompt_text = "输入无效，请重新输入:"


def click_one(fig, ax, title_text, stage, step_label, hint, close_state):
    if INTERACTION is None:
        raise RuntimeError("Interaction manager not initialized")
    status, pts = ginput_single(INTERACTION, fig, ax, stage, step_label, hint)
    if status == "back":
        return "back", (None, None)
    return "ok", pts


def click_many(fig, ax, title_text, stage, step_label, hint, close_state):
    if INTERACTION is None:
        raise RuntimeError("Interaction manager not initialized")
    status, pts = ginput_many(INTERACTION, fig, ax, stage, step_label, hint)
    if status == "back":
        return "back", np.array([]), np.array([])
    px, py = pts
    return "ok", px, py


def choose_save_path(default_name="Compressor_Curve_Data.csv"):
    root = Tk()
    root.withdraw()
    try:
        path = filedialog.asksaveasfilename(
            title="选择导出 CSV 路径",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
    finally:
        root.destroy()
    return path


def parse_igv_list(text, default_list):
    if text is None:
        return default_list, "IGV 列表为空，已使用默认值。"
    cleaned = text.strip()
    if not cleaned:
        return default_list, "IGV 列表为空，已使用默认值。"
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    values = []
    for p in parts:
        try:
            values.append(float(p))
        except ValueError:
            return default_list, "IGV 列表格式无效，已回退默认值。"
    if not values:
        return default_list, "IGV 列表为空，已使用默认值。"
    values = sorted(set(values))
    return values, None


def parse_int_value(text, default_val, name):
    cleaned = (text or "").strip()
    if not cleaned:
        return default_val, f"{name} 为空，已使用默认值 {default_val}。"
    try:
        val = int(cleaned)
    except ValueError:
        return default_val, f"{name} 无效，已回退默认值 {default_val}。"
    if val <= 1:
        return default_val, f"{name} 需大于 1，已回退默认值 {default_val}。"
    return val, None


def parse_float_value(text, default_val, name):
    cleaned = (text or "").strip()
    if not cleaned:
        return default_val, f"{name} 为空，已使用默认值 {default_val}。"
    try:
        val = float(cleaned)
    except ValueError:
        return default_val, f"{name} 无效，已回退默认值 {default_val}。"
    return val, None


def show_welcome_dialog(default_igvs, default_num_points, default_design_flow):
    root = Tk()
    root.title("压缩机曲线提取器")
    root.resizable(False, False)

    info = (
        "欢迎使用压缩机曲线提取器。\n"
        "步骤：选图 -> 标定上下图坐标轴 -> 各 IGV 取曲线点 -> 插值对齐 -> 导出 CSV。\n"
        "提示：点击的是坐标轴刻度线与轴的交点（不是曲线点）。\n"
        "快捷键：B 后退一步，Q/ESC 中止。"
    )

    label = tk.Label(root, text=info, justify="left", padx=10, pady=8)
    label.grid(row=0, column=0, columnspan=2, sticky="w")

    tk.Label(root, text="IGV 列表（逗号分隔）:").grid(row=1, column=0, sticky="e", padx=6, pady=4)
    tk.Label(root, text="采样点数量 (num_points):").grid(row=2, column=0, sticky="e", padx=6, pady=4)
    tk.Label(root, text="设计流量 (design_flow):").grid(row=3, column=0, sticky="e", padx=6, pady=4)

    igv_entry = tk.Entry(root, width=36)
    igv_entry.insert(0, ", ".join(str(v).rstrip("0").rstrip(".") for v in default_igvs))
    igv_entry.grid(row=1, column=1, padx=6, pady=4)

    num_entry = tk.Entry(root, width=36)
    num_entry.insert(0, str(default_num_points))
    num_entry.grid(row=2, column=1, padx=6, pady=4)

    flow_entry = tk.Entry(root, width=36)
    flow_entry.insert(0, str(default_design_flow))
    flow_entry.grid(row=3, column=1, padx=6, pady=4)

    result = {"cancel": True}

    def on_start():
        igvs, igv_msg = parse_igv_list(igv_entry.get(), default_igvs)
        num_points, np_msg = parse_int_value(num_entry.get(), default_num_points, "采样点数量")
        design_flow, df_msg = parse_float_value(flow_entry.get(), default_design_flow, "设计流量")
        msgs = [m for m in (igv_msg, np_msg, df_msg) if m]
        if msgs:
            messagebox.showinfo("提示", "\n".join(msgs), parent=root)
        result.update({
            "cancel": False,
            "igvs": igvs,
            "num_points": num_points,
            "design_flow": design_flow,
        })
        root.destroy()

    def on_cancel():
        result["cancel"] = True
        root.destroy()

    btn_start = tk.Button(root, text="开始", width=10, command=on_start)
    btn_cancel = tk.Button(root, text="退出/取消", width=10, command=on_cancel)
    btn_start.grid(row=4, column=0, padx=6, pady=10)
    btn_cancel.grid(row=4, column=1, padx=6, pady=10, sticky="e")

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    if result.get("cancel"):
        return None
    return result["igvs"], result["num_points"], result["design_flow"]


def safe_pchip(x, y, x_new):
    # 去重 + 排序，避免插值报错
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    x_unique, idx = np.unique(x, return_index=True)
    y_unique = y[idx]

    if len(x_unique) < 2:
        raise ValueError("点太少，无法插值（至少需要2个不同的x点）")

    return PchipInterpolator(x_unique, y_unique)(x_new)


def main():
    log(f"Python 路径: {sys.executable}")
    log(f"Matplotlib 后端: {mpl.get_backend()} ({_BACKEND_SOURCE})")
    log(f"Conda 环境: {os.environ.get('CONDA_DEFAULT_ENV', 'unknown')}")
    log(f"日志文件: {LOG_PATH}")

    config = show_welcome_dialog(DEFAULT_IGVS, DEFAULT_NUM_POINTS, DEFAULT_DESIGN_FLOW)
    if config is None:
        log("用户取消启动")
        return
    target_igvs, num_points, design_flow = config
    log(f"IGV 列表: {target_igvs}")
    log(f"采样点数量: {num_points}，设计流量: {design_flow}")

    set_stage("select_image")
    announce_step(None, "1", "请选择图片文件（上图：压力-流量，下图：功率-流量，确保是上下两张图）。")
    img_path = select_image()
    if not img_path:
        log("退出：未选择图片")
        print("未选择图片，退出。")
        return

    try:
        img = Image.open(img_path)
    except Exception as e:
        log(f"打开图片失败：{e}")
        print(f"打开图片失败：{e}")
        return

    fig, ax = plt.subplots(figsize=(12, 8))
    close_state = attach_close_logger(fig)
    global INTERACTION
    INTERACTION = InteractionManager(fig, ax, close_state)
    ax.imshow(img)
    ax.axis("off")

    # Windows上更稳：让窗口真正进入事件循环
    log("show(block=False) before")
    plt.show(block=False)
    plt.pause(0.1)
    log("show(block=False) after")

    log("===== 标定坐标轴（上图：压力-流量；下图：功率-流量）=====")

    def run_calibration(steps):
        values = {}
        idx = 0
        while idx < len(steps):
            s = steps[idx]
            hint = (
                f"{s['overlay']}\n"
                "只需点击 1 次坐标轴刻度线对应数值的交点（不是曲线点）。"
                "\n左键=确认，B=后退一步，Q/ESC=中止。"
            )
            status, pt = click_one(
                fig,
                ax,
                s["overlay"],
                s["stage"],
                s["step"],
                hint,
                close_state,
            )
            if status == "back":
                if idx > 0:
                    idx -= 1
                    log("已后退到上一标定步骤，请重新点击。")
                else:
                    log("当前已是第一步，无法后退。")
                continue

            coord_val = pt[0] if s["coord"] == "x" else pt[1]
            values[s["pix_key"]] = coord_val
            num_val = prompt_float(s["prompt"], s["prompt_title"], default=s["default"])
            values[s["val_key"]] = num_val
            log(f"{s['stage']} 完成; 像素={coord_val}, 数值={num_val}")
            idx += 1
        return values

    top_steps = [
        {
            "stage": "calibrate_top_x1",
            "step": "2",
            "overlay": "上图（压力-流量）X轴起点：点击左端刻度线与轴交点（最小流量）。",
            "prompt": "上图 X轴 起始数值（例如最小流量 3000）:",
            "prompt_title": "上图 X轴 起始数值",
            "default": 3000,
            "coord": "x",
            "pix_key": "x1",
            "val_key": "v_x1",
        },
        {
            "stage": "calibrate_top_x2",
            "step": "3",
            "overlay": "上图（压力-流量）X轴终点：点击右端刻度线与轴交点（最大流量）。",
            "prompt": "上图 X轴 结束数值（例如最大流量 6000）:",
            "prompt_title": "上图 X轴 结束数值",
            "default": 6000,
            "coord": "x",
            "pix_key": "x2",
            "val_key": "v_x2",
        },
        {
            "stage": "calibrate_top_y1",
            "step": "4",
            "overlay": "上图（压力-流量）Y轴起点：点击下端刻度线与轴交点（最小压力）。",
            "prompt": "上图 Y轴 起始数值（例如最小压力 2）:",
            "prompt_title": "上图 Y轴 起始数值",
            "default": 2,
            "coord": "y",
            "pix_key": "y1",
            "val_key": "v_y1",
        },
        {
            "stage": "calibrate_top_y2",
            "step": "5",
            "overlay": "上图（压力-流量）Y轴终点：点击上端刻度线与轴交点（最大压力）。",
            "prompt": "上图 Y轴 结束数值（例如最大压力 11）:",
            "prompt_title": "上图 Y轴 结束数值",
            "default": 11,
            "coord": "y",
            "pix_key": "y2",
            "val_key": "v_y2",
        },
    ]

    bot_steps = [
        {
            "stage": "calibrate_bottom_x1",
            "step": "6",
            "overlay": "下图（功率-流量）X轴起点：点击左端刻度线与轴交点（最小流量）。",
            "prompt": "下图 X轴 起始数值（例如最小流量 3000）:",
            "prompt_title": "下图 X轴 起始数值",
            "default": 3000,
            "coord": "x",
            "pix_key": "bx1",
            "val_key": "bv_x1",
        },
        {
            "stage": "calibrate_bottom_x2",
            "step": "7",
            "overlay": "下图（功率-流量）X轴终点：点击右端刻度线与轴交点（最大流量）。",
            "prompt": "下图 X轴 结束数值（例如最大流量 6000）:",
            "prompt_title": "下图 X轴 结束数值",
            "default": 6000,
            "coord": "x",
            "pix_key": "bx2",
            "val_key": "bv_x2",
        },
        {
            "stage": "calibrate_bottom_y1",
            "step": "8",
            "overlay": "下图（功率-流量）Y轴起点：点击下端刻度线与轴交点（最小功率）。",
            "prompt": "下图 Y轴 起始数值（例如最小功率 250）:",
            "prompt_title": "下图 Y轴 起始数值",
            "default": 250,
            "coord": "y",
            "pix_key": "by1",
            "val_key": "bv_y1",
        },
        {
            "stage": "calibrate_bottom_y2",
            "step": "9",
            "overlay": "下图（功率-流量）Y轴终点：点击上端刻度线与轴交点（最大功率）。",
            "prompt": "下图 Y轴 结束数值（例如最大功率 550）:",
            "prompt_title": "下图 Y轴 结束数值",
            "default": 550,
            "coord": "y",
            "pix_key": "by2",
            "val_key": "bv_y2",
        },
    ]

    top_vals = run_calibration(top_steps)
    bot_vals = run_calibration(bot_steps)

    x1 = top_vals["x1"]
    x2 = top_vals["x2"]
    v_x1 = top_vals["v_x1"]
    v_x2 = top_vals["v_x2"]
    y1 = top_vals["y1"]
    y2 = top_vals["y2"]
    v_y1 = top_vals["v_y1"]
    v_y2 = top_vals["v_y2"]
    top_axis = (x1, x2, v_x1, v_x2, y1, y2, v_y1, v_y2)

    bx1 = bot_vals["bx1"]
    bx2 = bot_vals["bx2"]
    bv_x1 = bot_vals["bv_x1"]
    bv_x2 = bot_vals["bv_x2"]
    by1 = bot_vals["by1"]
    by2 = bot_vals["by2"]
    bv_y1 = bot_vals["bv_y1"]
    bv_y2 = bot_vals["bv_y2"]
    bot_axis = (bx1, bx2, bv_x1, bv_x2, by1, by2, bv_y1, bv_y2)

    final_rows = []

    for i, igv in enumerate(target_igvs):
        color = get_color(i)
        log(f"===== IGV = {igv} =====")
        step_base = 10 + i * 2
        step_top = str(step_base)
        step_bot = str(step_base + 1)
        stage_top = f"igv_{igv}_top_points"
        stage_bot = f"igv_{igv}_bottom_points"

        while True:
            status_top, px, py = click_many(
                fig,
                ax,
                f"IGV={igv} 上图（压力-流量）：点击曲线上的多个点，按回车结束；B 撤销上一点；Q/ESC 中止。",
                stage_top,
                step_top,
                f"IGV={igv} 上图（压力-流量）取点：\n- 左键多次点击曲线点\n- 回车结束当前曲线\n- B 撤销上一点；Q/ESC 中止\n- 如图片不是上下两图，请确认",
                close_state,
            )
            if status_top == "back":
                log(f"IGV={igv} 上图取点被后退，重新取点")
                continue
            if px.size == 0:
                log(f"IGV={igv} 上图未取点，跳过")
                break

            q_p = pixel_to_value(px, *top_axis[:4])
            p_val = pixel_to_value(py, *top_axis[4:])
            ax.plot(px, py, color + "o-", linewidth=1.5)

            skip_igv = False
            while True:
                status_bot, kx, ky = click_many(
                    fig,
                    ax,
                    f"IGV={igv} 下图（功率-流量）：点击曲线上的多个点，按回车结束；B 撤销上一点；Q/ESC 中止。",
                    stage_bot,
                    step_bot,
                    f"IGV={igv} 下图（功率-流量）取点：\n- 左键多次点击曲线点\n- 回车结束当前曲线\n- B 撤销上一点；Q/ESC 中止\n- 如图片不是上下两图，请确认",
                    close_state,
                )
                if status_bot == "back":
                    log(f"IGV={igv} 下图取点被后退，重新取点")
                    continue
                if kx.size == 0:
                    log(f"IGV={igv} 下图未取点，跳过")
                    skip_igv = True
                    break

                q_k = pixel_to_value(kx, *bot_axis[:4])
                kw_val = pixel_to_value(ky, *bot_axis[4:])
                ax.plot(kx, ky, color + "s-", linewidth=1.5)
                break

            if skip_igv:
                break

            # 对齐区间
            q_min = max(np.min(q_p), np.min(q_k))
            q_max = min(np.max(q_p), np.max(q_k))
            if q_max <= q_min:
                log(f"IGV={igv} 两条曲线流量区间无交集，跳过")
                break

            q_std = np.linspace(q_max, q_min, num_points)

            try:
                p_interp = safe_pchip(q_p, p_val, q_std)
                kw_interp = safe_pchip(q_k, kw_val, q_std)
            except Exception as e:
                log(f"IGV={igv} 插值失败：{e}")
                break

            comments = [""] * num_points
            if igv == 0:
                idx = int(np.argmin(np.abs(q_std - design_flow)))
                if abs(q_std[idx] - design_flow) < 100:
                    q_std[idx] = design_flow
                    comments[idx] = "design_point"

            for q, p, kw, cmt in zip(q_std, p_interp, kw_interp, comments):
                final_rows.append([igv, int(round(q)), round(float(p), 2), round(float(kw), 1), cmt])

            plt.draw()
            plt.pause(0.01)
            break

    final_step = 10 + len(target_igvs) * 2
    set_stage("export_csv")
    announce_step(fig, str(final_step), "保存 CSV：选择导出路径")
    save_path = choose_save_path("Compressor_Curve_Data.csv")
    if not save_path:
        log("用户取消保存，未导出 CSV。")
        ax.set_title("已取消保存，未导出。按 Q 退出或关闭窗口。")
        done_step = str(final_step + 1)
        set_stage("done")
        announce_step(fig, done_step, "已取消保存，未导出。按 Q/ESC 可中止。")
        plt.show()
        log("退出：用户取消保存")
        return

    df = pd.DataFrame(final_rows, columns=["IGV_deg", "Q_Nm3hr", "Pdis_bar_g", "Power_kW", "comment"])
    df.to_csv(save_path, index=False, encoding="utf-8-sig")
    log(f"CSV 已导出到 {save_path}；共 {len(df)} 行")

    ax.set_title(f"完成：已导出 {save_path}")
    done_step = str(final_step + 1)
    set_stage("done")
    announce_step(fig, done_step, f"完成。已导出到：{save_path}\n关闭窗口或按 Q/ESC 退出。")
    log(f"about to final show; close_state={close_state}")
    plt.show()  # 保持窗口不立即关闭
    log("退出：正常结束")


if __name__ == "__main__":
    try:
        main()
    except UserCancelled as exc:
        log(f"退出：用户中止；原因={exc.reason}")
    except KeyboardInterrupt:
        log("退出：用户中止 (KeyboardInterrupt)")
    except Exception:
        log("退出：未处理异常，正在打印 traceback")
        log_traceback()
        traceback.print_exc()
