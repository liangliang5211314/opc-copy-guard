# AI 批量交付核对：数量对了，也可能漏交

一个人让 AI 批量整理资料、生成商品文案或准备客户文件时，用“开工前的应交清单”核对最终输出文件夹。本工具只读清单和文件元数据，不修改、删除或上传交付文件，不调用模型，不需要 API 密钥。

本包为 2026-11-09 重建版：先前临时副本已不可用，本次根据既有实现重建并重新测试，不宣称与旧包逐字节相同。

## 先跑一个例子

准备 Python 3.10 或以上，无第三方依赖。下载整个包并解压，在包含本说明和脚本的目录打开终端。本次实际验证为 Linux / Python 3.12.14；Windows、macOS 与其他 Python 版本尚未实际运行。

macOS/Linux 常用 `python3`，Windows 已安装 Python 时常用 `py -3`，以本机入口为准。复制：

```sh
python3 -B delivery_check.py --plan plan.csv --output examples/good
```

Windows 对应入口（未实测）：

```powershell
py -3 -B delivery_check.py --plan plan.csv --output examples/good
```

预期：

```text
PASS expected=3 ok=3 missing=0 empty=0 extra=0 blocked=0
```

再运行故障示例：

```sh
python3 -B delivery_check.py --plan plan.csv --output examples/bad
```

预期：

```text
FAIL expected=3 ok=1 missing=1 empty=1 extra=1 blocked=0
MISSING {"id": "P02", "file": "02-summary.txt"}
EMPTY {"id": "P03", "file": "03-summary.txt"}
EXTRA "old-summary.txt"
```

两目录各有 3 个普通文件。故障目录缺第二份，第三份零字节，还混入旧稿。只数数量发现不了。所有示例和故障均人为构造，不是真实客户资料或 AI 效果评测。上传/下载时必须保留零字节样例。

## 换成自己的任务

1. **开工前**按任务列清单，每个应交输出写一行。不要从最终文件夹倒推清单，否则缺失任务会被一起漏掉。
2. 本次结果单独放一个平铺文件夹。等待生成、移动和同步结束；不要边写边查。
3. 修改命令中的清单和输出目录。清单、脚本、日志放在输出目录外。带空格路径加双引号。
4. 看到 FAIL，按编号检查缺失或零字节文件；额外文件先核实来源，再人工处理。不要为通过检查删除计划行，也别盲目覆盖已验收结果。
5. 看到 PASS，继续打开文件验收内容、事实、格式、权限及可用性。PASS 不是质量合格证。

清单是 UTF-8 CSV，可带 BOM，表头恰好为 `id,file`。表格软件导出时选“CSV UTF-8（逗号分隔）”：

```csv
id,file
P01,01-summary.txt
P02,02-summary.txt
P03,03-summary.txt
```

编号用英文字母、数字、下划线或连字符，不重复。文件名可用中文，但不可写路径，UTF-8 编码不超过 180 字节。名称大小写须与实际文件精确一致。一项任务需交两份文件，就列两个不同编号。

## 报告与退出码

- expected：清单要求的输出数。
- ok：准确同名、普通文件、大于零字节的条目数，不表示内容正确。
- missing：找不到对应普通文件。
- empty：对应普通文件恰为零字节。
- extra：未列入清单的普通文件，包含隐藏文件。
- blocked：子目录、符号链接或其他非普通条目，不递归扫描、不跟随这些条目。若占用应交名称，还会列为 missing；分类数不保证相加等于文件总数。

missing、empty、extra、blocked 任一非零即 FAIL。大小写不同会同时产生 missing 和 extra，先查名称，不要先重做内容。

退出码：0 为本工具规则通过，1 为完成检查但有问题，2 为清单/目录/参数错误、未完成有效检查。ERROR 写入标准错误流，不要把 ERROR 当作 PASS。

自动流程可读 JSON，脚本不自行保存报告：

```sh
python3 -B delivery_check.py --plan plan.csv --output examples/good --json
```

## 失败先看什么

**先看报告中的编号、文件名，再确认 --plan 和 --output 指向同一次任务。**

- 找不到脚本：确认终端进入解压后的目录。
- CSV header：表头须精确为 `id,file`，不是分号分隔、无第三列或多余空格。
- duplicate：查重复编号、重名、大小写或 Unicode 规范形式碰撞。
- cannot read plan：查路径、读取权限、UTF-8 编码。
- cannot inspect output directory：查目录是否存在、可读，是否正在移动或同步。
- blocked：本工具不支持子目录、符号链接。改用专用平铺交付目录，或另找适合递归交付的工具。
- 中文在报告中显示 `\u`：这是 JSON 转义，不是文件名损坏；JSON 读取器可还原。

## 使用边界

- 原创合成文件检查，不是模型评测，没有准确率、节省时间、收益或部署结论。
- 不读交付正文，无法识别空格、占位内容、截断、重复、事实错误、损坏文件、旧版本或隐私泄露。正确文件名下放非零旧稿仍可 PASS。
- 不检查交付文件可读性；存在却打不开须后续人工验收。
- 不知道清单本身是否漏项，必须从任务输入预先确定并核对清单。
- 仅检查一层；硬链接按普通文件处理。祖先目录符号链接可能被系统解析，不提供恶意目录安全隔离或路径包含保证。
- 检查不是快照或防篡改机制，不保证之后文件未变；检查时停止并发写入。版本锁定另用校验和或版本管理。
- 文件名采取保守限制，拒绝路径、控制字符、常见 Windows 保留名和过长名称，不宣称覆盖全部文件系统命名规则。
- 无网络、无第三方依赖、无模型调用，不运行交付文件。

## 复核

```sh
python3 -B -m unittest -v
```

测试程序只创建、清理自己的临时合成目录；核对脚本本身不改交付文件。结果见 TEST_REPORT.md，真实文本输出见 run.log。文本日志不是终端截图。

## 公开技术依据

以下支持标准库实现，不是官方同款工具或效果背书：

- [Python 3.12 CSV](https://docs.python.org/3.12/library/csv.html)
- [Python 3.12 pathlib 与 lstat](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.lstat)
- [Python 3.12 普通文件类型检查](https://docs.python.org/3.12/library/stat.html#stat.S_ISREG)
- [Python 3.12 unittest 命令行](https://docs.python.org/3.12/library/unittest.html#command-line-interface)
