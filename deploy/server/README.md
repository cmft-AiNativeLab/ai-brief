# 固定域名静态站部署

服务器目录：`/mnt/data/ai-brief-web`

```bash
docker compose up -d
```

容器不开放宿主机端口，只加入 `nginx-proxy-manager_default` 网络。Nginx Proxy Manager 转发：

- 域名：`brief.ai-native-lab.com`
- 上游：`http://ai-brief-web:80`
- 证书：`*.ai-native-lab.com`
- 开启 Force SSL、HTTP/2、HSTS、Block Common Exploits

静态容器挂载 `.deploy` 父目录，Nginx 的 root 指向 `.deploy/current`。不要单独挂载 `current` 符号链接，否则后续原子切换可能对容器不可见。
