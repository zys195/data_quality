# 知识库（Knowledge Base）系统设计文档

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         前端 UI                                     │
│  文件上传 → 向量化状态追踪 → 在线问答                                │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────────┐
│                Java 后端 (openmetadata-server)                       │
│                                                                     │
│  KnowledgeBaseWorkflowService    KnowledgeBaseQAService              │
│    ├ 文件上传与校验                 ├ 5-Stage QA Pipeline           │
│    ├ meta.json 创建                ├ 属性提取/文件过滤/向量检索     │
│    ├ Pipeline 部署与触发            ├ MCP集成/答案生成               │
│    ├ 向量化状态查询                 └ 多模态Vision支持              │
│    └ 文件删除 (含ChromaDB清理)                                      │
│                                                                     │
│  KnowledgeBaseFileService         VectorSearchService                │
│    ├ 文件存储管理                    ├ 两阶段Parent-Child检索        │
│    ├ listFiles/meta读取             ├ 关键词+向量RRF融合             │
│    └ Tika文本提取                   └ ChromaDB查询构建              │
│                                                                     │
│  KnowledgeBaseLLMClient            AttributeExtractor                │
│    ├ 答案生成(deepseek-v4-pro)       ├ LLM结构化提取                │
│    ├ 属性提取(deepseek-v4-flash)     └ 规则引擎兜底                  │
│    ├ 查询扩展                                                       │
│    └ 多模态 Vision API                                              │
│                                                                     │
│  辅助类:                                                             │
│    ChromaDBHelper    ─ ChromaDB查询构建/结果解析                     │
│    FuzzyMatcher      ─ 关键词模糊匹配打分                            │
│    KeywordExtractor  ─ 规则引擎关键词提取                             │
│    KeywordConfig     ─ 关键词同义词典                                │
│    AttributeExtractionService ─ 三路并行属性提取编排                 │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────────┐
│         Python 层 (ingestion容器 / Airflow)                         │
│                                                                     │
│   KnowledgeBaseFileSource (Airflow DAG)                             │
│     ├ 文本提取: PyPDF2/python-docx/pandas/python-pptx              │
│     ├ Parent-Child分块                                              │
│     └ BGE-M3嵌入 → ChromaDB写入                                     │
│                                                                     │
│   Embed Server (ingestion:8102)                                     │
│     └ BGE-M3 文本嵌入服务                                           │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────────┐
│                基础设施 (Docker)                                     │
│                                                                     │
│   ChromaDB (chromadb:8000)  ─ 向量存储                              │
│   OpenMetadata Server (localhost:8585)  ─ 元数据搜索/MCP             │
│   Airflow (ingestion:8080)  ─ 工作流编排                            │
│   Shared Volume (/data/knowledge_base)  ─ 文件共享                   │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. 存储结构

### 2.1 目录布局

```
/data/knowledge_base/
├── uploads/{projectId}/          ← 文件上传目录（Java/QA读）
│   ├── 汉江智行营业执照副本.png
│   ├── 汉江智行营业执照副本.png.meta.json  ← 文件元数据
│   ├── 登记申请表.docx
│   ├── 登记申请表.docx.meta.json
│   └── dataGroup/               ← 角色分组子目录（Engineer）
│   └── lawGroup/                ← 角色分组子目录（Lawyer）
│   └── financeGroup/            ← 角色分组子目录（Accountant）
│   └── valueGroup/              ← 角色分组子目录（Evaluator）
├── original/{projectId}/        ← 原始文件副本（Ingestion处理用）
├── vectors/{projectId}/         ← 向量化文件（Ingestion写入）
└── settings.json                ← 系统配置
```

### 2.2 完整文件元数据属性清单 (`listFiles` 输出）

`listFiles` 先读取文件系统缺省属性，合并 `meta.json`，输出以下完整属性列表：

#### 缺省属性（文件系统提取）

