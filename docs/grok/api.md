Image generations
Grok Web 图片生成，支持 n、宽高比、1k/2k、URL、Base64 和扩展流式输出。
POST /v1/images/generations
接入信息
Base URL
https://your-chatgpt2api.example/v1
鉴权 Header
Authorization: Bearer g2a_...
请求参数
参数 说明
model * 模型页中已启用且当前存在可用账号支持的对外模型名称。
prompt * 用于生成或编辑图片的自然语言描述。
n 需要返回的图片数量；Web 会原样映射为上游 num_generations。
aspect_ratio 输出媒体的宽高比，例如 1:1、2:3 或 16:9。
resolution Console 图片支持 1k/2k；Web 图片生成忽略 resolution/quality，并由模型名
称选择上游产品。
quality Console Image 2.0 的生成质量，可选 low 或 medium；默认 medium。Web
图片生成路由忽略该字段。
response_format 图片返回格式，支持 url 或 b64_json。
stream 是否使用图片生成扩展 SSE 流；默认 false。
调用示例
cURL grok-imagine-image-2.0
export GROK2API_API_KEY="g2a_your_api_key"
curl -X POST "https://your-chatgpt2api.example/v1/images/generations" \
 -H "Authorization: Bearer $GROK2API_API_KEY" \
请求 响应
Grok2API © 2026 · Built by Chenyme
Grok2API v3.1.5
 -H "Content-Type: application/json" \
 -d '{
 "model": "grok-imagine-image-2.0",
 "prompt": "A minimal red chair in a bright studio",
 "n": 1,
 "response_format": "url"
}'
实现说明
客户端通过 n 指定图片数量；Web 将其原样映射为上游 num_generations。
生成结果统一归档到媒体存储；url 返回网关资源地址，b64_json 返回编码后的图片内容。


Image edits
Grok Web 图片编辑，使用官方 JSON 图片 URL 协议。
POST /v1/images/edits
接入信息
Base URL
https://your-chatgpt2api.example/v1
鉴权 Header
Authorization: Bearer g2a_...
请求参数
参数 说明
model * 模型页中已启用且当前存在可用账号支持的对外模型名称。
prompt * 用于生成或编辑图片的自然语言描述。
image / images * 待编辑图片，使用 image 或 images 传入 URL、Data URL 或已支持的图片引
用。
n 需要返回的图片数量；Web 会原样映射为上游 num_generations。
quality Console Image 2.0 的生成质量，可选 low 或 medium；默认 medium。Web
图片生成路由忽略该字段。
response_format 图片返回格式，支持 url 或 b64_json。
调用示例
cURL grok-imagine-image-2.0
export GROK2API_API_KEY="g2a_your_api_key"
curl -X POST "https://your-chatgpt2api.example/v1/images/edits" \
 -H "Authorization: Bearer $GROK2API_API_KEY" \
 -H "Content-Type: application/json" \
 -d '{
 "model": "grok-imagine-image-2.0",
 "prompt": "Change the chair to black",
请求 响应

Grok2API v3.1.5
 "image": {
 "url": "https://example.com/chair.png"
 },
 "n": 1,
 "response_format": "url"
}'
实现说明
图片编辑采用 JSON 请求体，不提供 multipart 兼容层。
远程图片会经过 SSRF、防体积超限和内容类型校验后再上传到上游。
生成结果统一归档到媒体存储；url 返回网关资源地址，b64_json 返回编码后的图片内容。
