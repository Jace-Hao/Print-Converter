《使用说明与交付报告.docx》生成器（备用工具）

- generate_docx.js：用 Node.js + docx 库生成交付文档的脚本。
- 日常使用不需要它；仅在需要修改、重新生成文档时使用。
- 重新生成方式：安装 Node.js 与 docx 库（npm install docx）后运行 node generate_docx.js，
  会在工具主目录生成《使用说明与交付报告.docx》；生成后建议再执行 docx 技能自带的后处理
  （目录占位注入、页脚域修复）并运行 postcheck 自检，以保证文档质量。
