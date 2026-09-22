// 水洗唛打印助手 - 交付文档生成器（docx-js）
// 生成《水洗唛打印助手 · 使用说明与交付报告》
// 规范来源：docx skill（报告场景 / Profile A 字体 / R1 封面 / CM-2 配色 / 三线外框横线表格）
"use strict";

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, WidthType, BorderStyle, ShadingType,
  Footer, PageNumber, NumberFormat, SectionType, TableOfContents,
  TableLayoutType,
} = require("docx");
const fs = require("fs");

// ==================== 配色（CM-2 Blue Orange） ====================
const C = {
  bg: "FEFEFE",
  primary: "1284BA",
  accent: "FF862F",
  body: "000000",
  muted: "606060",
  innerLine: "D8E4EC",
  headerText: "FFFFFF",
};
const COVER_PALETTE = {
  bg: C.bg, titleColor: C.primary, subtitleColor: C.muted,
  metaColor: "707070", footerColor: "A0A0A0", accent: C.accent,
};

// ==================== 封面 Recipe R1（照搬 design-system 的实现） ====================
const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };

function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const breakAfter = new Set([
    ..."，。、；：！？",
    ..."的与和及之在于为",
    ..."-_—–·/",
    ..." \t",
  ]);
  const lines = [];
  let remaining = title;
  while (remaining.length > charsPerLine) {
    let breakAt = -1;
    for (let i = charsPerLine; i >= Math.floor(charsPerLine * 0.6); i--) {
      if (i < remaining.length && breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
    }
    if (breakAt === -1) {
      const limit = Math.min(remaining.length, Math.ceil(charsPerLine * 1.3));
      for (let i = charsPerLine + 1; i < limit; i++) {
        if (breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
      }
    }
    if (breakAt === -1) {
      breakAt = charsPerLine;
      const prevChar = remaining[breakAt - 1];
      const nextChar = remaining[breakAt];
      if (prevChar && nextChar && !breakAfter.has(prevChar) && !breakAfter.has(nextChar) &&
          /[\u4e00-\u9fff]/.test(prevChar) && /[\u4e00-\u9fff]/.test(nextChar)) {
        breakAt = breakAt - 1;
      }
    }
    lines.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }
  if (remaining) lines.push(remaining);
  if (lines.length > 1 && lines[lines.length - 1].length <= 2) {
    const last = lines.pop();
    lines[lines.length - 1] += last;
  }
  return lines;
}

function calcTitleLayout(title, maxWidthTwips, preferredPt, minPt) {
  preferredPt = preferredPt || 40;
  minPt = minPt || 24;
  const charWidth = (pt) => pt * 20;
  const charsPerLine = (pt) => Math.floor(maxWidthTwips / charWidth(pt));
  let titlePt = preferredPt;
  let lines;
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) {
    const cpl = charsPerLine(minPt);
    lines = splitTitleLines(title, cpl);
    titlePt = minPt;
  }
  return { titlePt, titleLines: lines };
}

function calcCoverSpacing(params) {
  const p = Object.assign({
    titleLineCount: 1, titlePt: 36, hasSubtitle: false,
    hasEnglishLabel: false, metaLineCount: 0,
    fixedHeight: 800, pageHeight: 16838, marginTop: 0, marginBottom: 0,
  }, params);
  const SAFETY = 1200;
  const usableHeight = p.pageHeight - p.marginTop - p.marginBottom - SAFETY;
  const titleHeight = p.titleLineCount * (p.titlePt * 23 + 200);
  const subtitleHeight = p.hasSubtitle ? (12 * 23 + 600) : 0;
  const englishLabelHeight = p.hasEnglishLabel ? (9 * 23 + 600) : 0;
  const metaHeight = p.metaLineCount * (10 * 23 + 100);
  const implicitParaHeight = 3 * 300;
  const contentHeight = titleHeight + subtitleHeight + englishLabelHeight + metaHeight + p.fixedHeight + implicitParaHeight;
  const remainingSpace = usableHeight - contentHeight;
  const safeRemaining = Math.max(remainingSpace, 400);
  const FOOTER_MIN = 800;
  const rawTop = Math.floor(safeRemaining * 0.45);
  const rawBottom = Math.floor(safeRemaining * 0.45);
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  const midSpacing = Math.max(safeRemaining - topSpacing - bottomSpacing, 0);
  return { topSpacing, midSpacing, bottomSpacing };
}

