# 开发工具（可选）

随仓库提供的开发/测试脚本，**日常使用不需要**。请在仓库根目录下运行。

## render_test.py — 版面实验室

把任意水洗唛 PDF 渲染成 30×120mm 的裁剪 / 旋转 / 合成预览（顺时针、逆时针各一套），用于核对旋转方向与版面。

```bat
python 开发工具\render_test.py <输入.pdf> [输出目录]
```

输出：`info.json` + 各页的 `crop / rot / compose / full_rot` 预览图。

> 注：原「链路自测（test_custom.py）」依赖已下线的编辑类组件，已移至 `extras\test_custom.py` 存档。