| 属性名 | 类型 | 来源 | 示例 |
|--------|------|------|------|
| `id` | string | 文件名 | `"汉江智行营业执照副本.png"` |
| `fileId` | string | 文件名 | `"汉江智行营业执照副本.png"` |
| `name` | string | 文件名 | `"汉江智行营业执照副本.png"` |
| `fileName` | string | 文件名 | `"汉江智行营业执照副本.png"` |
| `fileType` | string | 扩展名 | `"png"` |
| `size` | long | 文件系统 | `102400` |
| `fileSize` | long | 文件系统 | `102400` |
| `uploadedAt` | string | 修改时间 | `"1700000000000"` |
| `sourcePath` | string | 存储路径 | `/data/knowledge_base/uploads/...` |
| `projectId` | string | 参数 | `"proj_xxx"` |
| `targetFolder` | string | 相对目录 | `"lawGroup"` |
| `vectorizationStatus` | enum | meta.json推断 | `"NOT_VECTORIZED"`/`"PENDING"`/`"VECTORIZED"` |

#### meta.json 自定义属性（上传时设置）

| 属性名 | 类型 | 来源 | 用于匹配权重 |
|--------|------|------|------------|
| `description` | string | 前端用户录入 | +2 |
| `tags` | string[] | 前端用户选择/录入 | +2 |
| `category` | string | 前端用户选择 | +2 |
| `region` | string | 前端用户选择 | +2 |
| `industry` | string | 前端用户选择 | +2 |
| `applicablePeriod` | string | 前端用户录入 | —（仅过滤用）|
| `targetFolder` | string | 前端指定 | +1 |
| `fileType` | string | 文件系统 | +1 |
| `enableVectorization` | boolean | 前端开关 | —（控制向量化决策）|
| `uploadUsername` | string | 系统自动 | — |
| `dataIndustry` | string | 前端录入 | — |
| `dataNameToRegister` | string | 前端录入 | — |
| `referenceRegulations` | string[] | 前端录入 | — |
| `projectObjective` | string[] | 前端录入 | — |
| `exchangeLocation` | string[] | 前端录入 | — |

#### LLM 属性提取输出（Stage 0）

| 属性名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `search_keywords` | string[] | 核心检索关键词 | `["汉江智行","营业执照","经营信息"]` |
| `file_name` | string | 目标文件名 | `"汉江智行营业执照副本.png"` |
| `file_type` | string | 文件类型 | `"png"` |
| `category` | string | 分类 | `"数据"` |
| `region` | string | 地区 | `"中国"` |
| `industry` | string | 行业 | `"科技"` |
| `description` | string | 描述 | `"营业执照"` |
| `applicable_period` | string | 适用时间 | `"2026"` |
| `tags` | string | 标签 | `"lineage"` |
| `target_dir` | string | 目标目录 | `"lawGroup"` |
| `uploaded_by` | string | 上传人 | `"张三"` |
| `need_mcp` | boolean | 需要MCP调用 | `true` |
| `mcp_service` | string | MCP服务名 | `"get_entity_lineage"` |
| `mcp_params` | object | MCP参数 | `{"entityFqn":"汉江智行"}` |

### 2.3 settings.json 完整配置项

```json
{
  "llmProvider": "openai",
  "llmModel": "deepseek-v4-flash",
  "llmApiKey": "...",
  "llmBaseUrl": "",

  "extractionModel": "deepseek-v4-flash",
  "extractionApiKey": "...",
  "extractionBaseUrl": "https://api.deepseek.com",
  "extractionTemperature": 0.15,
  "extractionMaxTokens": 512,

  "answerModel": "deepseek-v4-pro",
  "answerApiKey": "...",
  "answerBaseUrl": "https://api.deepseek.com",
  "answerTemperature": 0.3,
  "answerTopP": 0.9,
  "answerMaxTokens": 4000,

  "embeddingModel": "BAAI/bge-m3",
  "embeddingDim": 384,
  "chunkSize": 512,
  "chunkOverlap": 64,

  "allowedFileTypes": ["*"],
  "maxFileSize": 50
}
```

## 3. 文件上传流程

### 3.1 时序流程

