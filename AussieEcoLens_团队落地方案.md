# AussieEcoLens 团队落地方案（修订版 / 可分享）

> 目标评分：**D（70–79）为底线，争取更高**。
> 截止：**6 月 8 日 23:55（Moodle）**；团队内部目标：**6/3 初稿对齐、6/6 功能完成**。
> 云环境：**AWS = Academy Learner Lab**（IAM 受限、有预算/会话限制、无服务器资源持久）；**GCP = 学生账号 $300 计费**（Cloud Run / GCS 可用）。

---

## 0. 团队三大期望与对应保障

1. **每人可独立开发并通过 GitLab 合并** → 第 1 天冻结 API contract / DB schema / S3+GCS 路径 / mock response；全员用 mock 数据并行，不互相等待真实资源。
2. **拿到 D 评分** → 见第 9 节"保 D 优先级"；只要有完整 UI（不被 capped）且核心功能跑通，70+ 可达。
3. **6/3 初稿对齐、6/6 完成** → 见第 8 节时间线（已预留报告写作与 Demo 彩排）。

---

## 1. 总体架构

- 前端：`React + Vite`
- 后端（AWS Academy）：Cognito、S3、API Gateway（+ Cognito Authorizer）、Lambda（Python）、DynamoDB、SNS
- 模型服务（GCP）：Cloud Run（Python 容器，PyTorch + OpenCV + MegaDetector + SpeciesNet）
- 模型文件：GCS；上传文件：S3

```
用户(浏览器)
  │  Cognito 登录拿 ID token
  ├──(Authorization: Bearer JWT)──► AWS API Gateway ──► Lambda ──► DynamoDB / S3 / SNS
  └──(multipart + JWT)────────────► GCP Cloud Run /query/by-file (验 JWT)

S3 上传完成 ──(S3 event)──► 处理 Lambda ──(内部 secret)──► GCP Cloud Run 推理端点
                                   │
                                   └──► 写 DynamoDB + 发 SNS 通知
```

**跨云鉴权两条路径（重点，第 1 天必须冻结）：**
- 用户态：用户带 Cognito ID token 直接调用 AWS API Gateway 或 GCP `/query/by-file`，GCP 自行校验 Cognito JWT（拉取 Cognito JWKS 验签）。
- **内部态（关键修正）**：S3 事件触发的处理 Lambda **没有用户 token**，调用 Cloud Run 推理端点时使用 **shared secret / API key**（存 Lambda 环境变量，Cloud Run 校验 header）。用户态与内部态是 Cloud Run 上**两个独立入口**。

---

## 2. 分工（按技术模块，4 人并行）

- **成员 A — Auth + UI Shell + Upload Init**
  Cognito 注册/登录/登出、邮箱验证、受保护路由、未登录跳转；React 页面框架；上传初始化 API、checksum 去重、presigned S3 upload。
- **成员 B — Storage Processing**
  S3 event 触发处理；图片等比缩略图；视频 1fps 抽帧；调用 GCP 推理（内部 secret）；写 DynamoDB；发布 tag 通知。
- **成员 C — GCP ML + Query By File**
  Cloud Run 模型服务（双入口：内部 secret / 用户 JWT）；MegaDetector + SpeciesNet 推理；GCS 模型加载；`/query/by-file`。
- **成员 D — Query + Data Management + Notification + 集成**
  tag/species/thumbnail 查询；bulk tag edit；delete；SNS 订阅 API；查询/管理/通知 UI；DB 索引维护；**集成负责人**（统一处理 `develop` 合并冲突）。

**并行原则**：第 1 天冻结 API contract、DynamoDB schema、S3/GCS 路径、mock response；全员用 mock 开发。

---

## 3. 模型部署（GCP Cloud Run）

- 用 Cloud Run 部署唯一 ML 推理服务：避免 Lambda layer/包体积问题，更适配 PyTorch / MegaDetector / OpenCV。
- 模型文件（满足"换模型不改代码" 4.1）：
  - `gs://aussie-ecolens-g62-models/current/mdv5a.pt`
  - `gs://aussie-ecolens-g62-models/current/model.pt`
  - `gs://aussie-ecolens-g62-models/current/labels.txt`
- 启动时从 GCS 下载到容器本地缓存；更新模型只替换 `current/` 文件，不改业务代码。
- **设 `min-instances=1` 保活**，避免冷启动重新下模型导致 Demo 超时（$300 额度足够覆盖项目期）。
- Cloud Run 返回 `tagCounts` 与 confidence metadata。

---

## 4. 存储与数据库

### S3 文件结构
- `originals/images/{fileId}.{ext}`
- `originals/videos/{fileId}.{ext}`
- `thumbnails/images/{fileId}.jpg`
- `frames/{fileId}/frame_{second}.jpg`
- `thumbnails/frames/{fileId}/frame_{second}.jpg`

