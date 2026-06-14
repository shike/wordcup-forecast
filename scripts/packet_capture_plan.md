# 懂球帝 / 虎扑 App 接口抓包方案

目标：拿到懂球帝（Dongqiudi / All Football）和虎扑（Hupu）App 内部用于加载赛程、比分、球员数据、评分的真实 API 端点。

## 一、工具选择

| 工具 | 平台 | 适用场景 |
|------|------|---------|
| **Charles Proxy** | macOS / Windows | 最简单，支持 SSL 解密、重放、Map Remote |
| **Fiddler Everywhere** | 跨平台 | 免费替代品，功能类似 Charles |
| **Wireshark** | 跨平台 | 不需要代理设置，但解析 HTTPS 需要私钥或 TLS 1.2 环境 |
| **Frida + Objection** | Android / iOS | 绕过 SSL Pinning |
| **Postern / Drony** | Android | 将 App 流量强制转发到 Charles |

推荐组合：**Charles + Android 模拟器（雷电/夜神）+ Frida（如有 SSL Pinning）**。

## 二、Charles 基础配置

1. 安装 Charles，进入 `Proxy → SSL Proxying Settings`。
2. 添加 `*.*` 到 SSL Proxying 列表（或只加 `*.dongqiudi.com`、`*.hupu.com`、`api.dongqiudi.com`、`games.mobileapi.hupu.com`）。
3. 开启 `Proxy → macOS Proxy` / `Windows Proxy`。
4. 在手机/模拟器 Wi-Fi 中设置手动代理：
   - 服务器：Charles 所在电脑 IP
   - 端口：默认 `8888`
5. 手机浏览器访问 `chls.pro/ssl` 下载并安装 Charles 根证书。
   - Android：设置 → 安全 → 从存储安装证书。
   - iOS：安装后还要去 设置 → 通用 → 关于本机 → 证书信任设置 里开启完全信任。

## 三、懂球帝 App 抓包重点

### 3.1 先抓网页版热身

打开 `https://www.dongqiudi.com/match/` 或 `https://m.dongqiudi.com/`，在 Charles 里观察：
- 页面加载后是否有 XHR/Fetch 请求到 `api.dongqiudi.com`。
- 留意 URL 模式，如 `/v1/...`、`/v2/...`、`/app/...`、`/match/...`。
- 记录请求头中的 `Authorization`、`token`、`sign`、`device-id` 等字段。

### 3.2 App 抓包

1. 打开懂球帝 App，进入「比赛」Tab。
2. 在 Charles 中过滤 `dongqiudi`。
3. 重点关注以下数据对应的请求：
   - 比赛列表 / 赛程
   - 比赛详情（比分、事件、统计）
   - 球队阵容 / 球员评分
   - 积分榜、射手榜、助攻榜
   - 新闻列表（已确认旧端点 `/mobile/tab/1/archives?page=N` 已死）

### 3.3 常见端点猜测（需验证）

```text
https://api.dongqiudi.com/v1/matches
https://api.dongqiudi.com/v1/match/{id}
https://api.dongqiudi.com/v1/schedule
https://api.dongqiudi.com/v1/standings/{league_id}
https://api.dongqiudi.com/v1/topscorers/{league_id}
https://api.dongqiudi.com/v1/team/{id}/squad
```

## 四、虎扑 App 抓包重点

### 4.1 网页版入口

- 虎扑足球赛程：`https://soccer.hupu.com/`
- 虎扑评分：`https://m.hupu.com/score-item/common_second/{player_id}`

### 4.2 App 抓包

过滤域名：
- `games.mobileapi.hupu.com`
- `soccer.hupu.com`
- `m.hupu.com`

重点关注：
- 赛程接口
- 比赛详情统计
- 球员评分接口（JRs 评分 / SS 评分）
- 新闻/战报接口

### 4.3 常见端点猜测（需验证）

```text
https://games.mobileapi.hupu.com/1/1.0.0/match/getMatchList
https://games.mobileapi.hupu.com/1/1.0.0/match/getMatchDetail
https://games.mobileapi.hupu.com/1/1.0.0/player/getPlayerRating
```

## 五、绕过 SSL Pinning

如果 Charles 中很多请求显示 `<unknown>` 或 App 直接无法联网，说明有 SSL Pinning。

### Android（推荐）

1. 使用 Android 7 及以下系统的模拟器，或把 App 安装到系统证书区。
2. 或者用 Frida：
   ```bash
   # 安装 Frida-server 到手机/模拟器
   adb push frida-server /data/local/tmp/
   adb shell "chmod 755 /data/local/tmp/frida-server"
   adb shell "/data/local/tmp/frida-server &"

   # 运行通用 SSL Pinning 绕过脚本
   frida -U -f com.dongqiudi.app --no-pause -l ssl-pinning-disable.js
   ```
3. 通用脚本地址：`https://codeshare.frida.re/@pcipolloni/universal-android-ssl-pinning-bypass-2/`

### iOS

1. 越狱设备安装 `SSL Kill Switch 2`。
2. 或者使用 Frida + objection：
   ```bash
   objection -g com.dongqiudi.app explore
   ios sslpinning disable
   ```

## 六、导出与分析

1. 在 Charles 中选中所需请求 → `File → Export Session → HAR`。
2. 使用 `scripts/parse_har_apis.py` 提取端点和参数：
   ```bash
   python scripts/parse_har_apis.py path/to/dongqiudi.har --domain dongqiudi
   python scripts/parse_har_apis.py path/to/hupu.har --domain hupu
   ```
3. 将发现的端点补充到本计划或 `src/data/scrapers/` 中。

## 七、法律与合规提示

- 仅用于个人项目、学习研究或已获得授权的场景。
- 控制请求频率，不要对服务器造成压力。
- 尊重 App 的《用户协议》和 `robots.txt`。
- 商业用途请联系官方获取数据授权。

## 八、下一步

抓到真实端点后，可以：
1. 在 `src/data/scrapers/` 下新增 `dongqiudi.py` / `hupu.py`。
2. 把中文球员名、中文队名、评分、赔率等字段接入 `src/data/features.py`。
3. 用抓到的端点替换失效的旧接口（如 `dongqiudi.com/data/team_ranking/51`）。
