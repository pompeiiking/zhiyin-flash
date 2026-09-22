# 前端镜像：Node 构建 → nginx 静态托管。
#
# 为什么需要它：前端此前只有 `npm run dev` 一条路径，`docker compose up` 起来的
# 只是一个只有 API 的后端 —— 打开 8000 端口看到的是接口文档，不是产品。
# "重新部署一遍确认整体没问题"在那种形态下做不到。
#
# 两段构建把 node_modules 关在构建期：运行镜像里只有 dist 与 nginx。

FROM node:20-alpine AS build

WORKDIR /app

# 先只拷依赖清单：依赖没变时这一层命中缓存，改业务代码不必重装 node_modules。
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.27-alpine

# 站点配置与反代规则一起进镜像：compose 里不需要再挂配置文件。
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
