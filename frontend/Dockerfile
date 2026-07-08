# Frontend image — React/Vite SPA served by nginx, proxying /api to the backend
# service by name on the compose network (mirrors vite.config.ts's dev proxy).

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build-time OIDC config (slice 008) — Vite bakes VITE_* vars into the bundle at
# build time. Defaults match the local Dex instance (docker-compose `gameobs`
# profile); a real deployment overrides these via `docker build --build-arg`.
ARG VITE_OIDC_AUTHORITY
ARG VITE_OIDC_CLIENT_ID
ARG VITE_OIDC_ISSUER
ENV VITE_OIDC_AUTHORITY=${VITE_OIDC_AUTHORITY}
ENV VITE_OIDC_CLIENT_ID=${VITE_OIDC_CLIENT_ID}
ENV VITE_OIDC_ISSUER=${VITE_OIDC_ISSUER}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