```
用户选择文件 → 填写文件属性 → 上传
  │
  └→ KnowledgeBaseWorkflowService.uploadFiles(
       securityContext, fileParts, metadataJson, projectId, overwrite)
      │
      ├ 1. 解析 metadataJson（JSON字符串 → Map）
      │   ├ 提取 files[] 数组（每个元素对应一个文件的属性）
      │   ├ 提取 targetFolder（全局子目录）
      │   └ 提取 uploadUsername 等全局属性
      │
      ├ 2. 解析角色分组
      │   └ securityContext → resolveRoleGroup() → dataGroup/lawGroup/...
      │
      ├ 3. 逐文件循环（for i, filePart）
      │   │
      │   ├ 3a. 获取原始文件名（处理UTF-8编码）
      │   ├ 3b. 跳过隐藏文件（.开头）
      │   ├ 3c. 检查文件类型白名单（allowedFileTypes）
      │   ├ 3d. 检查文件大小限制（maxFileSize）
      │   ├ 3e. 检查是否已存在（overwrite=true时覆盖）
      │   ├ 3f. 解析逐文件 targetFolder（从 metadata.files[i]）
      │   ├ 3g. 生成 fileId = UUID.randomUUID()
      │   ├
      │   ├ 3h. 保存文件
      │   │   └ Files.copy(inputStream, targetPath, REPLACE_EXISTING)
      │   │
      │   ├ 3i. 创建 meta.json
      │   │   ├ fileInfo（fileId, filename, storedPath, fileSize, uploadedAt）
      │   │   ├ + metadata.files[i] 中所有前端传入属性
      │   │   └ → {filename}.meta.json
      │   │
      │   └ 3j. 返回 uploadedFiles[]
      │
      └─→ 自动部署向量化 Pipeline（autoDeployPipeline）
           │
           ├ 1. 查找可用 DatabaseService
           │   └ 优先顺序：sample_data > local_mysql > e2e_test_db
           │
           ├ 2. 创建/更新 IngestionPipeline
           │   ├ pipelineType = KNOWLEDGEBASE
           │   ├ 注入 chunkSize / chunkOverlap / embeddingModel
           │   └ 关联到 DatabaseService
           │
           ├ 3. 通过 PipelineServiceClient 部署到 Airflow
           │   └ deployResponse.code == 200 → 继续
           │
           └ 4. 触发运行
               ├ 新建管道：最多重试3次，间隔3秒
               └ 已有管道：触发1次
```

### 3.2 角色分组映射

| 用户角色 | 子目录 | 映射条件 |
|---------|--------|---------|
| DataAssetEngineer | `dataGroup/` | roleName.contains("Engineer") |
| DataAssetLawyer | `lawGroup/` | roleName.contains("Lawyer") |
| DataAssetAccountant | `financeGroup/` | roleName.contains("Accountant") |
| DataAssetEvaluator | `valueGroup/` | roleName.contains("Evaluator") |

### 3.3 fileType 白名单校验

```
settings.json.allowedFileTypes:
  ["*"]             → 允许所有类型（默认）
  ["pdf", "docx"]   → 只允许PDF和DOCX
  空列表             → 不限制（跳过校验）
```

## 4. 向量化流程（Python Ingestion 层）

### 4.1 Airflow DAG 执行

```
Airflow DAG: KNOWLEDGEBASE (pipelineType=KNOWLEDGEBASE)
  │
  └→ KnowledgeBaseFileSource
      │
      ├ 1. 从 shared volume /data/knowledge_base/original/{projectId}/
      │    读取待处理的源文件
      │
      ├ 2. 文本提取（_extract_text）
      │   ┌──────────────────────────────────┐
      │   │ .txt          → 直接读原始文本    │
      │   │ .pdf          → PyPDF2.PdfReader │
      │   │ .docx/.doc    → python-docx      │
      │   │ .xlsx/.xls    → pandas.read_excel│
      │   │ .pptx/.ppt    → python-pptx      │
      │   │ .yml/.yaml/.sh/.sql/.md/.log/   │
      │   │ .py/.json     → 直接读原始文本    │
      │   │ .png/.jpg/.gif/webp/bmp → 跳过  │
      │   └──────────────────────────────────┘
      │
      ├ 3. Parent-Child 分块
      │   ├ chunkSize = settings.chunkSize (默认512)
      │   └ chunkOverlap = settings.chunkOverlap (默认64)
      │
      ├ 4. BGE-M3 嵌入（384维）
      │   └ sentence-transformers → embedding vector
      │
      ├ 5. 写入 ChromaDB
      │   ├ collection: knowledge_base_chunks
      │   ├ metadata:
      │   │   ├ source_file:   "汉江智行营业执照副本.png"
      │   │   ├ chunk_type:    "parent" | "child"
      │   │   ├ parent_id:     "parent_0_1" (child块专用)
      │   │   ├ file_type:     "png"
      │   │   └ chunk_size:    512
      │   └ document:          块文本内容
      │
      └ 6. 更新 meta.json
          └ vectorizationStatus = "VECTORIZED"
```

