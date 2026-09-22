# 开发工具（可选）

随仓库提供的开发 / 测试脚本，**日常使用不需要**。请在仓库根目录下运行。

## test_custom.py — 自定义标签链路自测

模拟一张打印数据 PDF → 字段识别 → 版面渲染 → 干跑打印（不实际出纸），用于回归验证整条链路。

```bat
python 开发工具\test_custom.py
```

可选：设置环境变量 `WASH_LABEL_SAMPLE` 指向一张真实水洗唛 PDF，会额外验证真实样例的字段识别。

## render_test.py — 版面实验室

把任意水洗唛 PDF 渲染成 30×120mm 的裁剪 / 旋转 / 合成预览（顺时针、逆时针各一套），用于核对旋转方向与版面。

```bat
python 开发工具\render_test.py <输入.pdf> [输出目录]
```

输出：`info.json` + 各页的 `crop / rot / compose / full_rot` 预览图。
