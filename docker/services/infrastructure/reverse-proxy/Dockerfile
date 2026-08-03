FROM nginx:1.27-alpine

LABEL org.delfsa.component="infrastructure" org.delfsa.service="reverse-proxy"

RUN apk add --no-cache curl

COPY configs/nginx/nginx.conf /etc/nginx/nginx.conf

RUN mkdir -p /var/cache/nginx /var/run && \
    chown -R nginx:nginx /var/cache/nginx /var/run /etc/nginx

USER nginx

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -sf http://localhost:8080/healthz || exit 1

ENTRYPOINT ["nginx", "-g", "daemon off;"]