### 4.2 ChromaDB Collection 结构

```
Collection: knowledge_base_chunks
┌──────────────────────────────────────────────────────┐
│ id             │ 唯一标识（如 "parent_0_1"）         │
│ embedding      │ BGE-M3 384维浮点数向量               │
│ document       │ 块文本内容                           │
│ metadata       │ ┌────────────────────────────────┐  │
│                │ │ source_file     │ 文件名         │  │
│                │ │ chunk_type      │ parent/child   │  │
│                │ │ parent_id       │ 父块ID         │  │
│                │ │ file_type       │ png/pdf/docx  │  │
│                │ │ chunk_size      │ 字符数         │  │
│                │ └────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 4.3 向量化状态转化

```
enableVectorization=true                    enableVectorization=false
        │                                           │
        ▼                                           ▼
  vectorizationStatus = PENDING          vectorizationStatus = NOT_VECTORIZED
        │                                           │
        ▼                                           ▼
  Airflow DAG 执行                           不走向量化流程
        │
   ┌────┴────┐
   ▼         ▼
 成功       失败
   │         │
   ▼         ▼
VECTORIZED  NOT_VECTORIZED
            （保留原始状态）
```

## 5. QA 问答 5 阶段管道

### 5.1 总体流程

```
QARequest { question, projectId, fileList, userContext, maxResults, history }
  │
  ├─→ Stage 0: 属性提取
  │   ├ LLM 结构化提取 (deepseek-v4-flash, temp=0.15)
  │   ├ MCP entity_extract 提取命名实体
  │   └ 规则引擎 (KeywordExtractor + AttributeExtractor.keywordExtract)
  │   └→ attrs
  │       ├ search_keywords: ["汉江智行","营业执照","经营信息"]
  │       ├ need_mcp: false
  │       ├ mcp_service: ""
  │       ├ file_name/file_type/category/region/industry/...
  │       └ tags/description/applicable_period/target_dir/uploaded_by/...
  │
  ├─→ Stage 1: 文件过滤匹配
  │   ├ 触发条件: hasFiles && (hasKeywords || hasExplicitFilters)
  │   │   └ hasKeywords = search_keywords非空
  │   │   └ hasExplicitFilters = file_name/target_dir/file_type/tags/...
  │   ├ filterFilesByAttributes(attrs, fileList, question)
  │   │   ├ 收集关键词: search_keywords + description + category + region
  │   │   ├ FuzzyMatcher.score(fileName+3, desc+2, tags+2, cat+2, reg+2, dir+1, ext+1)
  │   │   ├ 动态阈值: maxScore≥6且gap≥2 → minScore=maxScore-2
  │   │   ├ Skill Swarm MCP 补充匹配
  │   │   └ 取并集去重 (FuzzyMatcher优先)
  │   └→ matchedFiles: ["汉江智行营业执照副本.png"]
  │
  ├─→ Stage 2: 向量检索
  │   ├ 查询构建
  │   │   ├ 原始问题: "从汉江智行营业执照中，识别出企业主要经营信息"
  │   │   ├ 单个关键词: "汉江智行", "营业执照", "经营信息"
  │   │   └ LLM扩展: 最多2条
  │   ├ Phase 1 — parent chunks
  │   │   ├ query: 每个查询变体独立执行
  │   │   ├ filter: chunk_type="parent" + source_file $in matchedFiles
  │   │   ├ n_results: topK × 4 (默认40)
  │   │   └→ docScores: {chunkId → similarity}
  │   ├ ─ Phase 1 无结果 → Fallback
  │   │   ├ filter: source_file $in matchedFiles (不限chunk_type)
  │   │   └ n_results: topK × 6 (默认60)
  │   ├ Phase 2 — child chunks
  │   │   ├ filter: chunk_type="child" + parent_id $in candidates
  │   │   ├ n_results: topK × 6 (默认60)
  │   │   └→ enrichment of docScores
  │   ├ RRF 融合
  │   │   ├ vecRank: 按相似度排序
  │   │   ├ kwRank: 按BM25关键词命中排序
  │   │   └ rrf = 1/(60+vecRank) + 1/(60+kwRank)
  │   └→ sources: [{chunkId, chunkText, similarity, source_file}]
  │
  ├─→ Stage 3: MCP集成
  │   ├ 始终执行: searchSystemMetadata()
  │   │   └ OpenMetadata SEARCH API → tables/glossaries
  │   └ 条件执行: need_mcp=true
  │       ├ 调用 MCP 工具 (get_entity_lineage/search_metadata/...)
  │       └→ sysCtx = 系统元数据 + MCP返回数据
  │
  └─→ Stage 4: 答案生成
      ├ 构建 ctxText = 向量块 + 历史 + 系统数据
      ├ 逐文件判定附件（见 5.2 文件处理矩阵）
      ├ buildLLMPrompt(question, ctxText, hasMatchedFiles)
      └ callAnswer(prompt, 0.3, attachedImages)
          └→ answer
