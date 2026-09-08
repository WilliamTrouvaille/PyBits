# IMG

IMG 是一个通过 OpenAI Images API 兼容后端生成图片的命令行工具。它从 `IMG/.env` 读取多组 `base_url + api_key + model` 配置，按确定性规则选择 provider，然后发送 `/v1/images/generations` 请求并保存返回的图片。

## 配置

IMG 不读取系统环境变量，只从文件系统中的 `IMG/.env` 读取配置：

```dotenv
IMG_PROVIDER_NAMES=main,backup
IMG_DEFAULT_PROVIDER=main

IMG_MAIN_BASE_URL=https://api.openai.com
IMG_MAIN_API_KEY=sk-...
IMG_MAIN_MODEL=gpt-image-2

IMG_BACKUP_BASE_URL=https://example.com
IMG_BACKUP_API_KEY=...
IMG_BACKUP_MODEL=gpt-image-2
```

`IMG_*_BASE_URL` 可以填写 `https://example.com` 或 `https://example.com/v1`；IMG 会在代码中统一规范化为 OpenAI 兼容的 `/v1` 根地址，并避免重复追加。

全局安装后，从任意目录运行 `IMG` 时，工具按以下顺序查找第一个存在的 `.env`：

1. 当前工作目录及其每一级父目录下的 `IMG/.env`。
2. `~/CODE/PYTHON/PyBits/IMG/.env`。
3. 已安装或当前源码包旁边的 `IMG/.env`。

Provider 选择规则：

1. 如果传入 `--provider NAME`，使用该 provider。
2. 否则如果 `.env` 中存在 `IMG_DEFAULT_PROVIDER=NAME`，使用该 provider。
3. 否则使用 `IMG_PROVIDER_NAMES` 中的第一项。

`IMG/.env` 已被 git 忽略，请不要提交 API key。

## 使用示例

```bash
IMG generate --prompt "A plain red square" --out ./output/image.png
IMG generate --prompt-file prompt.txt --out ./output/image.png
IMG generate --provider backup --prompt "A small icon" --out ./icon.png
```

Dry-run 不会发送网络请求，但仍会读取 `.env` 并输出将要使用的 provider、payload 和输出路径：

```bash
IMG generate --prompt "test" --out /tmp/img-test.png --dry-run
```

## 参数

```text
IMG generate [OPTIONS]

必填:
  --prompt TEXT          直接提供提示词；与 --prompt-file 二选一。
  --prompt-file PATH     从文本文件读取提示词；与 --prompt 二选一。
  --out PATH             输出图片路径。

可选:
  --provider NAME        指定 .env 中的 provider。
  --model MODEL          覆盖 provider 默认模型。
  --size SIZE            图片尺寸，默认 auto。
  --quality VALUE        质量：low、medium、high、auto，默认 medium。
  --output-format VALUE  输出格式：png、jpeg、jpg、webp，默认 png。
  --n N                  生成数量，1 到 10，默认 1。
  --force                允许覆盖已有输出文件。
  --dry-run              只打印请求摘要，不发送请求。
  --request-timeout SEC  请求超时时间，默认 120 秒。
  -v, --verbose          显示详细日志。
```

## 输出规则

- `--n 1` 时写入 `--out` 指定路径；如果路径没有扩展名，会按 `--output-format` 自动补全。
- `--n > 1` 时写入 `<stem>-1.<ext>`、`<stem>-2.<ext>` 等路径。
- 输出文件已存在且未传 `--force` 时，命令会在发送请求前失败，避免产生不可写结果。
- 图片先写入同目录临时文件，再原子替换为目标路径，避免半文件。

## 错误格式

可预期错误输出为：

```text
错误: ...
提示: ...
```

常见处理：

- 缺少配置：在 `IMG/.env` 中补充 `IMG_PROVIDER_NAMES` 和对应 provider 的 `BASE_URL`、`API_KEY`、`MODEL`。
- 鉴权失败：检查当前 provider 的 API key。
- 后端返回 URL：IMG 会下载该 URL 并写入本地文件；错误信息只显示 URL host，不显示完整签名 URL。
