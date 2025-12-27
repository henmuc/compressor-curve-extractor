# Compressor Curve Extractor

版本：0.1.0

中文简介：从压缩机特性曲线截图中交互式标定坐标轴、采点并导出 CSV 数据（适用于上图“压力-流量”、下图“功率-流量”的两张图组合）。

English (short): Interactive tool to calibrate axes, pick curve points, and export compressor curve data to CSV.

## 功能特性
- 交互式标定：点击坐标轴刻度交点并输入真实数值
- 多 IGV 批量采点：按 IGV 列表循环取点
- 自动插值对齐：输出统一采样点数
- 可选保存路径：导出 CSV
- GUI 友好：欢迎界面、清晰步骤提示、可后退/中止

## 环境依赖
- Windows + Anaconda/Miniconda
- 推荐在 conda 环境中安装依赖（可用 conda-forge）：
```powershell
conda create -n compressor python=3.10 -y
conda activate compressor
conda install -c conda-forge numpy pandas matplotlib scipy pillow pyside6 -y
```
说明：
- 程序会优先使用 QtAgg 后端（PySide6/PyQt），若不可用则回退到 TkAgg。
- `requirements.txt` 为 `conda list --export` 导出，适用于 conda 环境复现。

## 运行方式
### 命令行
```powershell
conda run -n compressor python -m src.main
```

### Windows 双击启动
- 双击 `Run_Compressor_Extractor.bat`
- 启动器会自动定位 conda 并在 `compressor` 环境中运行

## 使用步骤（简要）
1) 欢迎界面：可设置 IGV 列表、采样点数、设计流量；不修改直接开始
2) 选图：确认图片包含“上图压力-流量 / 下图功率-流量”
3) 标定坐标轴：按提示依次点击 X 轴左端/右端、Y 轴下端/上端（刻度线与轴交点）
4) 取曲线点：每个 IGV 在上图/下图分别取点，回车结束
5) 导出 CSV：选择保存路径

快捷键：
- B / Backspace：后退一步（标定或取点撤销）
- Enter：结束当前曲线取点
- Q / ESC：中止并退出

## 常见问题
1) QtAgg 不可用：
   - 安装 PySide6 或 PyQt：`conda install -c conda-forge pyside6 -y`
2) 窗口显示中文方块：
   - 安装 Windows 中文字体（微软雅黑/黑体）
3) 双击启动后报 “conda.exe not found”：
   - 安装/修复 Anaconda 或把 conda 加到 PATH
4) 环境名不一致：
   - 请确保环境名为 `compressor`

## 目录结构
- `src/main.py` 主程序
- `Run_Compressor_Extractor.bat` 双击启动器
- `Run_Compressor_Extractor.ps1` 可选 PowerShell 启动器
