# 世界杯预测程序 · Word Cup Forecast

输入两支球队，生成完整的 PPT 预测报告（含阵容、关键对位、三模型对比、蒙特卡洛模拟、最终结论）。

> 世界杯预测程序 / World Cup Match Forecast · 基于 Python 3.11+ / python-pptx / pandas / scikit-learn

## 快速开始

```bash
# 激活虚拟环境
source venv/bin/activate

# 列出已知球队
python predict.py --list-teams

# 仅做预测，不生成 PPT
python predict.py --team-a 巴西 --team-b 阿根廷 --dry-run

# 完整预测 + 生成 PPT
python predict.py --team-a 巴西 --team-b 阿根廷 \
  --match-date 2026-07-05 --stage final --simulations 10000

# 拉取今晚（指定日期）的赛程
python predict.py --fetch-fixtures 2026-06-15

# 预测赛程列表中第 N 场
python predict.py --predict-fixture 1 --fixture-date 2026-06-15
```

PPT 输出到 `./输出/{主队}_对阵_{客队}_{日期}.pptx`。

## 17 页 PPT 内容

| # | 页面 |
|---|---|
| 1 | 封面 + 推荐结果 + 综合概率 |
| 2 | 执行摘要 + 最可能比分 TOP 5 |
| 3 | 球队档案（FIFA / ELO / 主教练 / 队长） |
| 4 | 近期状态（近 10 场 + 攻守数据） |
| 5 | 预测首发 · A 队（阵型图 + 11 球员卡） |
| 6 | 预测首发 · B 队 |
| 7 | A 队核心球员 TOP 5（FIFA UT 风格卡） |
| 8 | B 队核心球员 TOP 5 |
| 9 | 关键对位 1v1（4 组对决） |
| 10 | 阵容深度（首发 vs 替补） |
| 11 | 球队能力雷达（6 维） |
| 12 | 定性因子 + 伤停名单 |
| 13 | 三模型概率对比（ELO / Poisson / XGBoost） |
| 14 | 蒙特卡洛模拟（TOP 比分） |
| 15 | 敏感性分析 |
| 16 | 最终预测 + 关键风险 |
| 17 | 附录（数据源 + 方法说明 + 免责声明） |

## 三层预测模型

| 层 | 模型 | 作用 |
|---|---|---|
| 1 | ELO | 历史实力基线 |
| 1 | Poisson + Dixon-Coles | 进球分布 → 胜平负 |
| 1 | XGBoost (GradientBoosting) | 梯度提升分类 |
| 2 | 定性调整 | 战术 / 经验 / 心理 / 场地 |
| 3 | 蒙特卡洛（10,000 次模拟） | 比分分布 + 概率 |

## 已支持的球队（带真实阵容种子）

**顶级 9 队：** 巴西 (BRA) / 阿根廷 (ARG) / 法国 (FRA) / 英格兰 (ENG) / 德国 (GER) / 西班牙 (ESP) / 葡萄牙 (POR) / 比利时 (BEL) / 埃及 (EGY)

**其他球队**（首次运行自动生成占位阵容）：荷兰 / 意大利 / 美国 / 墨西哥 / 日本 / 韩国 / 澳大利亚 / 摩洛哥 / 塞内加尔 / 佛得角 / 巴拉圭 / 波黑 / 加拿大 / 克罗地亚 / 瑞士 等

占位阵容可在 `data/squads/{CODE}.json` 中替换为真实球员数据。

## 项目结构

