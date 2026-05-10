# cc-connect 环境文件发送

当 song-study 运行在 cc-connect 环境中时（系统 prompt 提示 "You are running inside cc-connect"），生成文件后应自动推送到用户的消息平台。

## 发送方式：Python 直连（禁止 shell curl）

**shell `curl -F` 传 CJK 文件名时会损坏 UTF-8 编码，导致文件内容变成 `�` 替换字符，客户端无法打开。** 必须用 Python `urllib` 的 `multipart/form-data` 直接编码。

### 可复用脚本

本 skill 自带 `scripts/feishu_sender.py`，接受文件路径列表作为命令行参数：

```bash
PYTHONUTF8=1 python "<skill-dir>/scripts/feishu_sender.py" <file1> <file2> ...
```

### 脚本逻辑

1. 从 `~/.cc-connect/config.toml` 读 `app_id` / `app_secret`
2. 从 `~/.cc-connect/sessions/<project>_<hash>.json` 的 `active_session` 找 `feishu:oc_*` 格式的 chat_id
3. `urllib` POST 获取 `tenant_access_token`
4. `urllib` multipart/form-data 上传文件（正确处理 UTF-8 文件名）
5. `urllib` JSON POST 发送文件消息到 `im/v1/messages`

### 为什么不用 shell

- shell 变量中的 CJK 字符经 `$VAR` 展开后，在多级管道和 JSON 拼接中编码不可控
- `grep -o | cut` 提取 token 在复杂响应中脆弱
- curl `-F "file_name=中文.md"` 在 Windows bash 环境下实测产生 `�` 替换字符
- Python `urllib.request` 的字节级控制保证编码正确性

### 验证标准

发送后检查响应中 `code` 字段为 `0`，`file_name` 字段不含 `�` 替换字符。
