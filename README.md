# 岚桥波形交班档案

岚桥结构疲劳试验室用这套本地档案衔接白班采集和夜班复测。白班导入有序设备原帧，核对整轨读数，必要时提交勘误，再指名修订发行本次复测所需的原序位。夜班停源后仅凭固定件复读，按有效测点数和峰值安排复测，并用逐帧出处定位原设备导出。次日负责人按定稿号领取原报告和回执。

## 运行

在项目根目录使用 Python 3.11 和标准库。控制台物化项目时提供完整回归入口。

```text
python3 -B check_project.py
python3 -B -m handoff_demo
```

回归使用临时 SQLite 库，覆盖有符号读数、前置缺测、父版检查、重开初始化、固定件补发、独立来件、旧件、错界拒收、失败回滚及历史领取。演示实际导入样例并提交勘误，关闭源库后读取第 1、3、5 帧，签存报告后重开领取。样例整轨读数为 10、13、16、8、8，勘误后为 11、14、17、8、8。旧修订的复读结果为 10、16、8，有效帧数为 3，峰值为 16。

## Python 接口

源库用 `capture.store.open_source(path)` 打开，再执行 `initialize_capture(connection)` 和 `issue.register.initialize_issue(connection)`。复核库用 `receive.register.open_offline(path)` 打开，再执行同模块的 `initialize_intake(connection)` 和 `report.store.initialize_reports(connection)`。两个库分别持久化。初始化可重复执行，保留已登记的内容，样例由演示显式导入。公开写入口拥有提交边界，调用时连接应处于事务外。使用完毕后关闭连接。

| 入口 | 输入及成功结果 |
| --- | --- |
| `capture.importer.record(connection, track, frames, parent=None)` | `frames` 为有序 `SourceFrame(number, raw, origin)`，其中 `parent` 为关键字参数。新轨道省略父版，勘误提交完整新轨并指定同轨现行父版。返回新修订号。 |
| `wave.track.inspect(connection, track, revision_id)` | 返回指定修订的整轨 `FrameReading` 元组，保留原序与出处。 |
| `issue.register.dispatch(connection, track, revision_id, numbers)` | 选帧非空，原序升序且互异。返回 `(固定件字节, IssueReceipt)`，件号位于 `receipt.package_id`。 |
| `issue.register.copy(connection, package_id)` | 返回登记时的固定件字节和原发行回执。 |
| `receive.intake.accept(connection, raw)` | 仅使用固定件字节。返回含实收号、原件和重解明细的 `IntakeRecord`。 |
| `report.publish.publish(connection, intake_id)` | 返回同次签存的 `(Finding, FindingReceipt)`。报告含修订、所选原序、读数、出处及统计，定稿号位于 `finding.finding_id`。 |
| `report.lookup.fetch(connection, finding_id)` | 按原定稿号领取存档的报告和原回执。 |

`capture.revisions.load_current` 与 `load_revision` 分别读取现行修订和指定历史修订。`receive.register.load_intake` 按实收号重读原件与已核验读数。修订和报告编号由库在登记时生成，固定输入的业务读数、原序、出处及统计可重复核对。补发及重开领取沿用登记时产生的编号。

## 原帧、复读和错误

`SourceFrame.raw` 是 UTF-8 JSON 数组的原字节。`["A", 10, 2]` 是设定读数 10 和差分 2 的锚点。`["D", 1]` 先增加差分 1，再将新差分加到读数。`["M"]` 表示缺测，保持预测状态并占一个原序位。原序从 1 开始，首个可计量帧须为锚点，前置和全轨缺测均可保留。`Origin(export, locator)` 分别指设备导出标识及该导出物内的定位，均为非空 UTF-8 文本。单位为设备原生整数采样码。峰值取有效读数中的有符号最大值，零计为有效，全缺测时峰值为空。

固定件外层含 `version`、`payload`、`sha256`。版本 1 的载荷含 `package_id`、`track`、`revision_id`、`selection` 和 `frames`，新发行另含 `basis`。摘要为载荷经过 JSON 键排序、ASCII 转义、冒号和逗号紧凑分隔后的 SHA-256 十六进制值，用于校验内容完整性。清册行按所选原序包含 `number`、Base64 原字节 `raw` 及 `origin`。`basis` 按原序列出需要入口状态的连续选段，记录含 `start`、`value`、`difference`。`start` 为选段第一帧原序，即使该帧缺测。后两项为带符号的规范十进制整数字符串。选段首个可计量帧为锚点或整段全缺测时，自足重解。无 `basis` 的历史件在所有选段均可自足重解时仍可实收。实收核验每条依据对应的实际原序边界，再使用所选原编码产生读数。省略帧的原编码及出处保留在源站。

无效轨道结构、过时或跨轨父版、无效选帧、外层失配、缺证和错界来件报 `ValueError`。未知修订、件号、实收号或定稿号报 `LookupError`。数据库写入失败传播 SQLite 异常。发行和报告只在提交后返回成功回执。报告和回执同次提交，失败后可按原号继续领取旧成果。

`fixtures/bench-export.json` 是五帧设备导出，`fixtures/night-handoff.json` 可直接离线实收，`fixtures/legacy-handoff.json` 是可独立重解的旧件。系统处理单轨整数采样，产品范围限于本地采集档案与同版离线复核。