```
wordcup-forecast/
├── predict.py                       # CLI 入口（中文帮助）
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   ├── teams.json                   # 16 支球队基础信息
│   ├── formations.json              # 8 种阵型定义
│   └── squads/{CODE}.json           # 各国阵容种子（9 个真实阵容）
├── src/
│   ├── data/                        # 数据层
│   │   ├── api_client.py            # football-data.org 客户端
│   │   ├── wikipedia_client.py      # 球员信息 + 照片
│   │   ├── fixtures.py              # 赛程拉取（ESPN 公开 API）
│   │   ├── team_data.py
│   │   ├── squads.py
│   │   └── manual_input.py
│   ├── models/                      # 预测模型
│   │   ├── elo.py
│   │   ├── poisson.py
│   │   ├── ml_model.py
│   │   ├── adjustments.py
│   │   └── monte_carlo.py
│   ├── lineup/                      # 首发预测
│   │   ├── formations.py
│   │   ├── predictor.py
│   │   └── matchup_engine.py
│   ├── ppt/                         # PPT 生成
│   │   ├── builder.py               # 主流程（17 页 PPT）
│   │   ├── styles.py                # 视觉风格
│   │   ├── charts.py                # matplotlib 图表
│   │   ├── pitch_layout.py          # 球场阵型图
│   │   └── player_card.py           # FIFA UT 风格球员卡
│   ├── pipeline.py                  # 预测主流程
│   └── utils/                       # 工具
│       ├── config.py                # 配置（输出/缓存路径）
│       ├── i18n.py                  # 中英双语字典
│       ├── image.py                 # 图片处理
│       ├── logging.py
│       └── models.py                # Pydantic 数据模型
├── 输出/                            # 生成的 PPT
├── 缓存/                            # 球员照片、API 响应
└── venv/                            # Python 虚拟环境
```

## CLI 参数（全部中文帮助）

```
python predict.py --help
```

| 参数 | 说明 |
|---|---|
| `--team-a` | 主队（中文 / 英文 / 三字代码，如 `巴西` / `Brazil` / `BRA`） |
| `--team-b` | 客队（同上） |
| `--match-date` | 比赛日期 YYYY-MM-DD |
| `--stage` | 阶段：group / round_of_16 / quarterfinal / semifinal / final / third_place |
| `--venue` | 比赛场地 |
| `--lang` | PPT 语言：zh / en / bilingual |
| `--simulations` | 蒙特卡洛模拟次数（默认 10000） |
| `--dry-run` | 不生成 PPT |
| `--output` | 指定 PPT 输出路径 |
| `--list-teams` | 列出已知球队 |
| `--fetch-fixtures [日期]` | 拉取赛程列表 |
| `--all-fixtures` | 显示所有比赛（不仅顶级联赛） |
| `--predict-fixture N` | 预测赛程列表中第 N 场 |
| `--fixture-date` | 配合 `--predict-fixture` 指定日期 |

## 数据源

- **ESPN 公开 API**（主源）· 实时赛程
- **Wikipedia REST API** · 球员信息和照片
- **football-data.org** · 球队国际比赛历史（需 API Key）
- **本地种子阵容** · 各国阵容种子库
- **World Football ELO Ratings** · ELO 评分方法

## 已通过的测试场景

| 比赛 | 阶段 | 综合概率 |
|---|---|---|
| 巴西 vs 阿根廷 | 决赛 | 33.8% / 20.9% / 45.4% |
| 法国 vs 西班牙 | 半决赛 | 已生成 |
| 美国 vs 日本 | 小组赛 | 已生成 |
| 加拿大 vs 波黑 | 世界杯 06-12 | 55.0% / 19.2% / 25.8% |
| 美国 vs 巴拉圭 | 世界杯 06-12 | 51.6% / 19.4% / 29.0% |

## 已知限制

- 球员照片默认从 Wikipedia 拉取 + 缓存到 `缓存/球员照片/`；网络不可用时回退到首字母占位卡
- XGBoost 模型用合成数据训练（5000 样本）。生产环境应替换为 `data/historical_matches.csv` 真实历史
- matplotlib 不带 CJK 字体时图表内中文显示为 □，但 PPT 文字层完整；可把 CJK 字体放到 `assets/fonts/`

## 许可

仅供学习与个人使用。