function buildCoverR1(config) {
  const P = config.palette;
  const padL = 1200, padR = 800;
  const availableWidth = 11906 - padL - padR - 300;
  const tl = calcTitleLayout(config.title, availableWidth, 40, 24);
  const titlePt = tl.titlePt, titleLines = tl.titleLines;
  const titleSize = titlePt * 2;
  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel,
    metaLineCount: (config.metaLines || []).length,
    fixedHeight: 400,
  });
  const accentLeft = { style: BorderStyle.SINGLE, size: 8, color: P.accent, space: 12 };
  const children = [];
  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));
  if (config.englishLabel) {
    children.push(new Paragraph({
      indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: P.accent, space: 8 } },
      children: [new TextRun({
        text: config.englishLabel.split("").join("  "),
        size: 18, color: P.accent, font: { ascii: "Calibri", eastAsia: "SimHei" }, characterSpacing: 40,
      })],
    }));
  }
  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      indent: { left: padL },
      spacing: { after: i < titleLines.length - 1 ? 100 : 300, line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: titleLines[i], size: titleSize, bold: true, color: P.titleColor, font: { eastAsia: "SimHei", ascii: "Arial" } })],
    }));
  }
  if (config.subtitle) {
    children.push(new Paragraph({
      indent: { left: padL }, spacing: { after: 800 },
      children: [new TextRun({ text: config.subtitle, size: 24, color: P.subtitleColor, font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }
  for (const line of (config.metaLines || [])) {
    children.push(new Paragraph({
      indent: { left: padL + 200 }, spacing: { after: 80 },
      border: { left: accentLeft },
      children: [new TextRun({ text: line, size: 24, color: P.metaColor, font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }
  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));
  children.push(new Paragraph({
    indent: { left: padL, right: padR },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: P.accent, space: 8 } },
    spacing: { before: 200 },
    children: [
      new TextRun({ text: config.footerLeft || "", size: 16, color: P.footerColor, font: { ascii: "Arial" } }),
      new TextRun({ text: "                                        " }),
      new TextRun({ text: config.footerRight || "", size: 16, color: P.footerColor, font: { ascii: "Arial" } }),
    ],
  }));
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: P.bg },
        borders: noBorders,
        children,
      })],
    })],
  })];
}

// ==================== 正文构件 ====================
const F_HEAD = { ascii: "Times New Roman", eastAsia: "SimHei" };
const F_BODY = { ascii: "Times New Roman", eastAsia: "SimSun" };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER, keepNext: true,
    spacing: { before: 360, after: 160, line: 312 },
    children: [new TextRun({ text, bold: true, size: 32, font: F_HEAD, color: C.body })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2, keepNext: true,
    spacing: { before: 280, after: 120, line: 312 },
    children: [new TextRun({ text, bold: true, size: 30, font: F_HEAD, color: C.body })],
  });
}
function p(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: 480 },
    spacing: { line: 312, after: 120 },
    children: [new TextRun({ text, size: 24, font: F_BODY, color: C.body })],
  });
}
function flow(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 120, after: 160, line: 312 },
    children: [new TextRun({ text, bold: true, size: 21, font: F_BODY, color: C.body })],
  });
}
function bullet(text) {
  return new Paragraph({
    bullet: { level: 0 }, spacing: { line: 312, after: 60 },
    children: [new TextRun({ text, size: 24, font: F_BODY, color: C.body })],
  });
}
function cap(text) {
  return new Paragraph({
    keepNext: true, alignment: AlignmentType.CENTER, spacing: { before: 200, after: 80, line: 312 },
    children: [new TextRun({ text, bold: true, size: 21, font: F_HEAD, color: C.body })],
  });
}
function cellPar(text, opts) {
  opts = opts || {};
  return new Paragraph({
    spacing: { line: 312, before: 40, after: 40 },
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
    children: [new TextRun({ text, size: 21, font: F_BODY, color: opts.color || C.body, bold: !!opts.bold })],
  });
}
function makeTable(header, rows, widths) {
  const borderTop = { style: BorderStyle.SINGLE, size: 2, color: C.primary };
  const borderBottom = { style: BorderStyle.SINGLE, size: 2, color: C.primary };
  const borderInner = { style: BorderStyle.SINGLE, size: 1, color: C.innerLine };
  const borderNone = { style: BorderStyle.NONE };
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: borderTop, bottom: borderBottom, left: borderNone, right: borderNone,
      insideHorizontal: borderInner, insideVertical: borderNone,
    },
    rows: [
      new TableRow({
        tableHeader: true, cantSplit: true,
        children: header.map((t, i) => new TableCell({
          width: { size: widths[i], type: WidthType.PERCENTAGE },
          shading: { type: ShadingType.CLEAR, fill: C.primary },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [cellPar(t, { bold: true, color: C.headerText })],
        })),
      }),
      ...rows.map((r) => new TableRow({
        cantSplit: true,
        children: r.map((t, i) => new TableCell({
          width: { size: widths[i], type: WidthType.PERCENTAGE },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [cellPar(String(t))],
        })),
      })),
    ],
  });
}

