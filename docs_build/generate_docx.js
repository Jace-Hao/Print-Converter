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
  out.push(p("「水洗唛打印助手」v1.0 已完成开发并通过全链路实测：门店保持原有打印习惯（打印时选择「水洗唛转换」），工具在后台自动完成 捕获 → 旋转排版 → 送印 → 归档 全流程，无需任何额外操作。"));
  out.push(cap("表 1　交付成果清单"));
  out.push(makeTable(["成果", "内容", "位置"], [
    ["自动打印工具", "监视捕获、旋转、送印、归档、日志", "E:\\软件开发\\水洗唛打印助手"],
    ["控制面板", "一键启停、测试打印、查看日志与目录", "打开控制面板.cmd"],
    ["操作脚本", "启动/停止监视、校准打印、开机自启安装等", "工具目录（根目录）"],
    ["标签内容编辑器", "识别打印数据、编辑字段、预览并打印自定义标签", "打开标签编辑器.cmd"],
    ["使用说明（本文）", "原理、操作、校准、常见问题", "使用说明与交付报告.docx / 使用说明.html"],
  ], [18, 47, 35]));
  out.push(p("截至 2026 年 9 月 22 日，核心功能全部实测通过（详见第 5 章）；旋转方向默认采用「顺时针」，并已提供两版校准唛供现场比对，确认后即为最终配置。"));

  // ---- 2 背景与方案设计 ----
  out.push(h1("2. 背景与方案设计"));
  out.push(h2("2.1 原有流程的问题"));
  out.push(p("原流程需要人工执行四个步骤：打印预览、另存为 PDF、旋转 90 度、再发送到标签机。存在三个问题：一是操作繁琐，每张标签都要重复；二是旋转依靠人工判断，容易方向出错；三是中间 PDF 分散各处，日后补打、对账不便。"));
  out.push(h2("2.2 自动化方案"));
  out.push(p("工具采用「旁路捕获」思路：不修改洗衣管家本体，而是利用 pdfFactory 虚拟打印机的自动保存能力——每次打印到「水洗唛转换」后，PDF 会自动、静默地保存到指定目录；工具监视该目录，发现新文件后自动完成旋转、排版与送印。"));
  out.push(flow("打印水洗唛 → PDF 自动保存 → 监视捕获 → 旋转 90° 并排版 → 打印到标签机 → 自动归档"));
  out.push(h2("2.3 关键设计决策"));
  out.push(bullet("不侵入原则：不改造洗衣管家、不修改其业务数据，只使用打印链路；相关设置已备份，可随时回退。"));
  out.push(bullet("安全闸：只自动处理尺寸符合标签比例（120×30 毫米）的文件；不符合的文件（如 A4 文档）会被移入 out\\hold 目录待人工确认，避免误打。"));
  out.push(bullet("可追溯：每个标签自动归档 PDF 原件与位图预览，补打、对账、复查都方便。"));
  out.push(bullet("默认全自动：捕获成功即自动送印；如需「先预览再打印」，可将自动化模式切换为 dry_run（只预览不打印）。"));

  // ---- 3 快速上手 ----
  out.push(h1("3. 快速上手"));
  out.push(h2("3.1 日常三步"));
  out.push(bullet("双击「启动监视.cmd」启动后台监视（保持窗口开着；关闭窗口即停止监视）。"));
  out.push(bullet("照常打印水洗唛：打印时选择「水洗唛转换」。"));
  out.push(bullet("完成：工具自动旋转并打印到「水洗唛」，同时归档。"));
  out.push(h2("3.2 控制面板"));
  out.push(p("如果不习惯命令行窗口，可双击「打开控制面板.cmd」使用图形面板："));
  out.push(cap("表 2　控制面板按钮说明"));
  out.push(makeTable(["按钮", "功能"], [
    ["启动监视 / 停止监视", "打开或停止后台监视进程"],
    ["打印校准唛（两版）", "打印顺时针、逆时针两版校准标签"],
    ["处理 PDF 文件…", "手动选择一个 PDF 进行旋转打印"],
    ["标签编辑器", "打开标签内容编辑器（识别 → 编辑 → 预览 → 打印）"],
    ["监视目录 / 归档目录 / 预览目录 / 日志目录", "一键打开对应文件夹"],
    ["使用说明", "打开本文档的 HTML 版本"],
  ], [42, 58]));
  out.push(h2("3.3 第一次使用建议"));
  out.push(p("建议先手动打印一张真实水洗唛试跑：确认标签方向、内容完整性后，再进入日常使用。若方向与预期相反，按第 4 章切换旋转方向即可。"));

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
    ["automation.mode", "auto", "auto 自动打印；dry_run 只预览不打印"],
    ["automation.close_pdffactory_window", "true", "处理完成后自动关闭 pdfFactory 弹出窗口"],
  ], [34, 20, 46]));
  out.push(p("配置文件位于工具目录根下（config.json），可用记事本编辑；修改后重启监视生效。"));

  // ---- 5 测试与验收记录 ----
  out.push(h1("5. 测试与验收记录"));
  out.push(h2("5.1 测试环境"));
  out.push(makeTable(["项目", "说明"], [
    ["门店工作机", "Windows 11（xqyjzxy）"],
    ["洗衣管家", "单机版 v6.1.23"],
    ["虚拟打印机", "pdfFactory 8.31（水洗唛转换）"],
    ["标签打印机", "佳博 GP-9134T（水洗唛，300 点每英寸）"],
    ["标签规格", "30×120 毫米竖版（设计版面 120×30 毫米横版）"],
    ["工具版本", "v1.0（Python 3.14）"],
  ], [30, 70]));
  out.push(h2("5.2 测试记录"));
  out.push(makeTable(["序号", "测试项目", "方法", "结果"], [
    ["1", "捕获链路", "打印测试页到「水洗唛转换」，检查 PDF 自动落盘", "通过（无弹窗、静默保存）"],
    ["2", "连打合并", "快速连续发起 2 笔打印任务", "通过（合并为 1 个 2 页 PDF，逐页处理）"],
    ["3", "旋转与排版", "干跑模式生成标签位图并检查尺寸", "通过（30×120 毫米、300 点每英寸，尺寸精确）"],
    ["4", "物理打样", "打印两版校准唛（顺时针 / 逆时针）", "通过（标签机实际出纸）"],
    ["5", "端到端全链路", "打印 → 捕获 → 旋转 → 送印 → 归档 → 关窗", "通过（5 个任务、7 张标签全自动完成）"],
  ], [8, 18, 44, 30]));
  out.push(h2("5.3 待确认事项与验收结论"));
  out.push(p("待确认事项：旋转方向需现场目检两张校准唛后最终确认（默认顺时针）；其余配置均无需调整。测试期间共打印若干测试唛（内容均为测试数据，可直接丢弃）。"));
  out.push(p("验收结论：除上述方向目检外，全部验收项均已通过，工具具备投入日常使用的条件。"));

  // ---- 6 目录与文件说明 ----
  out.push(h1("6. 目录与文件说明"));
  out.push(cap("表 4　目录与关键文件"));
  out.push(makeTable(["名称", "说明"], [
    ["工具主目录", "E:\\软件开发\\水洗唛打印助手"],
    ["app\\", "程序代码（watcher 监视引擎、cli 命令行、ui 控制面板等）"],
    ["out\\archive\\", "归档：每个标签的 PDF 原件（补打用）"],
    ["out\\previews\\", "预览：处理后的标签位图"],
    ["out\\logs\\", "运行日志（排查问题先看这里）"],
    ["inbox\\", "手动投递目录：放入 PDF 会被自动处理"],
    ["config.json", "配置文件（旋转方向、偏移、监视目录等）"],
    ["打开标签编辑器.cmd", "标签内容编辑器入口（识别 → 编辑 → 预览 → 打印）"],
  ], [26, 74]));

  // ---- 7 常见问题 ----
  out.push(h1("7. 常见问题"));
  out.push(makeTable(["问题", "处理"], [
    ["打印后没有自动出标签？", "检查「启动监视」窗口是否仍在运行；查看 out\\logs 当天日志。"],
    ["屏幕上弹出了 pdfFactory 窗口？", "正常现象，工具处理完成后会自动关闭；无需手动操作。"],
    ["想暂停自动处理？", "关闭「启动监视」窗口，或在控制面板点击「停止监视」。"],
    ["标签打印出来方向不对？", "见 4.1 节：切换 rotate_dir 后重新启动监视。"],
    ["有旧标签需要补打？", "在 out\\archive 找到对应 PDF，拖到「把PDF拖到这里处理.cmd」上即可。"],
    ["某些 PDF 没有自动打印？", "尺寸不符合标签比例的文件会被安全闸拦下（移入 out\\hold），防止误打。"],
    ["电脑重启后需要手动启动吗？", "默认需要；运行一次「安装开机自启.ps1」即可随登录自动运行。"],
    ["会不会影响洗衣管家？", "不会。工具不修改洗衣管家程序与数据，仅使用打印链路。"],
  ], [36, 64]));

  // ---- 8 已知限制与注意事项 ----
  out.push(h1("8. 已知限制与注意事项"));
  out.push(bullet("pdfFactory 自动保存目录为固定默认位置（经实测无法自定义到其他目录），工具已按该位置配置监听；请勿随意改动该目录内正在生成的文件。"));
  out.push(bullet("旧打印机「水洗唛自动转换」已失效并从系统移除，与本方案无关；本工具不依赖它。"));
  out.push(bullet("工具默认不随开机启动；需要时运行「安装开机自启.ps1」，可随时用「卸载开机自启.ps1」撤销。"));
  out.push(bullet("正式启用前，请先完成旋转方向目检（见第 4 章）；确认无误即完成全部验收。"));

  // ---- 9 标签内容编辑器（初版） ----
  out.push(h1("9. 标签内容编辑器（初版）"));
  out.push(p("除自动旋转打印外，工具附带一个「标签内容编辑器」，用于临时调整或自制标签内容：打开后可从最近一次打印数据中自动识别字段（单号、客户、衣物名称、颜色、件数、品牌、损坏说明、服务项目、门店名、条码号），逐项修改后即时预览，并可一键打印到标签机。"));
  out.push(p("使用方式：双击「打开标签编辑器.cmd」，或通过控制面板的「标签编辑器」按钮打开；适用于需要临时补充说明、修改个别字段或补打特殊标签的场景。识别结果可直接手工修正；打印前建议先核对预览。"));
  out.push(p("后续计划：编辑器将持续根据实际使用反馈打磨；其余增强想法（如批量编辑、模板保存）视需要进一步推进。本工具已达到「日常可用、自动运行、可追溯、可回退」的交付标准。使用中如遇问题，请先查阅第 7 章与 out\\logs 日志，再行反馈处理。"));

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
      "版本：v1.0",
    ],
    footerLeft: "水洗唛打印助手 · 使用说明与交付报告",
    footerRight: "v1.0 · 2026-09-22",
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
    description: "洗衣管家水洗唛自动旋转打印工具——使用说明与交付报告（v1.0）",
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
