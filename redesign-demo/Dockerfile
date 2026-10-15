FROM node:22-alpine AS build
WORKDIR /workspace/redesign-demo
COPY redesign-demo/package*.json ./
RUN npm ci --no-audit --no-fund
COPY redesign-demo/ ./
COPY zhiyin-src/template/zhiyin-modules /workspace/zhiyin-src/template/zhiyin-modules/
RUN npm run build
FROM nginx:1.27-alpine
COPY redesign-demo/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/redesign-demo/dist/ /usr/share/nginx/html/
EXPOSE 80