```

### 5.2 文件处理矩阵（Stage 4）

| 文件格式 | 判定条件 | 处理方式 | 依赖 | 示例场景 |
|---------|---------|----------|------|---------|
| 图片 (png/jpg/gif/webp/bmp) | 任意 vectorizationStatus | 读字节 → base64 → `image_url` vision 附件 | JDK内置 | 营业执照扫描件 |
| 纯文本 (txt/md/json/csv/xml/yaml/log) | NOT_VECTORIZED 或 无向量块 | `Files.readString()` → ctxText | JDK内置 | 配置文件、日志 |
| 纯文本 (同上) | 有向量块 | 跳过，走 RAG | — | 已向量化的文档 |
| PDF（文字可提取） | NOT_VECTORIZED | PDFBox `PDFTextStripper` → ctxText | PDFBox 3.0.4 | 含文本的PDF报告 |
| PDF（扫描/图片型, 提取文本<50字符） | NOT_VECTORIZED | PDFBox `PDFRenderer` 第一页 → PNG → vision | PDFBox 3.0.4 | 扫描件PDF |
| DOXC/DOC | NOT_VECTORIZED 或 无向量块 | Tika `parseToString` → ctxText | Tika 3.1.0 | Word文档 |
| DOXC/DOC | 有向量块 | 跳过，走 RAG | — | 已向量化 |
| XLSX/XLS/PPTX/PPT/其他 | NOT_VECTORIZED 或 无向量块 | Tika `parseToString` → ctxText | Tika 3.1.0 | 表格/演示文稿 |
| XLSX/XLS/PPTX/PPT/其他 | 有向量块 | 跳过，走 RAG | — | 已向量化 |

### 5.3 Prompt 构建规则

```
有参考内容（向量块/文件内容/系统数据）:
  ## 用户问题
  {question}
  ## 参考内容
  {context}
  请根据参考内容回答用户问题。

无参考内容 + 已匹配文件（用户问题提到了文件但未匹配到内容）:
  ## 用户问题
  {question}
  请注意：未匹配到参考文件中与问题相关的具体内容。请根据你自身的知识回答用户问题。

无参考内容 + 无文件:
  ## 用户问题
  {question}
  请回答用户问题。