### DynamoDB 表一：`Files`
- PK：`fileId`
- 字段：`ownerSub`, `ownerEmail`, `originalFilename`, `fileType`, `contentType`, `sizeBytes`, `checksumSha256`, `status`
- 字段：`bucket`, `objectKey`, `fileUrl`, `thumbnailKey`, `thumbnailUrl`, `frameKeys`, `frameThumbnailKeys`
- 字段：`tagCounts`, `autoTagCounts`, `manualTagCounts`, `modelVersion`, `createdAt`, `updatedAt`, `deletedAt`, `errorMessage`
- GSI：**`ownerSub-checksum-index`（owner+checksum 复合去重，修正）**、`fileUrl-index`、`thumbnailUrl-index`、`ownerSub-index`

### DynamoDB 表二：`MediaTags`
- PK：`tagName`，SK：`fileId`
- 字段：`count`, `fileType`, `fileUrl`, `thumbnailUrl`, `updatedAt`
- 用于高效实现多标签 AND + minimum count 查询。

### DynamoDB 表三：`TagSubscriptions`
- PK：`subscriptionId`
- 字段：`ownerSub`, `email`, `tags`, `snsSubscriptionArns`, `status`, `createdAt`
- GSI：`ownerSub-index`, `tagName-index`

---

## 5. Public API V1

约定：AWS API 走 API Gateway + Cognito Authorizer；GCP API 自行验证 Cognito JWT。Header 固定 `Authorization: Bearer {Cognito ID token}`。

### AWS API
- `POST /v1/uploads/init` — Body: `filename, contentType, fileType, sizeBytes, checksumSha256`；返回重复文件结果或 `fileId, uploadUrl, objectKey, expiresIn`。
- `POST /v1/uploads/complete` — Body: `fileId, objectKey, checksumSha256`；返回 `fileId, status`。
- `GET /v1/files/{fileId}` — 返回文件状态、URLs、tags、processing error。
- `POST /v1/query/tags` — Body: `{ "tags": { "kangaroo": 2, "wombat": 1 } }`；多 tag = AND，count = minimum。
- `POST /v1/query/species` — Body: `{ "species": ["dingo", "koala"] }`；每个 species 至少 1 次。
- `POST /v1/query/thumbnail` — Body: `{ "thumbnailUrl": "..." }`；返回对应 full-size image URL。
- `POST /v1/tags/bulk` — Body: `urls, tags, operation`（`1=add, 0=remove`）；删除不存在 tag 静默忽略。
- `POST /v1/files/delete` — Body: `{ "urls": ["..."] }`；删除原文件、缩略图、frame、DynamoDB 记录与 `MediaTags` 索引。
- `POST /v1/notifications/subscriptions`、`GET /v1/notifications/subscriptions`、`DELETE /v1/notifications/subscriptions/{subscriptionId}` — 用 SNS email subscription 实现 tag 订阅。

### GCP API
- `POST /v1/query/by-file`（用户态，验 JWT）— multipart 临时文件；运行模型得 species set，再转调 AWS `/v1/query/tags`；**查询文件不写入 S3/DynamoDB**。
- `POST /internal/infer`（内部态，验 shared secret，修正补充）— 供 S3 处理 Lambda 调用；输入 image/frame URL，返回 `tagCounts` + confidence。

### 通知设计（修正）
- 用**单一 SNS topic** + 消息携带 `tag` message attribute + 每个订阅设置 **filter policy**（按订阅的 tag 过滤），避免每个 tag 建一个 topic。

---

## 6. UI 范围（满足 Rubric 高分标准）

- **Auth**：注册、登录、登出、未登录自动跳转；注册字段含 email、first name、last name、password；邮箱验证提示。
- **Upload**：图片/视频上传、checksum 计算、重复文件提示、上传进度、processing 状态、成功/失败反馈。
- **Query**：tag + count 查询表单、species 快速查询、thumbnail URL 查询、uploaded-file 查询。
- **Results**：图片显示 thumbnail 预览，点击获取 full-size image；视频显示 full video URL + tag 信息。
- **Management**：结果多选、bulk add/remove tags、bulk delete。
- **Notifications**：按 species tag 订阅/取消订阅邮件通知。
- **General**：统一导航、错误提示、loading 状态、空结果状态。

> 注意：有完整 UI 才不会被 capped 在 D；UI 三项共 20 分，是保 D 的关键之一。

---

## 7. GitLab 工作流

### 分支
- `main`：最终稳定版，仅 6/6 后从 `develop` 合并。
- `develop`：集成分支。
- `feature/auth-upload`、`feature/storage-processing`、`feature/gcp-ml-query-file`、`feature/query-management-notification`、`docs/team-report`

