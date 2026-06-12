# World Cup Forecast · 世界杯预测程序

A Python program that takes two football teams as input and outputs a complete PowerPoint report with a full match prediction: lineups, key matchups, model probabilities, Monte Carlo simulation, and a final pick.

## 快速开始

```bash
# activate venv
source venv/bin/activate

# list known teams
python predict.py --list-teams

# dry-run (no PPT)
python predict.py --team-a Brazil --team-b Argentina --dry-run

# full prediction + PPT
python predict.py --team-a Brazil --team-b Argentina \
  --match-date 2026-07-05 --stage final --simulations 10000
```

PPT outputs to `./output/{TeamA}_vs_{TeamB}_{date}.pptx`.

## 17-页 PPT 内容

| # | 页面 |
|---|---|
| 1 | 封面 + 推荐结果 + 综合概率 |
| 2 | 执行摘要 + TOP 5 比分 |
| 3 | 球队档案（FIFA / ELO / 教练 / 队长） |
| 4 | 近期状态（10 场 W/D/L + 攻守数据） |
| 5 | 预测首发 A 队（阵型图 + 11 球员卡） |
| 6 | 预测首发 B 队 |
| 7 | A 队核心球员 TOP 5（FIFA UT 风格卡） |
| 8 | B 队核心球员 TOP 5 |
| 9 | 关键对位 1v1（4 组对决） |
| 10 | 阵容深度（首发 vs 替补） |
| 11 | 能力雷达（6 维） |
| 12 | 定性因子 + 伤停 |
| 13 | 三模型概率对比（ELO / Poisson / XGBoost） |
| 14 | 蒙特卡洛模拟（TOP 比分） |
| 15 | 敏感性分析 |
| 16 | 最终预测 + 关键风险 |
| 17 | 附录（数据源 + 方法 + 免责声明） |

## 三层预测模型

| 层 | 模型 | 作用 |
|---|---|---|
| 1 | ELO | 历史实力基线 |
| 1 | Poisson + Dixon-Coles | 进球分布 → 胜平负 |
| 1 | XGBoost (GradientBoosting) | 梯度提升分类 |
| 2 | Qualitative adjustments | 战术 / 经验 / 心理 / 场地 |
| 3 | Monte Carlo (10k 模拟) | 比分分布 + 概率 |

## 已支持的球队（带真实阵容）

BRA / ARG / FRA / ENG / GER / ESP / POR

其他球队（NED, ITA, USA, MEX, JPN, KOR, AUS, MAR, SEN）首次运行会生成占位阵容，球员数据可在 `data/squads/{CODE}.json` 中替换。

## 项目结构

```
wordcup-forecast/
├── predict.py                  # CLI 入口
├── src/
│   ├── data/
│   │   ├── api_client.py       # football-data.org
│   │   ├── wikipedia_client.py # 球员信息 + 照片
│   │   ├── team_data.py        # 球队数据
│   │   ├── squads.py           # 阵容加载
│   │   └── manual_input.py     # 手工调整
│   ├── models/
│   │   ├── elo.py              # ELO 模型
│   │   ├── poisson.py          # Poisson + Dixon-Coles
│   │   ├── ml_model.py         # XGBoost
│   │   ├── adjustments.py      # 定性调整
│   │   └── monte_carlo.py      # 蒙特卡洛
│   ├── lineup/
│   │   ├── formations.py       # 8 种阵型
│   │   ├── predictor.py        # 首发预测
│   │   └── matchup_engine.py   # 1v1 对位
│   ├── ppt/
│   │   ├── builder.py          # 主流程
│   │   ├── styles.py           # 视觉风格
│   │   ├── charts.py           # matplotlib 图表
│   │   ├── pitch_layout.py     # 球场阵型图
│   │   └── player_card.py      # 球员卡渲染
│   ├── pipeline.py             # 预测主流程
│   └── utils/
│       ├── config.py           # 配置
│       ├── i18n.py             # 中英双语
│       ├── image.py            # 图片处理
│       ├── logging.py          # 日志
│       └── models.py           # Pydantic 数据模型
├── data/
│   ├── teams.json
│   ├── formations.json
│   └── squads/{CODE}.json      # 7 个真实阵容
├── output/                      # PPT 输出
├── cache/                       # Wikipedia + 球员照片
└── requirements.txt
```

## CLI 参数

```
--team-a TEXT          队 A (英文 / 中文 / 代码)
--team-b TEXT          队 B
--match-date YYYY-MM-DD
--stage {group, round_of_16, quarterfinal, semifinal, final, third_place}
--venue TEXT
--lang {zh, en, bilingual}
--simulations INT      蒙特卡洛模拟次数 (默认 10000)
--dry-run              不生成 PPT
--output PATH          PPT 输出路径
--list-teams           列出已知球队
```

## 已通过的测试场景

| 比赛 | 阶段 | 预测胜方 | 胜/平/负 |
|---|---|---|---|
| Brazil vs Argentina | Final | Argentina | 33.8% / 20.9% / 45.4% |
| France vs Spain | Semifinal | — | (已生成) |
| USA vs Japan | Group | — | (已生成) |

## 已知限制

- 球员照片默认从 Wikipedia 拉取 + 缓存；如果网络不可用会回退到文字卡
- XGBoost 模型用合成数据训练（5000 样本）。生产环境应替换为真实历史比赛
- matplotlib 不带 CJK 字体时图表内中文显示为 □，但 PPT 文字层不受影响