```

### 5.4 LLM API 调用格式

纯文本模式（OpenAI/DeepSeek兼容）:
```json
POST /v1/chat/completions
{
  "model": "deepseek-v4-pro",
  "messages": [
    {"role": "user", "content": "## 用户问题\n...\n## 参考内容\n..."}
  ],
  "temperature": 0.3,
  "top_p": 0.9,
  "max_tokens": 4000,
  "enable_thinking": true
}
```

多模态模式（带图片附件）:
```json
{
  "model": "deepseek-v4-pro",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "## 用户问题\n...\n## 参考内容\n..."},
      {"type": "image_url", "image_url": {
        "url": "data:image/png;base64,iVBORw0KGgo..."
      }}
    ]
  }],
  "temperature": 0.3,
  "top_p": 0.9,
  "max_tokens": 4000,
  "enable_thinking": true
}
```

### 5.5 置信度计算

```java
avgSimilarity = sum(similarity) / sources.size()
sourceFactor = min(1.0, sources.size() / 5.0)
confidence = avgSimilarity × sourceFactor
```

## 6. 属性提取规则引擎

### 6.1 分类词典 (CATEGORY_DICT)

| 分类 | 触发词 |
|------|--------|
| 财务 | 财务/会计/审计/年报/预算/税务/成本 |
| 技术 | 技术/开发/架构/研发/工程/部署/运维 |
| 合规 | 合规/法规/法务/制度/监管 |
| 产品 | 产品/需求/PRD/方案/设计文档 |
| 数据 | 数据/数据治理/数据资产/元数据/数据质量 |
| 运营 | 运营/业务/流程/管理 |
| 人力 | 人力/HR/招聘/绩效 |
| 商务 | 商务/合同/协议/报价 |

### 6.2 地区词典 (REGION_DICT)

| 地区 | 触发词 |
|------|--------|
| 中国 | 中国/国内/大陆/北京/上海/深圳/杭州 |
| 美国 | 美国/北美/硅谷/纽约 |
| 欧洲 | 欧洲/欧盟/英国/德国/法国 |
| 亚洲 | 亚洲/亚太/日本/韩国/新加坡 |
| 海外 | 海外/国际/global |

### 6.3 行业词典 (INDUSTRY_DICT)

| 行业 | 触发词 |
|------|--------|
| 金融 | 金融/银行/证券/保险/支付/基金 |
| 制造 | 制造/生产/工业/工厂/供应链 |
| 医疗 | 医疗/医药/医院/健康/生物 |
| 科技 | 科技/互联网/IT/软件/SaaS/云计算 |
| 能源 | 能源/电力/石油/天然气/新能源 |
| 零售 | 零售/电商/消费/品牌 |

### 6.4 关键词同义词典 (KeywordConfig.TYPE_SYNONYMS)

| 关键词 | 同义词 |
|--------|--------|
| 报告 | 报表/汇报/报告表/总结 |
| 合同 | 协议/合约/契约 |
| 方案 | 策划/规划/计划 |
| 数据 | dataset/数据集/数据库 |
| 规范 | 标准/规程/规定 |
| 纪要 | 记录/备忘录 |
| 制度 | 办法/条例/规定 |

### 6.5 FuzzyMatcher 匹配算法

```
isMatch(keyword, fileAttr):
  1. 直接包含: fileAttr.contains(keyword) → true
  2. 同义词: keyword在TYPE_SYNONYMS中 → 检查同义词是否匹配
  3. 分词: 按空格/下划线/连字符/括号等拆分 → 检查包含/被包含

score(keywords, fileName, fileType, tags, description, category, region, dir):
  for each keyword:
    fileName 匹配  → +3
    description 匹配 → +2
    tags 匹配       → +2
    category 匹配   → +2
    region 匹配     → +2
    dir 匹配        → +1
    fileType 匹配   → +1