// ==================== 正文内容 ====================
function bodyChildren() {
  const out = [];

  // ---- 1 交付概述 ----
  out.push(h1("1. 交付概述"));
  out.push(p("本报告面向「星期衣精致洗衣」门店的水洗唛打印场景：洗衣管家打印出的水洗唛为 120×30 毫米横版版面，而门店标签机（佳博 GP-9134T）按 30×120 毫米竖版出纸。此前每张标签都需要人工「另存 PDF → 旋转 → 再打印」，步骤繁琐且容易出错。"));
  out.push(p("「水洗唛打印助手」v2.0 已完成开发并通过全链路实测。本版本按现场反馈进行了架构升级：由工具自建一台专属虚拟打印机「水洗唛打印助手」，打印任务不再经过第三方虚拟打印机，直接进入工具完成转换并输出；同时新增「布局设计器」，水洗唛的版面布局可以自由设计。"));
  out.push(cap("表 1　交付成果清单"));
  out.push(makeTable(["成果", "内容", "位置"], [
    ["自动打印工具", "虚拟打印机捕获、截取对齐、旋转、送印、归档、日志", "E:\\软件开发\\水洗唛打印助手"],
    ["专属虚拟打印机", "「水洗唛打印助手」：由工具创建与管理，打印任务自动写入捕获文件", "安装虚拟打印机.cmd / 卸载虚拟打印机.cmd"],
    ["布局设计器", "自由设计水洗唛版面（文本/条码/线条），可打印与启用自动重排", "打开布局设计器.cmd"],
    ["控制面板", "一键启停、测试打印、查看日志与目录、虚拟打印机状态", "打开控制面板.cmd"],
    ["操作脚本", "启动/停止监视、校准打印、开机自启安装等", "工具目录（根目录）"],
    ["使用说明（本文）", "原理、操作、校准、常见问题", "使用说明与交付报告.docx / 使用说明.html"],
  ], [16, 49, 35]));
  out.push(p("截至 2026 年 9 月 22 日，v2.0 核心功能全部实测通过（详见第 5 章）：虚拟打印机的创建、高速捕获（连续打印无丢失）、真实样例版面对齐、物理出纸烟测均已完成；旋转方向默认采用「顺时针」，并已提供两版校准唛供现场比对，确认后即为最终配置。"));

  // ---- 2 背景与方案设计 ----
  out.push(h1("2. 背景与方案设计"));
  out.push(h2("2.1 原有流程的问题"));
  out.push(p("原流程需要人工执行四个步骤：打印预览、另存为 PDF、旋转 90 度、再发送到标签机。存在三个问题：一是操作繁琐，每张标签都要重复；二是旋转依靠人工判断，容易方向出错；三是中间 PDF 分散各处，日后补打、对账不便。v1.0 曾借助第三方虚拟打印机的自动保存目录完成捕获，但依赖外部软件（pdfFactory）的配置，链路较长。"));
  out.push(h2("2.2 自动化方案（v2.0 架构）"));
  out.push(p("工具升级为「自建虚拟打印机」架构：由工具创建一台专属虚拟打印机「水洗唛打印助手」（基于 Windows 内置的 Microsoft Print To PDF 驱动 + 文件端口）。洗衣管家打印水洗唛时选择该打印机，打印任务会被静默写成一个捕获文件；工具以高频监视捕获文件的每个新版本，自动完成 截取标签区域 → 版面对齐 → 旋转排版 → 送印 → 归档 全流程。整个过程不再经过 pdfFactory 等第三方软件，链路更短、更稳定。"));
  out.push(flow("打印水洗唛 → 捕获文件写入 → 高速捕获 → 截取对齐 → 旋转 90° 并排版 → 打印到标签机 → 自动归档"));
  out.push(h2("2.3 关键设计决策"));
  out.push(bullet("不侵入原则：不改造洗衣管家、不修改其业务数据，只新增一台打印设备并使用打印链路；洗衣管家配置改动前均已备份，可随时回退。"));
  out.push(bullet("自建虚拟打印机：打印机由工具安装脚本创建（约 10 秒，需管理员确认一次），日常无需维护；可随时用卸载脚本移除。"));
  out.push(bullet("安全闸：只自动处理内容位于标签区域内的捕获文件；不符合的文件（如整页文档）会被移入 out\\hold 目录待人工确认，避免误打。"));
  out.push(bullet("可追溯：每个标签自动归档 PDF 原件与位图预览，补打、对账、复查都方便。"));
  out.push(bullet("默认全自动：捕获成功即自动送印；如需「先预览再打印」，可将自动化模式切换为 dry_run（只预览不打印）。"));

  // ---- 3 快速上手 ----
  out.push(h1("3. 快速上手"));
  out.push(h2("3.1 日常使用"));
  out.push(bullet("确认虚拟打印机已就绪：打开控制面板点击「虚拟打印机」查看状态（本机已安装；如被删除，双击「安装虚拟打印机.cmd」重新安装）。"));
  out.push(bullet("双击「启动监视.cmd」启动后台监视（保持窗口开着；关闭窗口即停止监视）。"));
  out.push(bullet("照常打印水洗唛：打印时选择「水洗唛打印助手」。"));
  out.push(bullet("完成：工具自动截取、旋转并打印到「水洗唛」，同时归档。"));
  out.push(h2("3.2 控制面板"));
  out.push(p("如果不习惯命令行窗口，可双击「打开控制面板.cmd」使用图形面板："));
  out.push(cap("表 2　控制面板按钮说明"));
  out.push(makeTable(["按钮", "功能"], [
    ["启动监视 / 停止监视", "打开或停止后台监视进程"],
    ["打印校准唛（两版）", "打印顺时针、逆时针两版校准标签"],
    ["处理 PDF 文件…", "手动选择一个 PDF 进行旋转打印"],
    ["布局设计器", "打开布局设计器（设计版面 → 预览 → 打印）"],
    ["虚拟打印机", "查看虚拟打印机状态；未就绪可一键安装/修复"],
    ["监视目录 / 归档目录 / 预览目录 / 日志目录", "一键打开对应文件夹"],
    ["使用说明", "打开本文档的 HTML 版本"],
  ], [42, 58]));
  out.push(h2("3.3 第一次使用建议"));
  out.push(p("建议先手动打印一张真实水洗唛试跑：确认标签方向、内容完整性后，再进入日常使用。若方向与预期相反，按第 4 章切换旋转方向即可。测试期间打印的测试唛（含校准唛）内容均为样例数据，可直接丢弃。"));

  // ---- 4 校准与设置 ----
  out.push(h1("4. 校准与设置"));
  out.push(h2("4.1 旋转方向校准"));
  out.push(p("不同门店的标签机安装方向、耗材方向可能存在差异，工具提供两版校准样张：双击「打印校准唛.cmd」，会连续打印两张测试标签——第 1 版为顺时针旋转、第 2 版为逆时针旋转。选择与门店日常输出一致的方向后，在配置文件中设置。"));
  out.push(p("默认值：rotate_dir 为 cw（顺时针）。如需改为逆时针：将 config.json 中 rotate_dir 的值改为 ccw，保存后重新启动监视即可生效。"));
  out.push(h2("4.2 常用配置项"));
  out.push(cap("表 3　主要配置项说明（config.json）"));
  out.push(makeTable(["配置项", "默认值", "说明"], [
    ["watch.dirs", "自动保存目录、D:\\水洗唛输出、inbox", "需要监视的目录列表"],
    ["watch.stable_seconds", "8", "文件连续多少秒不再变化才判定为写入完成"],
    ["pipeline.rotate_dir", "cw", "旋转方向：cw 顺时针 / ccw 逆时针"],
    ["pipeline.offset_mm", "[0, 0]", "打印位置微调（毫米）；如整体右移 0.5 毫米填 [0.5, 0]"],
    ["pipeline.crop_pad_mm", "0.5", "内容裁剪留边（毫米）"],
    ["print.printer", "水洗唛", "目标标签机名称"],
    ["print.dither", "true", "灰度抖动；如文字发虚可改为 false"],
    ["capture.slot_file", "spool\\capture.pdf", "虚拟打印机捕获文件位置（勿改）"],
    ["capture.crop_mm", "[0, 0, 120, 30]", "从捕获页左上角截取的标签区域（毫米）"],
    ["capture.shift_mm", "[2.03, 0]", "版面对齐微调（对齐旧版式，一般勿改）"],
    ["pipeline.render_mode", "rotate", "rotate 原样旋转；layout 按布局设计器模板重排"],
    ["pipeline.layout_template", "默认", "layout 模式使用的模板名"],
    ["automation.mode", "auto", "auto 自动打印；dry_run 只预览不打印"],
  ], [34, 20, 46]));
  out.push(p("配置文件位于工具目录根下（config.json），可用记事本编辑；修改后重启监视生效。"));
  out.push(h2("4.3 虚拟打印机维护"));
  out.push(p("虚拟打印机「水洗唛打印助手」由工具创建和管理："));
  out.push(bullet("状态检查：控制面板 →「虚拟打印机」，查看端口与设备状态。"));
  out.push(bullet("安装/修复：双击「安装虚拟打印机.cmd」（会请求一次管理员确认），可重复运行。"));
  out.push(bullet("卸载：双击「卸载虚拟打印机.cmd」，移除虚拟打印机与端口（不影响标签机与洗衣管家）。"));
  out.push(bullet("说明：虚拟打印机基于 Windows 内置 PDF 驱动，不额外安装任何软件；打印任务写入 spool\\capture.pdf 捕获文件，由工具实时读取。"));

  // ---- 5 测试与验收记录 ----
  out.push(h1("5. 测试与验收记录"));
  out.push(h2("5.1 测试环境"));
  out.push(makeTable(["项目", "说明"], [
    ["门店工作机", "Windows 11（xqyjzxy）"],
    ["洗衣管家", "单机版 v6.1.23"],
    ["虚拟打印机", "「水洗唛打印助手」（工具自建：Microsoft Print To PDF 驱动 + 文件端口）"],
    ["标签打印机", "佳博 GP-9134T（水洗唛，300 点每英寸）"],
    ["标签规格", "30×120 毫米竖版（设计版面 120×30 毫米横版）"],
    ["工具版本", "v2.0（Python 3.14）"],
  ], [30, 70]));
  out.push(h2("5.2 测试记录"));
  out.push(makeTable(["序号", "测试项目", "方法", "结果"], [
    ["1", "虚拟打印机创建", "执行安装脚本创建「水洗唛打印助手」并检查端口/驱动", "通过（约 10 秒完成，可重复运行）"],
    ["2", "捕获链路", "打印测试页到「水洗唛打印助手」，检查捕获文件落盘", "通过（静默写入，无弹窗）"],
    ["3", "连打抗丢失", "瞬间连续发起 3 笔打印任务 × 3 轮", "通过（9/9 全部捕获，逐张处理）"],
    ["4", "版面对齐", "真实样例经新链路与旧版式逐像素比对", "通过（位置偏差 ≤1 像素；对齐补偿生效）"],
    ["5", "旋转与排版", "干跑模式生成标签位图并检查尺寸", "通过（30×120 毫米、300 点每英寸，尺寸精确）"],
    ["6", "安全闸", "读取干扰页面（整页文档）测试校验", "通过（正确拦下并转存 out\\hold）"],
    ["7", "物理烟测", "真实样例经全链路打印实体标签一张", "通过（标签机实际出纸，边距与原版式一致）"],
    ["8", "界面自检", "控制面板、布局设计器窗口冒烟", "通过（窗口正常打开，无报错）"],
  ], [8, 18, 44, 30]));
  out.push(h2("5.3 待确认事项与验收结论"));
  out.push(p("待确认事项：① 旋转方向需现场目检两张校准唛后最终确认（默认顺时针）；② 洗衣管家打印设备已指向「水洗唛打印助手」，建议下一次实际打印时留意首张标签（必要时重启一次洗衣管家）。测试期间打印的测试唛内容均为样例数据，可直接丢弃。"));
  out.push(p("验收结论：除上述现场目检外，v2.0 全部验收项均已通过，工具具备投入日常使用的条件。"));

  // ---- 6 目录与文件说明 ----
  out.push(h1("6. 目录与文件说明"));
  out.push(cap("表 4　目录与关键文件"));
  out.push(makeTable(["名称", "说明"], [
    ["工具主目录", "E:\\软件开发\\水洗唛打印助手"],
    ["app\\", "程序代码（watcher 监视引擎、capture 捕获器、layout 布局引擎、designer 布局设计器等）"],
    ["out\\archive\\", "归档：每个标签的 PDF 原件（补打用）"],
    ["out\\previews\\", "预览：处理后的标签位图"],
    ["out\\logs\\", "运行日志（排查问题先看这里）"],
    ["inbox\\", "手动投递目录：放入 PDF 会被自动处理"],
    ["spool\\", "虚拟打印机捕获文件与作业暂存（运行数据）"],
    ["templates\\", "布局模板（布局设计器保存的位置）"],
    ["config.json", "配置文件（旋转方向、偏移、监视目录、捕获与布局等）"],
    ["安装虚拟打印机.cmd / 卸载虚拟打印机.cmd", "创建/移除虚拟打印机「水洗唛打印助手」（需管理员确认一次）"],
    ["打开布局设计器.cmd", "布局设计器入口（设计 → 预览 → 打印）"],
  ], [30, 70]));

  // ---- 7 常见问题 ----
  out.push(h1("7. 常见问题"));
  out.push(makeTable(["问题", "处理"], [
    ["打印后没有自动出标签？", "检查打印时选择的打印机是否为「水洗唛打印助手」，以及「启动监视」是否仍在运行；并查看 out\\logs 当天日志。"],
    ["「水洗唛打印助手」打印机不见了？", "双击「安装虚拟打印机.cmd」重新安装（约 10 秒）；或打开控制面板点「虚拟打印机」查看状态。"],
    ["想暂停自动处理？", "关闭「启动监视」窗口，或在控制面板点击「停止监视」。"],
    ["标签打印出来方向不对？", "见 4.1 节：切换 rotate_dir 后重新启动监视。"],
    ["想改水洗唛的版面布局？", "双击「打开布局设计器.cmd」自由排版；满意后勾选「用于自动打印」，之后每张标签按你的布局重排（识别失败会自动回退为原样旋转）。"],
    ["有旧标签需要补打？", "在 out\\archive 找到对应 PDF，拖到「把PDF拖到这里处理.cmd」上即可。"],
    ["某些打印内容没有自动输出？", "内容不在标签区域内的文件会被安全闸拦下（移入 out\\hold），防止误打。"],
    ["电脑重启后需要手动启动吗？", "默认需要；运行一次「安装开机自启.ps1」即可随登录自动运行。"],
    ["会不会影响洗衣管家？", "不会。工具不修改洗衣管家程序与数据，仅使用打印链路。"],
  ], [36, 64]));

  // ---- 8 已知限制与注意事项 ----
  out.push(h1("8. 已知限制与注意事项"));
  out.push(bullet("虚拟打印机「水洗唛打印助手」基于系统内置驱动，无需额外软件；安装/修复/卸载均通过脚本一键完成。"));
  out.push(bullet("旧通道（pdfFactory「水洗唛转换」自动保存目录）仍被工具兼容监听，作为兜底；如从旧地址打印，同样会被自动处理。"));
  out.push(bullet("捕获文件为「最近一次任务」覆盖写入；工具以高频监视抓取每个新任务，连续打印已实测无丢失；极端场景可对照归档记录补打。"));
  out.push(bullet("工具默认不随开机启动；需要时运行「安装开机自启.ps1」，可随时用「卸载开机自启.ps1」撤销。"));
  out.push(bullet("正式启用前，请先完成旋转方向目检（见第 4 章）；确认无误即完成全部验收。"));

  // ---- 9 虚拟打印机与布局设计器 ----
  out.push(h1("9. 虚拟打印机与布局设计器"));
  out.push(h2("9.1 虚拟打印机（自建）"));
  out.push(p("工具创建专属虚拟打印机「水洗唛打印助手」，它是整套自动打印的入口：洗衣管家打印水洗唛时选择它，任务即被写入捕获文件，由工具自动转换并输出到标签机。安装、修复、卸载均为一键脚本，日常无需维护；控制面板内可随时查看状态（详见 4.3 节）。"));
  out.push(h2("9.2 布局设计器"));
  out.push(p("双击「打开布局设计器.cmd」即可自由设计水洗唛版面："));
  out.push(bullet("元素：文本（支持 {字段} 占位，如 {客户}、{单号}）、条码（默认绑定条码号）、线条；可任意增删、拖动、微调。"));
  out.push(bullet("排版：拖动移动、方向键微调（Shift 为精细模式）、0.5 毫米吸附；属性面板可设置字号（毫米）、加粗、对齐方式。"));
  out.push(bullet("数据：「识别最近打印」自动读取最近一次打印数据；也可手工编辑或使用示例数据预览。"));
  out.push(bullet("预览：左为横版设计、右为竖版打印效果（与标签机实际输出一致）。"));
  out.push(bullet("模板：可保存多套模板（保存在 templates\\ 目录），随时切换、另存、删除。"));
  out.push(bullet("打印：「打印测试」直接按当前布局打印一张水洗唛。"));
  out.push(bullet("用于自动打印：勾选后，之后每张标签都会按该布局重排后打印（识别失败时自动回退为原样旋转，确保不出错）。"));
  out.push(p("建议：先不改自动打印，等布局在「打印测试」中确认满意后，再勾选「用于自动打印」。任何时间取消勾选即可恢复原样旋转。"));

  return out;
}