### Merge Request 规则
- 所有 feature 分支合并到 `develop`；每个 MR 至少 1 人 review。
- 涉及接口或 DB schema 的 MR 必须通知全组。
- 不直接 push 到 `main` / `develop`。
- **出现冲突由集成负责人（D）统一处理**，保留双方改动后再合并。
- **全员都必须有自己的 commits**（评分要求 + Peer Assessment 证据，不能由一人代提）。

---

## 8. 时间线（已加入报告写作与 Demo 彩排）

- **5/30**：冻结方案 + API V1 + DB schema + 分支；**额外冻结内部推理 secret 鉴权 contract**。
- **5/31**：完成 Cognito/S3/DynamoDB/GCS/Cloud Run 基础配置；**实测 Cognito 验证邮件 + SNS 订阅确认邮件可达**；前端 mock 页面开始。
- **6/1**：A 完成 auth/upload init；B 完成 S3 trigger + thumbnail；C 完成 Cloud Run 推理 skeleton（双入口）；D 完成 query/data API skeleton。
- **6/2**：核心第一版打通（上传→处理→入库→tag 查询→UI 联通）。
- **6/3（初稿对齐日）**：各成员模块可独立演示，接口字段冻结无重大变更。
- **6/4**：完成 query-by-file、bulk tag edit、delete、notifications、管理 UI。
- **6/5**：全链路测试 + 修 bug + 补截图 + **Demo 彩排第一轮 + 录屏兜底**。
- **6/6**：`develop` 合并到 `main`；功能冻结；开始写团队报告。
- **6/7**：完成团队报告（1000 字）+ 每人 Individual Report（500 字）+ Demo 彩排第二轮。
- **6/8**：23:55 前在 Moodle 提交（团队报告 1 份 + 每人各自 Individual Report）。

---

## 9. 保 D 优先级（时间不足时的取舍）

- **必达（决定能否上 70）**：Auth 全流程 / 上传+checksum 去重 / 缩略图+视频 1fps / ML 打标+入库 / tag 查询(AND+min count) / 基本 UI / 可跑通的 Demo。
- **高 ROI 加分**：query-by-file(8 分)、thumbnail-URL 查询(6)、bulk tag(3)、delete(3)、notifications(4)。
- **stretch（受限可少投入）**：精细 IAM（Academy 只能用 LabRole，预期拿 50%）、UI 美化到 "professional"。

---

## 10. 报告与 Demo（占 20 分，勿丢）

### 团队报告（≤1000 字，1 人提交）
- 多云架构图（**必须用各云官方架构图标**）。
- 三列贡献表：姓名+学号 / 贡献百分比 / 贡献的项目模块（每人 ≤100 字）。
- 简单用户测试指南。
- 源码仓库链接（GitLab，私有仓库，分享给全体教学团队）。
- 表格、架构图、UI 截图、参考文献不计入字数。

### Individual Report（每人 500 字，各自提交，独立完成）
- 个人角色与对多云系统的贡献（150 字）。
- 团队协作反思：评价队友、团队挑战、协作情况（150 字）。
- 务必独立完成，避免串通/抄袭。

### Demo（15 分，强制项："No demo = No marks"）
- 全员到场（Zoom）；先讲架构（3–5 分钟），再演示核心功能 + Q&A（≤15 分钟）。
- 准备**演示脚本**与**录屏兜底**，防止现场环境/会话失效。

### Peer Assessment
- 每人提交保密表；全员保留各自 commits 与 UI 截图证据。

### AWS Academy 说明（写进报告）
- 主动说明 Academy 的 IAM 限制（只能用 LabRole），并展示在可控范围内已尽量收窄权限（bucket policy / 资源级 policy）。

---

## 11. 验收清单（Acceptance Tests）

- 未登录用户不能访问除注册/登录外的页面和 API。
- 同一文件重复上传由 `checksumSha256`（owner+checksum）拦截，不靠文件名。
- 图片生成等比压缩 thumbnail；视频按 1 frame/sec 抽帧。
- 上传后自动触发 ML，DynamoDB 写入 file type、URLs、tag counts、model version。
- tag 查询支持 AND + minimum count；species 查询返回至少含 1 个该物种的文件。
- thumbnail URL 查询返回正确 full-size image URL。
- query-by-file 不永久保存查询文件，返回匹配的 DB 文件。
- **内部 Lambda→Cloud Run 推理调用必须带 secret 校验，未授权调用被拒。**
- bulk tag add/remove 支持多个 URL；删除不存在 tag 不报错。
- delete API 同时删除 S3 原文件、缩略图、frames、DynamoDB 记录与 tag index。
- 用户订阅 tag 后，仅当对应 tag 新增文件时收到 SNS email 通知。
- **Cognito 验证邮件与 SNS 订阅确认邮件在 Academy 中实测可达。**
- **每人均有独立 commits；每人提交 Individual Report；完成至少一次完整 Demo 彩排 + 录屏兜底。**