```

### 6.6 动态阈值

```java
if (maxScore >= 6 && scoreGap >= 2) {
    minScore = maxScore - 2;   // 第一名明显领先
} else if (maxScore >= 4 && scoreGap >= 1) {
    minScore = maxScore - 1;   // 有小差距
} else {
    minScore = 1;              // 无差距，保留全部
}
```

## 7. MCP 工具清单

| 工具名 | 触发关键词 | 用途 | 参数 |
|--------|-----------|------|------|
| `search_metadata` | 数据资产/资产目录/数据目录/分级分类/分类/资产列表/搜索元数据/元数据查询 | 搜索 OpenMetadata 元数据 | query, size |
| `get_entity_details` | 企业信息/公司信息/实体详情/元数据详情 | 获取实体详细信息 | entityType, fqn |
| `get_entity_lineage` | 数据血缘/血缘分析/lineage/血缘关系/数据流向 | 获取数据血缘关系 | entityType, fqn, upstreamDepth, downstreamDepth |
| `semantic_search` | 语义搜索/语义检索/相似搜索/智能搜索/自然语言搜索 | 语义检索 | query, size |
| `get_test_definitions` | 质量规则/质量指标/测试定义 | 查询数据质量规则 | entityFqn |
| `root_cause_analysis` | 根因分析/故障分析/异常分析 | 根因分析 | entityFqn, metricName |
| `create_test_case` | 创建测试/质量测试 | 创建质量测试用例 | entityFqn |
| `create_glossary` | 创建术语 | 创建术语表 | — |
| `create_lineage` | 创建血缘/构建血缘 | 构建血缘关系 | — |
| `entity_extract` | Stage 0 自动调用 | 提取命名实体 | text |
| `skill_swarm` | Stage 1 自动调用 | 文件匹配补充 | keywords, files |

MCP 调用方式：JSON-RPC 2.0 over HTTP
```
POST http://localhost:8585/mcp
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "method": "tools/call",
  "params": {"name": "search_metadata", "arguments": {"query": "...", "size": 5}}
}
```

## 8. QA Response 结构

```json
{
  "answer": "从营业执照中识别到的企业主要经营信息如下：...",
  "relevantSources": [
    {
      "chunkId": "parent_0_1",
      "chunkText": "【上下文】汉江智行科技有限公司...",
      "similarity": 0.85,
      "metadata": {"source_file": "汉江智行营业执照副本.png"}
    }
  ],
  "totalSources": 3,
  "confidence": 0.68,
  "queryContext": {"search_keywords": ["汉江智行","营业执照","经营信息"]},
  "thinking": {
    "question": "从汉江智行营业执照中识别出企业主要经营信息",
    "attribute_extraction": {"search_keywords": [...], "need_mcp": false},
    "file_filter": {"has_filters": true, "matched_count": 1, "matched_files": [...]},
    "vector_search": {"query": "...", "chunks_found": 0, "chunks": []},
    "mcp": {"need_mcp": false, "result": "none"},
    "llm_prompt": "## 用户问题\n...\n## 参考内容\n...",
    "chromadb_query_chunks": [],
    "file_attachments": {"images_count": 1, "files": "..."},
    "answer_llm_request": "{...}",
    "answer_llm_response": "{...}"
  }
}
```

## 9. 系统配置变量

| 环境变量 | 用途 | 默认值 |
|---------|------|--------|
| `KNOWLEDGE_BASE_ENABLED` | 启用/禁用 KB | `true` |
| `KNOWLEDGE_BASE_STORAGE_BASE_PATH` | 文件存储根目录 | `/data/knowledge_base` |
| `KNOWLEDGE_BASE_STORAGE_TYPE` | 存储类型 | `local` |
| `KNOWLEDGE_BASE_CHROMADB_HOST` | ChromaDB 地址 | `http://chromadb:8000` |
| `KNOWLEDGE_BASE_SETTINGS_PATH` | settings.json 路径 | `/data/knowledge_base` |
| `KNOWLEDGE_BASE_EMBEDDING_DIM` | 嵌入维度 | `384` |
| `KNOWLEDGE_BASE_LLM_PROVIDER` | LLM 提供商 | `openai` |
| `KNOWLEDGE_BASE_LLM_MODEL` | LLM 模型 | `deepseek-v4-flash` |
| `KNOWLEDGE_BASE_LLM_ENDPOINT` | LLM 端点 | — |
| `KNOWLEDGE_BASE_LLM_API_KEY` | LLM 密钥 | — |
| `KB_EMBED_HOST` | 嵌入服务主机 | `ingestion` |
| `KB_EMBED_PORT` | 嵌入服务端口 | `8102` |
| `CHROMA_HOST` | ChromaDB 主机 | `openmetadata_chromadb` |
| `CHROMA_PORT` | ChromaDB 端口 | `8000` |
| `AUTHORIZATION_TOKEN` | MCP/API 鉴权 | — |
| `INGESTION_BOT_TOKEN` | Ingestion 鉴权（备选） | — |
| `PIPELINE_SERVICE_CLIENT_ENDPOINT` | Airflow 端点 | `http://ingestion:8080` |
| `DEFAULT_PROJECT_ID` | 默认项目ID | `default` |