// ==================== 文档组装 ====================
function buildDocument() {
  const coverConfig = {
    title: "水洗唛打印助手",
    subtitle: "使用说明与交付报告",
    englishLabel: "WASH LABEL PRINT ASSISTANT",
    metaLines: [
      "交付对象：星期衣精致洗衣（门店工作机）",
      "交付日期：2026 年 9 月 22 日",
      "版本：v2.0",
    ],
    footerLeft: "水洗唛打印助手 · 使用说明与交付报告",
    footerRight: "v2.0 · 2026-09-22",
    palette: COVER_PALETTE,
  };

  const tocChildren = [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 480, after: 360 },
      children: [new TextRun({ text: "目    录", bold: true, size: 32, font: F_HEAD, color: C.body })],
    }),
    new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-3" }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 200 },
      children: [new TextRun({ text: "说明：本目录由域代码生成；编辑文档后如页码变化，请右键目录并选择「更新域」刷新页码。", italics: true, size: 18, color: "888888" })],
    }),
  ];

  const pageNumFooter = () => new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080" })],
    })],
  });

  const pgSize = { width: 11906, height: 16838 };
  const pgMargin = { top: 1440, bottom: 1440, left: 1701, right: 1417 };

  return new Document({
    creator: "水洗唛打印助手",
    title: "水洗唛打印助手 · 使用说明与交付报告",
    description: "洗衣管家水洗唛自动旋转打印工具——使用说明与交付报告（v2.0）",
    styles: {
      default: {
        document: {
          run: { font: F_BODY, size: 24, color: C.body },
          paragraph: { spacing: { line: 312 } },
        },
        heading1: { run: { font: F_HEAD, size: 32, bold: true, color: C.body }, paragraph: { spacing: { before: 360, after: 160, line: 312 } } },
        heading2: { run: { font: F_HEAD, size: 30, bold: true, color: C.body }, paragraph: { spacing: { before: 280, after: 120, line: 312 } } },
      },
    },
    sections: [
      {
        properties: { page: { size: pgSize, margin: { top: 0, bottom: 0, left: 0, right: 0 } } },
        children: buildCoverR1(coverConfig),
      },
      {
        properties: {
          type: SectionType.NEXT_PAGE,
          page: { size: pgSize, margin: pgMargin, pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN } },
        },
        footers: { default: pageNumFooter() },
        children: tocChildren,
      },
      {
        properties: {
          type: SectionType.NEXT_PAGE,
          page: { size: pgSize, margin: pgMargin, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } },
        },
        footers: { default: pageNumFooter() },
        children: bodyChildren(),
      },
    ],
  });
}

const OUT = "E:/软件开发/水洗唛打印助手/使用说明与交付报告.docx";
const doc = buildDocument();
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("生成完成: " + OUT + " (" + buf.length + " bytes)");
}).catch((e) => {
  console.error("生成失败:", e);
  process.exit(1);
});
