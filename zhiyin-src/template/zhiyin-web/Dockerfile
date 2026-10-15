FROM node:22-alpine AS build
WORKDIR /workspace/zhiyin-src/template/zhiyin-web
COPY zhiyin-src/template/zhiyin-web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY zhiyin-src/template/zhiyin-web/ ./
COPY zhiyin-src/template/zhiyin-modules /workspace/zhiyin-src/template/zhiyin-modules/
RUN npm run build
FROM nginx:1.27-alpine
COPY zhiyin-src/template/zhiyin-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/zhiyin-src/template/zhiyin-web/dist/ /usr/share/nginx/html/
EXPOSE 80
