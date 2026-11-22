# 锚点更正复核

夜班对已收到的冻结波形另行签存复核结果。一次复核的指令作用于该件的同一冻结原轨，随后按原位交付选中的读数。源库的修订、实收原件和已签实测报告保留原样。原帧和数据库初始化沿用 README.md。

## 办理入口

- `issue.register.dispatch_review(connection, track, revision_id, numbers)` 按原接口的非空、升序、唯一的选帧规则发行 V2 固定件，返回 `(raw, IssueReceipt)`。沿用 `issue.register.copy(connection, package_id)`，重开源库后按件号补发原字节及原发行回执。
- `receive.intake.accept_review(connection, raw)` 仅凭 V2 字节验封并登记，返回原式 `IntakeRecord`。`original` 保留实收原字节，`readings` 为该件空指令的选位读数。关闭源库后即可验收及办理复核。
- `report.publish.publish_review(connection, intake_id, edits)` 接受已登记的 V2 实收号。`edits` 是 Python 字典，键为所选原锚点的整数原位，值为 `(读数, 差分)` 整数元组或 `None`。`None` 令该锚点按原位缺测处理。布尔值不可作为整数。每次从该件冻结原轨起算，所有指令同时作用，字典顺序无关，空字典合法。
- `report.lookup.fetch_review(connection, finding_id)` 重开复核库后按定稿号领取存档结果和原回执。签存与领取都返回 `(finding, FindingReceipt)`。`finding` 提供 `.finding_id`、`.intake_id`、`.edits`、`.readings` 和 `.metrics`。`.edits` 按原指令字典格式读回，`.readings` 沿用 `IntakeReadings`，`.metrics` 沿用 `Metrics`。有效数和有符号峰值逐选位计算，零是实值，全缺测时峰值为空。全部读数和指令保留整数精度。

## 固定件与拒签

V2 沿用 `version`、`payload`、`sha256` 外层，`version` 为整数 `2`。载荷中的 `package_id`、`track`、`revision_id`、`selection` 和 `frames` 沿用 V1 的格式和原位含义。复核依据随载荷一同封存，摘要按 README.md 的载荷规范计算。依据的具体格式由实现定义，交付时说明如何生成和核验。与 V1 相同，发行方可信，摘要用于检查传输完整性。实收核对摘要、清册、原位及复核依据在件内可核对的结构和绑定，并确认空指令下可解码。省略帧的原编码、逐帧读数及逐帧出处留在源站，固定件只可携带供复核使用的派生依据。

所选原帧保留原字节、原位和设备出处。未选帧保持冻结时的含义，仍参加整轨顺序解码。缺测占原位且保持预测状态。任何差分若先于首个剩余有效锚点，整次拒签，即使该差分位于选区外或随后有锚点重置。全轨始终缺测是合法情形。成功签存按选位原序记录读数与原出处，并绑定本次实际实收号、指令及同次提交的回执。领取使用已存定稿。

坏件、无效选帧、对非所选原锚点下指令、用 V1 实收发起 V2 复核或整轨不可解时报 `ValueError`。未知修订、件号、实收号和定稿号报 `LookupError`。SQLite 写入失败原样传播。发行或实收失败不新增本次对应成果，拒签或签存失败不新增本次定稿或成功回执，已存在的实收和历史结果仍可领取。保留已有源库、复核库、V1 入口、旧件、实测定稿和全部原回归。

## 交班样例

`anchor_examples.py` 中的 A、D、M 沿用原设备帧规则。下表的「拒签」为 `ValueError`。每行均可先用空指令取得原选位读数。

| 原轨 | 选位 | 原读数 | 指令 | 应得结果 |
| --- | --- | --- | --- | --- |
| A(10,2) D(0) D(0) | 1、3 | 10、14 | `{1: (20, 3)}` | 20、26 |
| A(10,2) A(12,2) D(0) | 1、3 | 10、14 | `{1: (20, 3)}` | 20、14 |
| A(10,2) D(0) A(12,2) D(0) | 1、4 | 10、14 | `{1: None}` | 拒签 |
| A(10,2) M A(12,2) D(0) | 1、4 | 10、14 | `{1: None}` | 缺测、14 |
| A(10,2) D(0) | 1 | 10 | `{1: None}` | 拒签 |
| A(10,2) M | 1 | 10 | `{1: None}` | 缺测 |
| A(8,2) D(1) A(−4,1) M D(−2) | 1、3、5 | 8、−4、−5 | `{1: (0, -1), 3: None}` | 0、缺测、−2 |
| 同上一轨 | 1、3、5 | 8、−4、−5 | `{1: None, 3: None}` | 拒签 |

`python3 -B -m anchor_examples` 核对夹具在现有 V1 中的原选位读数和出处。新增入口完成后，`python3 -B -m anchor_examples --review` 办理 V2 发行、补发、断源实收、拒签和重开领取，逐件核对结果与回执。

沿用现有 `.pointwise-runtime.json` 的 `version`、`kind` 和 `setup` 约定。令 `verify` 的参数数组运行全部旧回归及新增复核核验，任一步核验失败即以非零退出。令 `demo` 的参数数组实际展示断源后的两种更正结果、隐藏差分拒签和重开领取。原 `check_project.py` 与 `handoff_demo` 仍可照常运行。
