FROM python:3.11-slim
ARG BUILD_REVISION=working-tree
ENV ZHIYIN_BUILD_REVISION=$BUILD_REVISION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY zhiyin-src/template/ /app/

RUN pip install .

# data/objects 必须**先在镜像里存在**：docker-compose.yml 把具名卷挂在这个路径上，
# 而具名卷的挂载点若在镜像里不存在，docker 会以 root 建出来 —— 应用以 app 用户运行，
# 材料上传就会 Permission denied（验证：docker compose exec zhiyin-flash touch data/objects/x）。
RUN mkdir -p /app/data/objects \
    && useradd --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["python", "-m", "zhiyin_boot", "--host", "0.0.0.0", "--port", "8000"]
