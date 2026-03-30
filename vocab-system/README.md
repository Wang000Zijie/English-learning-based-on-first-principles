# 词汇学习系统 v3

本项目是一个本地运行的英语词汇学习工具，核心能力是：
- AI 新词分析入库
- 间隔复习
- 造句纠错
- 阅读短文生成（熟词语境 + 生词注入）
- 词汇本管理（统计、筛选、排序、闪卡）

## 版本与状态
- 当前版本：v3.x
- 最近整理时间：2026-03-30
- 状态：可直接运行，功能测试通过

## 核心特性

### 1) 新词分析
- 支持中英混合/换行输入清洗
- 支持流式进度展示
- 支持中途停止，停止后结果不入库

### 2) 今日复习
- 基于复习记录自动计算待复习词
- 复习结果回写并驱动词级别变化

### 3) 阅读短文
- 支持剧情走向与自定义走向
- 熟词喂给量、生词喂给量可配置
- 支持停止生成
- 历史短文支持直接加载和删除
- 双语高亮联动：英文目标词与中文锚点对应高亮

### 4) 词汇本
- 支持生词库/熟词库切换
- 支持编辑、批量删除、导出、自测
- 统计字段包含：抽中次数、复习次数、正确率
- 支持单项排序与多因素组合排序

### 5) 多模型配置
- 支持 Provider：minimax、kimi、deepseek、gpt、gemini
- 顶部栏可动态切换 Provider/Model
- 支持联调角色分配（author/analyst/reviewer/news_fetcher）

## 项目结构

```text
core/          核心业务逻辑（API、生成、复习、词处理）
data/          SQLite 管理与本地数据库
ui/            桌面界面（customtkinter）
prompts/       各模块提示词
scripts/       辅助脚本（如熟词导入）
main.py        程序入口
functional_test.py  功能回归入口
```

## 快速开始

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 配置文件
1. 复制 `config.example.yaml` 为 `config.yaml`
2. 在 `config.yaml` 中填写 API Key

### 3) 启动
```bash
python main.py
```

### 4) 运行功能测试
```bash
python functional_test.py
```

### 5) 清理测试与缓存产物
```powershell
powershell -ExecutionPolicy Bypass -File scripts/clean_artifacts.ps1
```

## 配置说明

### 学习配置
- `learning.review_intervals`: 复习间隔
- `learning.passage.familiar_reference_words`: 熟词喂给量
- `learning.passage.new_word_feed_count`: 生词喂给量
- `learning.passage.continue_previous_chapter`: 是否续写上一章（默认 false）

### UI 配置
- `ui.font_size`: 字体大小
- `ui.window_width` / `ui.window_height`: 窗口尺寸

## 数据与隐私
- 数据默认存储在 `data/vocab.db`
- 不会主动上传本地数据库
- 仅在调用模型 API 时发送必要文本内容

## 本次整理内容
- 清理了运行缓存与测试产物（`__pycache__`、测试数据库、日志）
- 新增 `.gitignore`，避免把本地隐私和大文件上传到仓库
- 新增 `config.example.yaml`，用于安全分享项目
- 移除未使用依赖：`anthropic`

## GitHub 发布建议
1. 初始化仓库并提交
2. 配置远程仓库地址
3. 推送到 GitHub

示例命令：
```bash
git init
git add .
git commit -m "chore: cleanup project and refresh docs"
git branch -M main
git remote add origin <你的仓库地址>
git push -u origin main
```