## 10. 已知缺陷与修复记录

### 已修复

| # | 问题描述 | 文件 | 修复内容 |
|---|---------|------|---------|
| 1 | RRF 融合使用 `cid`（collection ID）而非 `chunkId` 作为 map key，导致所有 chunk 的 RRF 值相同、排序失效 | `VectorSearchService.java:310-317` | `kwScores.get(cid)` → `kwScores.get(chunkId)`, same for ranks and entry key |
| 2 | RRF 结果的 `source_file` 被设为 chunkId（如 `parent_0_1`）而非原始文件名，导致 Stage 4 文件匹配 `mf.equals(source_file)` 永远为假 | `VectorSearchService.java:328-332` | `md.put("source_file", chunkId)` → 使用 `chunkSourceFiles` map |
| 3 | `chunkSourceFiles` 在 Phase 1/fallback 已收集 `chunkId→sourceFile`，但 RRF 结果构建时未使用 | `VectorSearchService.java:200, 240` | Phase 1/fallback 收集并保存，RRF 循环中使用 |
| 4 | `hasFileFilters` 不检查 `search_keywords`，导致有搜索关键词但无显式过滤属性时文件匹配被跳过 | `QAService.java:646-667` | 增加 `hasKeywords` 条件：`hasFiles && (hasKeywords \|\| hasExplicitFilters)` |
| 5 | Prompt 强制"数据合规律师"角色，回答全是合规报告模板 | `QAService.java:374-388` | 改为无角色设定，根据三种场景（有内容/无内容有文件/无内容无文件）动态生成 prompt |
| 6 | 图片文件不发 vision 附件，LLM 无法识别图片内容 | `QAService.java:855-872` | `Files.readAllBytes` → base64 → `image_url` content，与 prompt 文本一起发送 |
| 7 | PDF 扫描件不发 vision（`PDFDocument.load` 参数错误 + PDFBox 3.x `Loader` API） | `QAService.java:882-912` | 文本>50字符→PDFStripper提取；<50字符→PDFRenderer渲染为PNG→vision |
| 8 | 缺少 Tika 依赖，Office 文档（DOCX/XLSX/PPTX）无法提取文本 | `pom.xml + FileService.java:203-211` | 添加 `tika-core` + `tika-parsers-standard-package`，增加 `extractText()` 方法 |
| 9 | 数据资产/血缘分析/分级分类等关键词未能触发 MCP 调用 | `AttributeExtractor.java:66-76` | 扩增 `MCP_TOOL_DICT` 触发词，补充"血缘分析/数据流向/资产目录/分级分类/智能搜索/企业信息"等 |
| 10 | `generateAnswerFromSources` 方法签名没传 `images` 参数，图片附件在 RAG 路径丢失 | `QAService.java:992-1000` | 重构为统一路径：全部通过主流程 `callAnswer(llmPrompt, 0.3, images)` |

### 未修复（已知限制）

| # | 限制 | 说明 |
|---|------|------|
| 1 | ChromaDB 无距离阈值 | query 返回前 topK 条，无最小相似度门槛，低质量匹配结果可能混入 |
| 2 | 多页 PDF 仅渲染第一页 | 扫描型 PDF 超过1页时，只发送第1页的图片渲染 |
| 3 | PDFBox/Ollama/Anthropic 路径无 vision 支持 | 仅 OPENAI 路径（DeepSeek兼容）支持多模态 `image_url` 附件 |
| 4 | 无 embedding distance 阈值 | `chunk_type=parent` 和 child 查询不设距离过滤，理论上会返回完全不相关的 chunk |
| 5 | 向量化状态非实时刷新 | 向量化完成后通过 Airflow 更新 meta.json，需再次调用 listFiles 才可见最新状态 |